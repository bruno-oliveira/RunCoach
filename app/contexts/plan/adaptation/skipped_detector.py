"""Skipped and rescheduled workout detection."""

from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date
from app.contexts.plan.repositories import SQLAlchemyPlanRepository

from ._helpers import today_date


def detect_skipped_workouts(
    plan_id: str,
    db: Session,
    *,
    since: Optional["datetime"] = None,
) -> Dict[str, int]:
    """Detect skipped and rescheduled workouts up to today.

    A workout is "unlinked" if no RunLog references it directly.
    Among unlinked workouts:
    - "rescheduled" = that week's total volume was still met (>= 80%)
    - "skipped" = truly missed (week volume not met)

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
        row[0] for row in
        db.query(RunLog.daily_workout_id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.daily_workout_id.isnot(None),
        )
        .all()
    )

    # Group unlinked past workouts by week
    unlinked_by_week: Dict[int, int] = defaultdict(int)
    since_date = _to_date(since) if since else None

    for workout, week_number in daily_workouts:
        workout_date = plan_start_date + timedelta(
            weeks=(week_number - 1),
            days=(workout.day_of_week - 1)
        )
        if workout_date > today:
            continue
        if since_date and workout_date <= since_date:
            continue
        if workout.id not in linked_workout_ids:
            unlinked_by_week[week_number] += 1

    if not unlinked_by_week:
        return {"skipped": 0, "rescheduled": 0}

    # Batch: fetch all run volumes for this plan in one query
    all_plan_runs = (
        db.query(RunLog.date, RunLog.distance_km)
        .filter(RunLog.training_plan_id == plan_id)
        .all()
    )
    weekly_actual_km: Dict[int, float] = defaultdict(float)
    for run_date, dist in all_plan_runs:
        rd = _to_date(run_date)
        if rd and plan_start_date:
            delta = (rd - plan_start_date).days
            if delta >= 0:
                wk = delta // 7 + 1
                weekly_actual_km[wk] += dist or 0.0

    weekly_plans = {
        wp.week_number: wp
        for wp in db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    }

    skipped = 0
    rescheduled = 0

    for week_num, unlinked_count in unlinked_by_week.items():
        wp = weekly_plans.get(week_num)
        if not wp:
            skipped += unlinked_count
            continue

        planned_km = wp.total_km or 0
        actual_km = weekly_actual_km.get(week_num, 0.0)
        if planned_km > 0 and actual_km >= planned_km * 0.8:
            rescheduled += unlinked_count
        else:
            skipped += unlinked_count

    return {"skipped": skipped, "rescheduled": rescheduled}
