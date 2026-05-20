"""Plan listing endpoint (my-plans page)."""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.infrastructure.config import settings
from app.dependencies import get_db, get_optional_user
from app.models import TrainingPlan, User
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.plan.plan_date_utils import compute_current_week
from app.contexts.plan.plan_type_registry import display_label as plan_display_label
from app.core.training.strength_plan import derive_experience_level
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


@router.get("/my-plans")
async def list_my_plans(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """List all training plans for current user."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    try:
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)

        adaptation_service = AdaptationService()
        today = date.today()
        for plan in plans:
            plan.target_distance_display = plan_display_label(plan)
            plan.experience_level = derive_experience_level(plan.current_weekly_km or 0)

            if plan.start_date:
                sd = plan.start_date
                start_d = sd.date() if isinstance(sd, datetime) else sd
                current_wk = compute_current_week(start_d, today, pre_start=0)
                if current_wk > plan.weeks_duration:
                    plan.status_label = "Completed"
                elif current_wk >= 1:
                    plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
                    try:
                        adaptation_service.check_alerts(
                            plan.id, current_user.id, db
                        )
                    except Exception:
                        logger.warning("Alert check failed for plan %s", plan.id, exc_info=True)
                else:
                    plan.status_label = f"Starts {start_d.strftime('%b')} {start_d.day}"
            else:
                plan.status_label = None

        return templates.TemplateResponse(
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
        raise HTTPException(status_code=500, detail="An internal error occurred while listing plans")
