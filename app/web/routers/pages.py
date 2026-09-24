"""Static page endpoints (home, privacy, post-connect setup)."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from sqlalchemy.orm import Session

from app.contexts.nutrition.nutrition_content import (
    TRAIL_FUEL_PHASES,
    generate_trail_fuel_ideas,
    generate_trail_nutrition_tips,
)
from app.contexts.plan.plan_helpers import current_active_plan, decorate_plan_status
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
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
    """Trail fuelling & racing tips — a public, top-level reference surface."""
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


@router.get("/setup/watch", response_class=HTMLResponse)
def setup_watch(
    request: Request,
    return_to: str = Query(default="/my-plans"),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Post-connect setup: walks the runner through the Intervals.icu toggles."""
    safe = (
        return_to
        if return_to.startswith("/") and not return_to.startswith("//")
        else "/my-plans"
    )
    return templates.TemplateResponse(
        request,
        "setup_watch.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "return_to": safe,
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


@router.get("/today", include_in_schema=False)
def today(
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Where the installed app opens: today's session, if there is one.

    The home screen icon is tapped on the way out of the door, so it should
    land on the Today card of the plan in progress — not on the marketing hero
    one tap away from it. Anyone without a running plan gets the home page,
    which is the right place to start one.
    """
    if current_user is not None:
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)
        local = local_today()
        for plan in plans:
            decorate_plan_status(plan, local)
        plan = current_active_plan(plans)
        if (
            plan is not None
            and plan.start_date is not None
            and getattr(plan, "status_label", None) != "Completed"
        ):
            return RedirectResponse(f"/plan/{plan.id}#today-card", status_code=302)
    return RedirectResponse("/", status_code=302)


_SERVICE_WORKER = Path(__file__).resolve().parents[1] / "static" / "js" / "sw.js"


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """The service worker, from the site root so its scope is the whole site.

    ``no-cache`` because browsers only pick up a new worker when the script's
    bytes change — a day-long static cache would pin every device to the old
    push handler for a day after each deploy.
    """
    return FileResponse(
        _SERVICE_WORKER,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest() -> JSONResponse:
    """The web app manifest — what makes RunCoach installable to a home screen.

    Served from a route rather than dropped in the static tree for two
    reasons. The content type has to be exactly ``application/manifest+json``
    (the global ``X-Content-Type-Options: nosniff`` header means a guessed
    type would make the browser refuse the manifest outright), and the
    manifest must not be cached behind a content hash while the icons it
    points at legitimately are.

    ``start_url`` is ``/today``, a redirect resolved on every launch: the
    installed app opens on the plan in progress, and a stale or missing plan
    falls back to the root rather than a dead link.
    """
    return JSONResponse(
        {
            "name": "RunCoach",
            "short_name": "RunCoach",
            "description": (
                "Personalised running plans that adapt to what you actually run."
            ),
            "start_url": "/today",
            "scope": "/",
            "display": "standalone",
            "background_color": "#FBFBFA",
            "theme_color": "#0E7C5A",
            "icons": [
                {
                    "src": "/static/icons/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": "/static/icons/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                },
                {
                    "src": "/static/icons/icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
            # Long-press the home-screen icon and these are the next steps.
            "shortcuts": [
                {"name": "Today", "url": "/today"},
                {"name": "My plans", "url": "/my-plans"},
                {"name": "Coach", "url": "/analytics"},
                {"name": "Recipes", "url": "/recipes"},
            ],
        },
        media_type="application/manifest+json",
    )
