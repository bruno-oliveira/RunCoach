"""Triathlon training plan endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.core.triathlon_plan_generator import TriathlonPlanGenerator
from app.dependencies import get_db, get_optional_user
from app.models.triathlon_plan import TriathlonPlan
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["triathlon"])
templates = Jinja2Templates(directory="app/templates")

_generator = TriathlonPlanGenerator()

DISTANCE_LABELS = {
    "sprint": "Sprint Triathlon",
    "olympic": "Olympic Triathlon",
    "half_ironman": "Half Ironman (70.3)",
}


# ---------------------------------------------------------------------------
# Selection page
# ---------------------------------------------------------------------------


@router.get("/triathlon", response_class=HTMLResponse)
async def triathlon_index(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "triathlon.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
            "current_page": "triathlon",
        },
    )


# ---------------------------------------------------------------------------
# Generate plan
# ---------------------------------------------------------------------------


@router.post("/triathlon/generate", response_class=HTMLResponse)
async def generate_triathlon_plan(
    request: Request,
    distance: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    anonymous_user_id: Optional[str] = Cookie(None),
) -> HTMLResponse:
    if distance not in DISTANCE_LABELS:
        raise HTTPException(status_code=400, detail=f"Invalid distance: {distance}")

    try:
        weeks = _generator.generate_plan(distance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Only persist user_id for authenticated (DB-backed) users; anonymous cookie
    # IDs are not rows in the users table so we leave user_id NULL instead.
    user_id: Optional[str] = current_user.id if current_user else None

    plan = TriathlonPlan(
        user_id=user_id,
        distance=distance,
        weeks_duration=len(weeks),
        plan_data=json.dumps(weeks),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return RedirectResponse(url=f"/triathlon/plan/{plan.id}", status_code=303)


# ---------------------------------------------------------------------------
# View plan
# ---------------------------------------------------------------------------


@router.get("/triathlon/plan/{plan_id}", response_class=HTMLResponse)
async def view_triathlon_plan(
    plan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    anonymous_user_id: Optional[str] = Cookie(None),
) -> HTMLResponse:
    plan = db.query(TriathlonPlan).filter(TriathlonPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Basic ownership check: allow if plan is unclaimed, belongs to current user,
    # or belongs to the anonymous session.
    owner_ok = (
        plan.user_id is None
        or (current_user and plan.user_id == current_user.id)
        or (anonymous_user_id and plan.user_id == anonymous_user_id)
    )
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Access denied")

    weeks = json.loads(plan.plan_data)
    distance_info = _generator.get_distance_info(plan.distance)

    # Build phase summary for the legend
    phases = []
    seen = set()
    for w in weeks:
        p = w["phase"]
        if p not in seen:
            phases.append(p)
            seen.add(p)

    return templates.TemplateResponse(
        "triathlon_plan.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
            "current_page": "triathlon",
            "plan": plan,
            "weeks": weeks,
            "distance_info": distance_info,
            "distance_label": DISTANCE_LABELS[plan.distance],
            "phases": phases,
        },
    )


# ---------------------------------------------------------------------------
# Delete plan
# ---------------------------------------------------------------------------


@router.delete("/api/triathlon/plan/{plan_id}")
async def delete_triathlon_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    anonymous_user_id: Optional[str] = Cookie(None),
):
    plan = db.query(TriathlonPlan).filter(TriathlonPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    owner_ok = (
        plan.user_id is None
        or (current_user and plan.user_id == current_user.id)
        or (anonymous_user_id and plan.user_id == anonymous_user_id)
    )
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(plan)
    db.commit()
    return {"message": "Triathlon plan deleted"}
