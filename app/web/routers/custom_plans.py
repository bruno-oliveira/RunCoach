"""The custom-plan builder: a page, the options it offers, and a preview.

Creating the plan is not here: the builder posts to ``/generate-plan`` with its
choices in a ``custom_spec`` field, so a custom plan goes through the one
creation path every plan takes (duplicate check, plan limit, the anonymous
plan that survives sign-in).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from app.contexts.plan.custom_plan_service import (
    builder_options,
    preview,
    problems_json,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.training_config import DISTANCE_NAMES
from app.dependencies import get_optional_user, get_plan_generator
from app.exceptions import InvalidCustomPlanException, RunCoachException
from app.infrastructure.config import settings
from app.models import User
from app.schemas import PlanRequest
from app.web.rate_limit import custom_plan_preview_limiter
from app.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["custom-plans"])

# The request fields the builder sends; anything else in the body is ignored.
_REQUEST_FIELDS = (
    "current_km",
    "target_distance",
    "weeks",
    "max_runs_per_week",
    "is_trail",
    "target_elevation_gain_m",
    "training_terrain",
    "body_weight_kg",
    "recent_race_distance_km",
    "recent_race_time",
    "goal_time",
    "custom_spec",
)


@router.get("/plans/custom/new", response_class=HTMLResponse)
def custom_plan_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
):
    """The builder: the usual basics, then a session for every cell."""
    road = [(km, DISTANCE_NAMES[km]) for km in (5.0, 10.0, 21.1, 42.2)]
    return templates.TemplateResponse(
        request,
        "custom_plan.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "road_distances": road,
        },
    )


@router.get("/api/custom-plans/options")
def custom_plan_options(
    target_distance: float = Query(..., gt=0, le=163),
    max_runs_per_week: int = Query(4, ge=3, le=6),
    is_trail: bool = Query(False),
    target_elevation_gain_m: Optional[float] = Query(None, ge=0, le=10000),
    training_terrain: Optional[str] = Query(None),
    weeks: Optional[int] = Query(None, ge=1, le=52),
    current_km: Optional[float] = Query(None, ge=0, le=300),
):
    """Every cell of the grid for this goal and frequency, with its options."""
    return builder_options(
        target_distance=target_distance,
        runs_per_week=max_runs_per_week,
        is_trail=is_trail,
        target_elevation_gain_m=target_elevation_gain_m,
        training_terrain=training_terrain,
        weeks=weeks,
        current_km=current_km,
    )


@router.post("/api/custom-plans/preview")
def custom_plan_preview(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
):
    """The plan the current choices make — generated, never stored.

    A choice the request cannot hold answers 422 with the keyed problems, so
    the page can point at the cell; any other invalid input answers 422 with
    the message the creation form would show.
    """
    custom_plan_preview_limiter.check(request)
    fields = {k: payload[k] for k in _REQUEST_FIELDS if payload.get(k) is not None}
    if "custom_spec" not in fields:
        return JSONResponse({"message": "No sessions were chosen."}, status_code=422)
    try:
        plan_request = PlanRequest(**fields)
        return preview(plan_request, plan_generator)
    except InvalidCustomPlanException as e:
        return JSONResponse(
            {"message": e.user_message, "problems": problems_json(e.problems)},
            status_code=422,
        )
    except ValidationError as e:
        first = e.errors()[0].get("msg", "") if e.errors() else ""
        return JSONResponse(
            {"message": first.removeprefix("Value error, ") or "Check your values."},
            status_code=422,
        )
    except RunCoachException as e:
        return JSONResponse({"message": e.user_message}, status_code=422)
