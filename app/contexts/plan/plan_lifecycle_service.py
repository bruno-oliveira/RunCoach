"""Plan lifecycle operations — limit checking, customization, deletion."""

import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.time_utils import local_today
from app.core.training.periodization.plan_calendar import plan_has_ended
from app.infrastructure.config import settings
from app.models import (
    DailyWorkout,
    PlanCustomization,
    RunLog,
    TrainingPlan,
    WeeklyPlan,
)

from .plan_adjustments import (
    adjust_distance,
    adjust_intensity,
    apply_ai_suggestions,
    swap_workout,
)
from .repositories import SQLAlchemyPlanRepository

logger = logging.getLogger(__name__)

MAX_PLANS_PER_USER = settings.max_plans_per_user


def has_reached_plan_limit(user_id: str, db: Session) -> bool:
    today = local_today()
    training_plans = SQLAlchemyPlanRepository(db).list_by_user(user_id)
    active_training = sum(1 for p in training_plans if not _is_plan_completed(p, today))
    return active_training >= MAX_PLANS_PER_USER


def _is_plan_completed(plan: TrainingPlan, today: date) -> bool:
    start = plan.start_date
    start_d = start.date() if isinstance(start, datetime) else start
    return plan_has_ended(start_d, plan.weeks_duration, today)


def customize_plan(
    training_plan: TrainingPlan,
    week_number: int,
    adjustment_type: str,
    adjustment_value: str,
    db: Session,
) -> list[dict]:
    plan_data = training_plan.plan_data if training_plan.plan_data else []

    # Pace zones let the structured builders inject the runner's actual paces
    # when regenerating a customised workout (falls back to generic cues).
    try:
        from app.contexts.plan.adaptation.reconcile import pace_zones_for

        pace_zones = pace_zones_for(training_plan)
    except Exception:  # pragma: no cover - defensive; never block customize
        pace_zones = None

    if adjustment_type == "intensity":
        plan_data = adjust_intensity(
            plan_data, week_number, adjustment_value, pace_zones
        )
    elif adjustment_type == "workout_swap":
        plan_data = swap_workout(plan_data, week_number, adjustment_value, pace_zones)
    elif adjustment_type == "distance":
        plan_data = adjust_distance(plan_data, week_number, float(adjustment_value))
    elif adjustment_type == "ai_suggest":
        plan_data = apply_ai_suggestions(
            plan_data, week_number, adjustment_value, pace_zones
        )

    customization = PlanCustomization(
        training_plan_id=training_plan.id,
        week_number=week_number,
        adjustment_type=adjustment_type,
        adjustment_value=adjustment_value,
    )
    db.add(customization)

    training_plan.plan_data = plan_data
    db.commit()

    return plan_data


def delete_plan(training_plan: TrainingPlan, db: Session) -> None:
    plan_id = training_plan.id

    from app.models.run_feedback import RunFeedback

    db.query(RunLog).filter(RunLog.training_plan_id == plan_id).update(
        {RunLog.training_plan_id: None, RunLog.daily_workout_id: None},
        synchronize_session="fetch",
    )

    weekly_plans = (
        db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan_id).all()
    )
    workout_ids = []
    for wp in weekly_plans:
        wids = [
            w.id
            for w in db.query(DailyWorkout.id)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .all()
        ]
        workout_ids.extend(wids)
    if workout_ids:
        db.query(RunFeedback).filter(
            RunFeedback.planned_workout_id.in_(workout_ids)
        ).update(
            {RunFeedback.planned_workout_id: None},
            synchronize_session="fetch",
        )

    for wp in weekly_plans:
        db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan_id).delete()

    db.query(PlanCustomization).filter(
        PlanCustomization.training_plan_id == plan_id
    ).delete()

    # A recovery block outlives the race plan it followed; it just stops
    # pointing at it.
    db.query(TrainingPlan).filter(TrainingPlan.follows_plan_id == plan_id).update(
        {TrainingPlan.follows_plan_id: None}, synchronize_session="fetch"
    )

    db.delete(training_plan)
    db.commit()
