"""Skipped and rescheduled workout detection."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.workouts.workout_registry import QUALITY_STIMULUS_TYPES
from app.models import DailyWorkout, RunLog, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import today_date


def detect_skipped_workouts(
    plan_id: str,
    db: Session,
    *,
    since: Optional["datetime"] = None,
) -> Dict[str, int]:
    """Detect skipped and rescheduled workouts up to today.

    A workout is "unlinked" if no RunLog references it directly. Among unlinked
    workouts the verdict depends on what the session's stimulus actually *is*:

    * *Volume-defined* sessions are judged on the week, as they always were —
      "rescheduled" when the week still met >= 80 % of its planned volume,
      "skipped" otherwise. Volume is the honest proxy for these because volume
      is what they are for.
    * *Intensity-defined* sessions (``QUALITY_STIMULUS_TYPES``) are judged on
      whether the week delivered quality work at all. They used to share the
      volume rule, which reported the session the runner most needed as one
      they had done elsewhere: swap the intervals for extra easy miles and the
      week still clears its volume bar, so the missed interval was counted as
      "rescheduled". A missed *long* run is far less likely to be masked by
      this, because it is usually the week's largest single contributor —
      dropping it drops the week under the bar by itself — which is why the
      volume proxy is left in charge of it.

    Args:
        since: If provided, only count workouts scheduled after this date.

    Returns:
        Dict with ``skipped`` and ``rescheduled`` counts.
    """
    training_plan = SQLAlchemyPlanRepository(db).get_by_id(plan_id)

    if not training_plan:
        return {"skipped": 0, "rescheduled": 0}

    sd = training_plan.start_date or training_plan.created_at
    plan_start_date = _to_date(sd)
    today = today_date()

    daily_workouts = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            DailyWorkout.workout_type.notin_(["rest", "recovery"]),
        )
        .all()
    )

    # Batch: fetch all linked workout IDs in one query
    linked_workout_ids = set(
        row[0]
        for row in db.query(RunLog.daily_workout_id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.daily_workout_id.isnot(None),
        )
        .all()
    )

    # Group unlinked past workouts by week, keeping each one's type: the verdict
    # depends on the stimulus the individual session asked for, not merely on
    # how many of them there were.
    unlinked_by_week: Dict[int, List[str]] = defaultdict(list)
    since_date = _to_date(since) if since else None

    for workout, week_number in daily_workouts:
        workout_date = plan_start_date + timedelta(
            weeks=(week_number - 1), days=(workout.day_of_week - 1)
        )
        if workout_date > today:
            continue
        if since_date and workout_date <= since_date:
            continue
        if workout.id not in linked_workout_ids:
            unlinked_by_week[week_number].append(workout.workout_type or "")

    if not unlinked_by_week:
        return {"skipped": 0, "rescheduled": 0}

    # Batch: fetch every run in this plan in one query. Whole rows rather than
    # columns, because the stimulus test needs ``effective_workout_type`` — an
    # ORM-level reconciliation of the explicit tag against the inference, which
    # a column query cannot reproduce.
    all_plan_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan_id).all()

    weekly_actual_km: Dict[int, float] = defaultdict(float)
    weekly_quality_runs: Dict[int, int] = defaultdict(int)
    for run in all_plan_runs:
        rd = _to_date(run.date)
        if rd and plan_start_date:
            delta = (rd - plan_start_date).days
            if delta >= 0:
                wk = delta // 7 + 1
                weekly_actual_km[wk] += run.distance_km or 0.0
                if run.effective_workout_type in QUALITY_STIMULUS_TYPES:
                    weekly_quality_runs[wk] += 1

    weekly_plans = {
        wp.week_number: wp
        for wp in db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    }

    skipped = 0
    rescheduled = 0

    for week_num, unlinked_types in unlinked_by_week.items():
        wp = weekly_plans.get(week_num)
        if not wp:
            skipped += len(unlinked_types)
            continue

        planned_km = wp.total_km or 0
        actual_km = weekly_actual_km.get(week_num, 0.0)
        volume_met = planned_km > 0 and actual_km >= planned_km * 0.8

        # Quality runs are consumed as they are credited, so one delivered
        # quality session cannot excuse two unlinked ones.
        quality_available = weekly_quality_runs.get(week_num, 0)

        for workout_type in unlinked_types:
            if workout_type in QUALITY_STIMULUS_TYPES:
                if quality_available > 0:
                    quality_available -= 1
                    rescheduled += 1
                else:
                    skipped += 1
            elif volume_met:
                rescheduled += 1
            else:
                skipped += 1

    return {"skipped": skipped, "rescheduled": rescheduled}
