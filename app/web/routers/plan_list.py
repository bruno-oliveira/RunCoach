"""Plan listing endpoint (my-plans page)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.contexts.plan.plan_helpers import plan_statuses
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.time_utils import local_today
from app.dependencies import get_db, get_optional_user
from app.infrastructure.config import settings
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


@router.get("/my-plans")
def list_my_plans(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """List all training plans for current user."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    try:
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)

        statuses = plan_statuses(plans, local_today())
        # Split here rather than in the template: the template would have to
        # reach into the statuses mapping to do it, and this list is what the
        # page actually renders.
        active_plans = [p for p in plans if not statuses[p.id].completed]
        completed_plans = [p for p in plans if statuses[p.id].completed]

        return templates.TemplateResponse(
            request,
            "my_plans.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plans": plans,
                "active_plans": active_plans,
                "completed_plans": completed_plans,
                "plan_statuses": statuses,
                "plan_count": len(active_plans),
                "max_plans": 3,
            },
        )
    except Exception as e:
        logger.error("Error listing plans: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="An internal error occurred while listing plans"
        )
