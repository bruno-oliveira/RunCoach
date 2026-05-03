"""Template context building for plan views."""

from datetime import date, datetime
from typing import Any, Optional

from fastapi import Request

from app.config import settings
from app.core.training.strength_plan import derive_experience_level
from app.models import TrainingPlan, User
from .plan_date_utils import (
    build_week_dates,
    compute_current_week,
    ensure_seven_days,
    next_monday,
    workout_dates,
)


def plan_view_context(
    request: Request,
    current_user: Optional[User],
    training_plan: TrainingPlan,
    plan_data: list[dict],
    nutrition_plan: dict,
    **extra: Any,
) -> dict[str, Any]:
    """Build the standard plan.html template context dict."""
    plan_data = ensure_seven_days(plan_data)

    start_date_val = None
    current_week_number = None
    week_dates = None
    workout_date_labels: dict[tuple[int, int], str] = {}
    today_obj = date.today()

    plan_completed = False
    if training_plan.start_date:
        sd = training_plan.start_date
        start_date_val = sd.date() if isinstance(sd, datetime) else sd if isinstance(sd, date) else sd
        num_weeks = len(plan_data) if plan_data else training_plan.weeks_duration
        week_dates = build_week_dates(start_date_val, num_weeks)
        current_week_number = compute_current_week(start_date_val, today_obj)
        if current_week_number and current_week_number > num_weeks:
            current_week_number = None
            plan_completed = True
        workout_date_labels = workout_dates(start_date_val, num_weeks)

    ctx: dict[str, Any] = {
        "request": request,
        "user": current_user,
        "google_client_id": settings.google_client_id,
        "plan": plan_data,
        "plan_id": training_plan.id,
        "training_plan": training_plan,
        "current_km": training_plan.current_weekly_km,
        "experience_level": derive_experience_level(training_plan.current_weekly_km or 0),
        "target_distance": training_plan.target_distance,
        "weeks": training_plan.weeks_duration,
        "nutrition_plan": nutrition_plan,
        "nutrition_phases": (
            training_plan.nutrition_phases_data
            if training_plan.nutrition_phases_data
            else {}
        ),
        "race_protocol": (
            training_plan.race_protocol_data
            if training_plan.race_protocol_data
            else {}
        ),
        "vdot": training_plan.vdot,
        "logged_runs": {},
        "performance_analysis": None,
        "progress_data": None,
        "start_date": start_date_val,
        "current_week_number": current_week_number,
        "plan_completed": plan_completed,
        "today_iso": today_obj.isoformat(),
        "current_day_of_week": today_obj.isoweekday(),
        "week_dates": week_dates,
        "workout_date_labels": workout_date_labels,
        "next_monday": next_monday(),
    }
    ctx.update(extra)
    return ctx
