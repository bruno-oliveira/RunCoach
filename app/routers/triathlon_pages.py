"""Triathlon page endpoints (HTML responses)."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.export.triathlon_pdf_generator import TriathlonPDFGenerator
from app.core.generators.triathlon_plan_generator import TriathlonPlanGenerator
from app.dependencies import get_db, get_optional_user, get_plan_service
from app.models.triathlon_plan import TriathlonPlan
from app.models.user import User
from app.services.plan_service import PlanService
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["triathlon-pages"])
templates = create_templates()

_generator = TriathlonPlanGenerator()
_pdf_generator = TriathlonPDFGenerator()

DISTANCE_LABELS = {
    "sprint": "Sprint Triathlon",
    "olympic": "Olympic Triathlon",
    "half_ironman": "Half Ironman (70.3)",
}


def _verify_triathlon_plan_ownership(
    plan: TriathlonPlan,
    current_user: Optional[User],
    anonymous_user_id: Optional[str],
) -> None:
    owner_ok = (
        plan.user_id is None
        or (current_user and plan.user_id == current_user.id)
        or (anonymous_user_id and plan.user_id == anonymous_user_id)
    )
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Access denied")


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
    plan_service: PlanService = Depends(get_plan_service),
) -> HTMLResponse:
    if distance not in DISTANCE_LABELS:
        raise HTTPException(status_code=400, detail=f"Invalid distance: {distance}")

    # Only persist user_id for authenticated (DB-backed) users; anonymous cookie
    # IDs are not rows in the users table so we leave user_id NULL instead.
    user_id: Optional[str] = current_user.id if current_user else None

    # Enforce per-user plan limit (counts both training and triathlon plans)
    if user_id and plan_service.has_reached_plan_limit(user_id, db):
        raise HTTPException(
            status_code=400,
            detail=f"Plan limit reached. You can have a maximum of {plan_service.MAX_PLANS_PER_USER} plans.",
        )

    # --- Duplicate detection ---
    if user_id:
        existing = (
            db.query(TriathlonPlan)
            .filter(TriathlonPlan.user_id == user_id, TriathlonPlan.distance == distance)
            .first()
        )
        if existing:
            logger.info(
                f"Duplicate triathlon plan detected for user {user_id} — returning existing plan {existing.id}"
            )
            return RedirectResponse(url=f"/triathlon/plan/{existing.id}", status_code=303)

    try:
        weeks = _generator.generate_plan(distance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    plan = TriathlonPlan(
        user_id=user_id,
        distance=distance,
        weeks_duration=len(weeks),
        plan_data=weeks,
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

    _verify_triathlon_plan_ownership(plan, current_user, anonymous_user_id)

    weeks = plan.plan_data
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
# Download PDF
# ---------------------------------------------------------------------------


@router.get("/triathlon/download-pdf/{plan_id}")
async def download_triathlon_pdf(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    anonymous_user_id: Optional[str] = Cookie(None),
) -> FileResponse:
    plan = db.query(TriathlonPlan).filter(TriathlonPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    _verify_triathlon_plan_ownership(plan, current_user, anonymous_user_id)

    try:
        pdf_path = _pdf_generator.generate_pdf(plan)
    except Exception:
        logger.exception("Triathlon PDF generation error for plan %s", plan_id)
        raise HTTPException(status_code=500, detail="PDF generation failed")

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="PDF generation failed — file not created")

    label = DISTANCE_LABELS.get(plan.distance, plan.distance).replace(" ", "_")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"triathlon_{label}_{plan_id[:8]}.pdf",
    )
