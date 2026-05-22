"""Analytics dashboard HTML page."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.plan.plan_type_registry import display_label as plan_display_label
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.dependencies import get_db, get_optional_user
from app.infrastructure.config import settings
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics-page"])
templates = create_templates()


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Analytics dashboard page."""
    plans = []
    if current_user:
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)

    plan_summaries = []
    for p in plans:
        plan_summaries.append(
            {
                "id": p.id,
                "label": f"{plan_display_label(p)} — {p.weeks_duration}wk",
                "target_distance_km": p.target_distance_km,
            }
        )

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
