"""Plan sharing, start date, save/claim, delete, and PDF download endpoints."""

import logging
import os
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.plan_helpers import get_plan_or_404, plan_view_context
from app.contexts.plan.plan_service import PlanService
from app.contexts.plan.plan_type_registry import display_label as plan_display_label
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.dependencies import (
    get_current_user,
    get_db,
    get_optional_user,
    get_pdf_generator,
    get_plan_service,
)
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.export.plan_export_dto import PlanExportDTO
from app.models import User
from app.rate_limit import plan_generation_limiter
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


# ---------------------------------------------------------------------------
# Start date
# ---------------------------------------------------------------------------


class StartDateRequest(BaseModel):
    start_date: date


@router.post("/api/plan/{plan_id}/start")
async def set_plan_start_date(
    plan_id: str,
    body: StartDateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the start date for a training plan."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    training_plan.start_date = datetime.combine(body.start_date, datetime.min.time())
    db.commit()
    return {"ok": True, "start_date": body.start_date.isoformat()}


# ---------------------------------------------------------------------------
# Share plan
# ---------------------------------------------------------------------------


@router.post("/api/plan/{plan_id}/share")
async def toggle_share_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate or revoke a share link for a training plan."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    if training_plan.share_token:
        training_plan.share_token = None
        db.commit()
        return {"shared": False, "share_token": None, "share_url": None}

    token = secrets.token_urlsafe(16)
    training_plan.share_token = token
    db.commit()
    return {"shared": True, "share_token": token}


@router.get("/shared/{share_token}", response_class=HTMLResponse)
async def view_shared_plan(
    share_token: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_service: PlanService = Depends(get_plan_service),
):
    """View a publicly shared training plan (read-only)."""

    training_plan = SQLAlchemyPlanRepository(db).get_by_share_token(share_token)
    if not training_plan:
        raise HTTPException(status_code=404, detail="Shared plan not found")

    plan_data = training_plan.plan_data
    plan_data = plan_service.enrich_plan_data_with_ids(plan_data, training_plan.id, db)

    nutrition_plan = plan_service.nutrition_for_template(
        training_plan.nutrition_plan_data
    )

    owner = SQLAlchemyUserRepository(db).get_by_id(training_plan.user_id)
    extra = plan_service.get_plan_view_data(training_plan, owner, db)

    ctx = plan_view_context(
        request, current_user, training_plan, plan_data, nutrition_plan, db=db, **extra
    )
    ctx["shared_view"] = True
    ctx["plan_owner_display_name"] = (
        owner.name.split()[0] if owner and owner.name else "A Runner"
    )
    ctx["share_token"] = share_token
    ctx["distance_display"] = plan_display_label(training_plan, space_before_km=True)

    return templates.TemplateResponse("plan_shared.html", ctx)


# ---------------------------------------------------------------------------
# Save / delete plan
# ---------------------------------------------------------------------------


@router.post("/api/plan/{plan_id}/save")
async def save_plan_to_account(
    plan_id: str,
    anonymous_user_id: Optional[str] = Cookie(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save/claim a plan to the current user's account."""
    training_plan = get_plan_or_404(plan_id, db, check_ownership=False)

    if training_plan.user_id == current_user.id:
        return {"message": "Plan already saved to your account", "plan_id": plan_id}

    plan_owner = SQLAlchemyUserRepository(db).get_by_id(training_plan.user_id)
    if plan_owner and (plan_owner.google_id or plan_owner.email):
        raise HTTPException(status_code=403, detail="This plan belongs to another user")

    if training_plan.user_id != anonymous_user_id:
        raise HTTPException(
            status_code=403, detail="This plan does not belong to your session"
        )

    training_plan.user_id = current_user.id
    db.commit()

    return {"message": "Plan saved to your account", "plan_id": plan_id}


@router.delete("/api/plan/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    plan_service: PlanService = Depends(get_plan_service),
):
    """Delete a training plan owned by the current user."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    plan_service.delete_plan(training_plan, db)
    return {"message": "Plan deleted successfully"}


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------


@router.get("/download-pdf/{plan_id}")
async def download_pdf(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    pdf_generator: PDFGenerator = Depends(get_pdf_generator),
) -> FileResponse:
    """Download training plan as PDF."""
    plan_generation_limiter.check(request)
    try:
        training_plan = get_plan_or_404(plan_id, db, current_user, anonymous_user_id)

        if not training_plan.plan_data:
            raise HTTPException(status_code=400, detail="No training plan data found")

        plan_data = training_plan.plan_data

        if not plan_data:
            raise HTTPException(status_code=400, detail="Empty training plan data")

        export_dto = PlanExportDTO.from_orm(training_plan, plan_data=plan_data)
        pdf_path = pdf_generator.generate_pdf(plan_data, export_dto)

        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=500, detail="PDF generation failed - file not created"
            )

        file_size = os.path.getsize(pdf_path)
        if file_size < 1000:
            raise HTTPException(
                status_code=500, detail="PDF generation failed - file too small"
            )

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"running_plan_{plan_id}.pdf",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("PDF generation error")
        raise HTTPException(
            status_code=500, detail="PDF generation failed. Please try again."
        )
