"""Plan listing endpoint (my-plans page)."""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_optional_user
from app.models import TrainingPlan, User
from app.models.triathlon_plan import TriathlonPlan
from app.constants import DISTANCE_NAMES
from app.services.adaptation_service import AdaptationService
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
        plans = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.user_id == current_user.id)
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )

        adaptation_service = AdaptationService()
        today = date.today()
        for plan in plans:
            td = plan.target_distance_km
            if td > 0:
                plan.target_distance_display = DISTANCE_NAMES.get(td, f"{td}km")
            elif plan.plan_type == "performance":
                plan.target_distance_display = "Performance"
            else:
                plan.target_distance_display = f"{td}km"
            plan.experience_level = derive_experience_level(plan.current_weekly_km or 0)

            if plan.start_date:
                sd = plan.start_date
                start_d = sd.date() if isinstance(sd, datetime) else sd
                delta_days = (today - start_d).days
                current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
                if current_wk > plan.weeks_duration:
                    plan.status_label = "Completed"
                elif current_wk >= 1:
                    plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
                    try:
                        adaptation_service.check_alerts(
                            plan.id, current_user.id, db
                        )
                    except Exception:
                        logger.warning(f"Alert check failed for plan {plan.id}", exc_info=True)
                else:
                    plan.status_label = f"Starts {start_d.strftime('%b')} {start_d.day}"
            else:
                plan.status_label = None

        triathlon_plans = (
            db.query(TriathlonPlan)
            .filter(TriathlonPlan.user_id == current_user.id)
            .order_by(TriathlonPlan.created_at.desc())
            .all()
        )

        _tri_labels = {
            "sprint": "Sprint Triathlon",
            "olympic": "Olympic Triathlon",
            "half_ironman": "Half Ironman (70.3)",
        }
        for tp in triathlon_plans:
            tp.distance_label = _tri_labels.get(tp.distance, tp.distance)

        return templates.TemplateResponse(
            "my_plans.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plans": plans,
                "plan_count": sum(1 for p in plans if p.status_label != "Completed"),
                "max_plans": 3,
                "triathlon_plans": triathlon_plans,
            },
        )
    except Exception as e:
        logger.error(f"Error listing plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while listing plans")
