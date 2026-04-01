"""Reusable helpers for plan route handlers."""

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TrainingPlan, User
from app.dependencies import verify_plan_ownership
from app.template_helpers import create_templates


templates = create_templates()


def error_response(
    request: Request,
    user: Optional[User],
    error: str,
    error_type: str,
    suggestion: Optional[str] = None,
):
    """Build an index.html TemplateResponse with the standard error context."""
    ctx: dict[str, Any] = {
        "request": request,
        "user": user,
        "google_client_id": settings.google_client_id,
        "error": error,
        "error_type": error_type,
    }
    if suggestion:
        ctx["suggestion"] = suggestion
    return templates.TemplateResponse("index.html", ctx)


def get_plan_or_404(
    plan_id: str,
    db: Session,
    current_user: Optional[User] = None,
    anonymous_user_id: Optional[str] = None,
    *,
    check_ownership: bool = True,
    require_user_match: bool = False,
) -> TrainingPlan:
    """Fetch a TrainingPlan by ID, raising 404/403 as appropriate.

    Args:
        plan_id: The plan's primary key.
        db: SQLAlchemy session.
        current_user: Authenticated user (may be None for anonymous).
        anonymous_user_id: Cookie-based anonymous session ID.
        check_ownership: If True, verify the caller owns the plan.
        require_user_match: If True, match on user_id column directly
            (used by endpoints that already require authentication).
    """
    training_plan = (
        db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    )

    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if require_user_match:
        if not current_user:
            raise HTTPException(
                status_code=403, detail="Authentication required to access this plan"
            )
        if training_plan.user_id != current_user.id:
            raise HTTPException(
                status_code=403, detail="Not authorized to access this plan"
            )
    elif check_ownership:
        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this plan"
            )

    return training_plan


def _build_week_dates(start_date: date, num_weeks: int) -> list[dict]:
    """Build a list of week date ranges from a start date."""
    week_dates = []
    for i in range(num_weeks):
        week_start = start_date + timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        week_dates.append({
            "week": i + 1,
            "start": week_start.strftime("%b %-d"),
            "end": week_end.strftime("%b %-d"),
            "start_iso": week_start.isoformat(),
        })
    return week_dates


def _compute_current_week(start_date: date, today: date) -> Optional[int]:
    """Compute 1-indexed current week number, or None if plan hasn't started or is over."""
    delta_days = (today - start_date).days
    if delta_days < 0:
        return None
    return (delta_days // 7) + 1


def _next_monday() -> str:
    """Return the ISO date string of the next Monday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).isoformat()


def _workout_dates(start_date: date, num_weeks: int) -> dict[tuple[int, int], str]:
    """Map (week, day) to formatted date string like 'Mon, Mar 3'."""
    day_abbrevs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    result = {}
    for w in range(num_weeks):
        week_start = start_date + timedelta(weeks=w)
        for d in range(7):
            dt = week_start + timedelta(days=d)
            result[(w + 1, d + 1)] = f"{day_abbrevs[d]}, {dt.strftime('%b %-d')}"
    return result


def plan_view_context(
    request: Request,
    current_user: Optional[User],
    training_plan: TrainingPlan,
    plan_data: list[dict],
    nutrition_plan: dict,
    **extra: Any,
) -> dict[str, Any]:
    """Build the standard plan.html template context dict."""
    # Calendar tracking
    start_date_val = None
    current_week_number = None
    week_dates = None
    workout_date_labels: dict[tuple[int, int], str] = {}
    today_obj = date.today()

    if training_plan.start_date:
        sd = training_plan.start_date
        # Coerce datetime → date (datetime is a subclass of date, so check it first)
        start_date_val = sd.date() if isinstance(sd, datetime) else sd if isinstance(sd, date) else sd
        num_weeks = len(plan_data) if plan_data else training_plan.weeks_duration
        week_dates = _build_week_dates(start_date_val, num_weeks)
        current_week_number = _compute_current_week(start_date_val, today_obj)
        if current_week_number and current_week_number > num_weeks:
            current_week_number = None  # plan is over
        workout_date_labels = _workout_dates(start_date_val, num_weeks)

    ctx: dict[str, Any] = {
        "request": request,
        "user": current_user,
        "google_client_id": settings.google_client_id,
        "plan": plan_data,
        "plan_id": training_plan.id,
        "training_plan": training_plan,
        "current_km": training_plan.current_weekly_km,
        "target_distance": training_plan.target_distance,
        "weeks": training_plan.weeks_duration,
        "nutrition_plan": nutrition_plan,
        "nutrition_phases": (
            json.loads(training_plan.nutrition_phases_data)
            if training_plan.nutrition_phases_data
            else {}
        ),
        "race_protocol": (
            json.loads(training_plan.race_protocol_data)
            if training_plan.race_protocol_data
            else {}
        ),
        "vdot": training_plan.vdot,
        "logged_runs": {},
        "performance_analysis": None,
        "progress_data": None,
        # Calendar tracking
        "start_date": start_date_val,
        "current_week_number": current_week_number,
        "today_iso": today_obj.isoformat(),
        "current_day_of_week": today_obj.isoweekday(),
        "week_dates": week_dates,
        "workout_date_labels": workout_date_labels,
        "next_monday": _next_monday(),
    }
    ctx.update(extra)
    return ctx
