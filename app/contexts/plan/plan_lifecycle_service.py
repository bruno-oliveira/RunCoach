"""Plan lifecycle operations — limit checking, customization, deletion."""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

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
    today = date.today()
    training_plans = SQLAlchemyPlanRepository(db).list_by_user(user_id)
    active_training = sum(
        1 for p in training_plans
        if not _is_plan_completed(p, today)
    )
    return active_training >= MAX_PLANS_PER_USER


def _is_plan_completed(plan: TrainingPlan, today: date) -> bool:
    if not plan.start_date:
        return False
    start_d = plan.start_date.date() if isinstance(plan.start_date, datetime) else plan.start_date
    end_date = start_d + timedelta(weeks=plan.weeks_duration)
    return today > end_date


def customize_plan(
    training_plan: TrainingPlan,
    week_number: int,
    adjustment_type: str,
    adjustment_value: str,
    db: Session,
) -> list[dict]:
    plan_data = training_plan.plan_data if training_plan.plan_data else []

    if adjustment_type == "intensity":
        plan_data = adjust_intensity(plan_data, week_number, adjustment_value)
    elif adjustment_type == "workout_swap":
        plan_data = swap_workout(plan_data, week_number, adjustment_value)
    elif adjustment_type == "distance":
        plan_data = adjust_distance(plan_data, week_number, float(adjustment_value))
    elif adjustment_type == "ai_suggest":
        plan_data = apply_ai_suggestions(plan_data, week_number, adjustment_value)

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
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
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
        db.query(DailyWorkout).filter(
            DailyWorkout.weekly_plan_id == wp.id
        ).delete()
    db.query(WeeklyPlan).filter(
        WeeklyPlan.training_plan_id == plan_id
    ).delete()

    db.query(PlanCustomization).filter(
        PlanCustomization.training_plan_id == plan_id
    ).delete()

    db.delete(training_plan)
    db.commit()
