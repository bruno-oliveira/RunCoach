"""Analytics dashboard HTML page."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_optional_user
from app.models import TrainingPlan
from app.constants import DISTANCE_NAMES
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics-page"])
templates = create_templates()


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Analytics dashboard page."""
    plans = []
    if current_user:
        plans = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.user_id == current_user.id)
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )

    plan_summaries = []
    for p in plans:
        td = p.target_distance_km
        if td > 0:
            label = DISTANCE_NAMES.get(td, f"{td}km")
        elif p.plan_type == "performance":
            label = "Performance"
        elif p.plan_type == "fitness":
            label = "Fitness"
        else:
            label = f"{td}km"
        plan_summaries.append({
            "id": p.id,
            "label": f"{label} — {p.weeks_duration}wk",
            "target_distance_km": td,
        })

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": current_user,
            "current_page": "analytics",
            "google_client_id": settings.google_client_id,
            "plans": plan_summaries,
        },
    )
