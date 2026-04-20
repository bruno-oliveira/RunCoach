"""Shared helpers for the adaptation sub-package."""

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

# Regex to strip legacy adaptation/recalibration notes from workout notes
ANNOTATION_RE = re.compile(r"\s*\((Adapted|Recalibrated|Adjusted):[^)]*\)")


def today_date():
    """Return today's date in UTC, timezone-naive (for SQLite compat)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).date()


def backfill_baselines(training_plan: TrainingPlan, db: Session) -> None:
    """Ensure every DailyWorkout has a baseline_distance_km.

    For plans created before the column existed, sets baseline to
    current distance_km.
    """
    workouts_needing_backfill = (
        db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == training_plan.id,
            DailyWorkout.baseline_distance_km.is_(None),
            DailyWorkout.distance_km.isnot(None),
            DailyWorkout.distance_km > 0,
        )
        .all()
    )
    if not workouts_needing_backfill:
        return

    for workout in workouts_needing_backfill:
        workout.baseline_distance_km = workout.distance_km
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


def batch_workouts_by_week(
    week_ids: List[str],
    db: Session,
) -> Dict[str, List[DailyWorkout]]:
    """Fetch all DailyWorkouts for the given WeeklyPlan IDs in one query.

    Returns {weekly_plan_id: [DailyWorkout, ...]}.
    """
    all_workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id.in_(week_ids))
        .all()
    )
    grouped: Dict[str, list] = defaultdict(list)
    for w in all_workouts:
        grouped[w.weekly_plan_id].append(w)
    return grouped
