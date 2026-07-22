"""Static page endpoints (home, privacy)."""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.nutrition.nutrition_content import (
    TRAIL_FUEL_PHASES,
    generate_trail_fuel_ideas,
    generate_trail_nutrition_tips,
)
from app.contexts.plan.plan_helpers import current_active_plan, decorate_plan_status
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.time_utils import local_today
from app.dependencies import get_db, get_optional_user
from app.infrastructure.config import settings
from app.models import User
from app.template_helpers import create_templates

router = APIRouter(tags=["pages"])
templates = create_templates()


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    # Signed-in runners get a training-status hero instead of the first-time
    # pitch, driven by their current plan. Anonymous visitors skip the query.
    current_plan = None
    plan_count = 0
    if current_user is not None:
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)
        today = local_today()
        for plan in plans:
            decorate_plan_status(plan, today)
        current_plan = current_active_plan(plans)
        plan_count = sum(1 for p in plans if p.status_label != "Completed")

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "current_plan": current_plan,
            "plan_count": plan_count,
        },
    )


@router.get("/tips", response_class=HTMLResponse)
def tips_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    """Trail fuelling & racing tips — a public, top-level reference surface.

    Promoted out of the Race Prep page so the guidance is discoverable on its
    own rather than buried beside the GPX pacing tool.
    """
    return templates.TemplateResponse(
        request,
        "tips.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "current_page": "tips",
            "trail_fuel_ideas": generate_trail_fuel_ideas(),
            "trail_fuel_phases": TRAIL_FUEL_PHASES,
            "trail_tips": generate_trail_nutrition_tips(),
        },
    )


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
        },
    )
