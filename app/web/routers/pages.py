"""Static page endpoints (home, privacy, post-connect setup)."""

from datetime import timedelta
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

from app.application.single_run_service import (
    MAX_DAYS_AHEAD,
    current_vdot,
    plan_overlaps,
    recent_intensity_split,
    recent_views,
    suggest_for_today,
)
from app.contexts.nutrition.nutrition_content import (
    TRAIL_FUEL_PHASES,
    generate_trail_fuel_ideas,
    generate_trail_nutrition_tips,
)
from app.contexts.plan.plan_helpers import (
    PlanStatus,
    current_active_plan,
    in_progress_plan,
    plan_statuses,
)
from app.contexts.plan.recovery_block_service import RecoveryOffer, recovery_offer
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.coaching.intensity_split import TARGET_EASY_SHARE
from app.core.time_utils import local_today
from app.core.training.workouts.single_run import (
    SIMILAR_DISTANCE_MIN_KM,
    SIMILAR_DISTANCE_SHARE,
    SINGLE_RUN_TYPES,
    max_distance_km,
    min_distance_km,
)
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
    statuses: dict[str, PlanStatus] = {}
    offer: Optional[RecoveryOffer] = None
    if current_user is not None:
        today = local_today()
        plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)
        statuses = plan_statuses(plans, today)
        current_plan = current_active_plan(plans, statuses)
        plan_count = sum(1 for s in statuses.values() if not s.completed)
        # Every plan finished: the one just completed may have a recovery
        # block waiting, which is a better next step than "View this week".
        if current_plan is not None and statuses[current_plan.id].completed:
            offer = recovery_offer(current_plan, plans, today)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "current_plan": current_plan,
            "plan_statuses": statuses,
            "plan_count": plan_count,
            "recovery_offer": offer,
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


@router.get("/run", response_class=HTMLResponse)
def single_run_page(
    request: Request,
    source: Optional[str] = Query(default=None, alias="from"),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Single run — one generated workout, with no plan around it."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    today = local_today()
    plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(current_user.id)
    split = recent_intensity_split(current_user, db, today)
    return templates.TemplateResponse(
        request,
        "single_run.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "current_page": "run",
            "today": today,
            "has_plan": in_progress_plan(plans, today) is not None,
            # Sizing by time needs a pace to convert with; the form disables
            # the option up front rather than letting the request fail.
            "has_paces": current_vdot(current_user, db, today) is not None,
            "max_date": today + timedelta(days=MAX_DAYS_AHEAD),
            "run_types": [
                {
                    "key": run_type,
                    "min_km": min_distance_km(run_type),
                    "max_km": max_distance_km(run_type),
                }
                for run_type in SINGLE_RUN_TYPES
            ],
            "plan_overlaps": plan_overlaps(current_user, db, today),
            "similar_distance": {
                "share": SIMILAR_DISTANCE_SHARE,
                "min_km": SIMILAR_DISTANCE_MIN_KM,
            },
            "single_runs": recent_views(current_user, db),
            # The form opens on the coach's pick rather than a blank choice.
            # `?from=rest` is the plan's rest-day card, which promised a run
            # small enough not to undo the rest.
            "suggestion": suggest_for_today(
                current_user, db, today, rest_day=source == "rest"
            ),
            "split": (
                {
                    "easy_pct": round(split.easy_share * 100),
                    "target_pct": round(TARGET_EASY_SHARE * 100),
                    "verdict": split.verdict,
                }
                if split is not None
                else None
            ),
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
        statuses = plan_statuses(plans, local_today())
        plan = current_active_plan(plans, statuses)
        if (
            plan is not None
            and plan.start_date is not None
            and not statuses[plan.id].completed
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
