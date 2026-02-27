"""Reusable helpers for plan route handlers."""

import json
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TrainingPlan, User
from app.dependencies import verify_plan_ownership


templates = Jinja2Templates(directory="app/templates")


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
    if require_user_match and current_user:
        training_plan = (
            db.query(TrainingPlan)
            .filter(
                TrainingPlan.id == plan_id,
                TrainingPlan.user_id == current_user.id,
            )
            .first()
        )
    else:
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )

    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if check_ownership and not require_user_match:
        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this plan"
            )

    return training_plan


def plan_view_context(
    request: Request,
    current_user: Optional[User],
    training_plan: TrainingPlan,
    plan_data: list[dict],
    nutrition_plan: dict,
    **extra: Any,
) -> dict[str, Any]:
    """Build the standard plan.html template context dict."""
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
    }
    ctx.update(extra)
    return ctx
