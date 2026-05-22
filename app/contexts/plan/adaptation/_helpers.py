"""Shared helpers for the adaptation sub-package."""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.core.training.baseline_recovery import (
    ANNOTATION_RE,
    parse_adjustment_multiplier,
    recover_baseline,
    strip_annotations,
)
from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan

# ANNOTATION_RE is re-exported from the pure core module (single source of
# truth) so existing `from ._helpers import ANNOTATION_RE` imports keep working.
_ = ANNOTATION_RE  # re-export marker


def today_date():
    """Return today's date in UTC, timezone-naive (for SQLite compat)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).date()


def backfill_baselines(training_plan: TrainingPlan, db: Session) -> None:
    """Ensure every DailyWorkout has a correct baseline_distance_km.

    For plans created before the column existed, sets the baseline to the
    current distance_km. Crucially, a current distance that still carries an
    ``(Adjusted: xN)`` note is *not* a true baseline (it was inflated by an
    earlier adjustment), so it is back-computed from the note's multiplier
    rather than frozen as-is.

    Also self-heals already-corrupted rows: when a non-null baseline equals
    the (annotated) distance, the baseline was frozen to an adjusted value by
    an earlier backfill — recover the true original and strip the stale note.
    """
    workouts = (
        db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == training_plan.id,
            DailyWorkout.distance_km.isnot(None),
            DailyWorkout.distance_km > 0,
        )
        .all()
    )

    dirty = False
    for workout in workouts:
        if workout.baseline_distance_km is None:
            multiplier = parse_adjustment_multiplier(workout.notes)
            if multiplier and multiplier != 1.0:
                true_value = round(workout.distance_km / multiplier, 1)
                workout.baseline_distance_km = true_value
                workout.distance_km = true_value
                workout.notes = strip_annotations(workout.notes)
            else:
                workout.baseline_distance_km = workout.distance_km
            dirty = True
            continue

        true_baseline, true_distance, recovered = recover_baseline(
            workout.distance_km,
            workout.baseline_distance_km,
            workout.notes,
        )
        if recovered:
            workout.baseline_distance_km = true_baseline
            workout.distance_km = true_distance
            workout.notes = strip_annotations(workout.notes)
            dirty = True

    if dirty:
        db.flush()


def parse_plan_data_lookups(
    training_plan: TrainingPlan,
) -> Tuple[List[Dict], Dict[int, Dict], Dict[Tuple[int, int], Dict]]:
    """Parse plan_data JSON and build lookup dicts for plan syncing.

    Returns (plan_data, pd_week, pd_workout) where:
    - plan_data: the parsed list of week dicts
    - pd_week: {week_number: week_dict}
    - pd_workout: {(week_number, day): workout_dict}
    """
    plan_data = training_plan.plan_data if training_plan.plan_data else []
    pd_week: Dict[int, Dict] = {}
    pd_workout: Dict[Tuple[int, int], Dict] = {}
    for wk in plan_data:
        pd_week[wk["week"]] = wk
        for wo in wk.get("daily_workouts", []):
            pd_workout[(wk["week"], wo["day"])] = wo
    return plan_data, pd_week, pd_workout


def is_current_week_in_progress(
    plan_id: str,
    start_date: date,
    current_week: int,
    current_day_of_week: int,
    db: Session,
) -> bool:
    """Whether the user has already started the current week.

    A week is "in progress" once the first day of it has passed (today is
    past Monday) OR any run inside that week's date range has been logged.
    Used to decide whether adjustments are allowed to modify the current
    week: only a fresh, untouched current week (Monday + no logs) is
    adjustable.
    """
    if current_day_of_week > 1:
        return True
    start_of_current_week = datetime.combine(
        start_date + timedelta(weeks=current_week - 1),
        datetime.min.time(),
    )
    has_run = (
        db.query(RunLog.id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.date >= start_of_current_week,
        )
        .first()
    )
    return has_run is not None


def batch_workouts_by_week(
    week_ids: List[str],
    db: Session,
) -> Dict[str, List[DailyWorkout]]:
    """Fetch all DailyWorkouts for the given WeeklyPlan IDs in one query.

    Returns {weekly_plan_id: [DailyWorkout, ...]}.
    """
    all_workouts = (
        db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id.in_(week_ids)).all()
    )
    grouped: Dict[str, list] = defaultdict(list)
    for w in all_workouts:
        grouped[w.weekly_plan_id].append(w)
    return grouped
