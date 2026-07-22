"""Plan listing endpoint (my-plans page)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.contexts.plan.plan_helpers import decorate_plan_status
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

        today = local_today()
        for plan in plans:
            decorate_plan_status(plan, today)

        return templates.TemplateResponse(
            request,
            "my_plans.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plans": plans,
                "plan_count": sum(1 for p in plans if p.status_label != "Completed"),
                "max_plans": 3,
            },
        )
    except Exception as e:
        logger.error("Error listing plans: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="An internal error occurred while listing plans"
        )
