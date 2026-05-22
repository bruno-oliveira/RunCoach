"""Plan fetching with ownership validation."""

from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.dependencies import verify_plan_ownership
from app.infrastructure.config import settings
from app.models import TrainingPlan, User
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
    return templates.TemplateResponse(request, "index.html", ctx)


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
    training_plan = SQLAlchemyPlanRepository(db).get_by_id(plan_id)

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
