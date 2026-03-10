"""Plan generation and management endpoints."""

import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.nutrition_engine import NutritionEngine
from app.core.pdf_generator import PDFGenerator
from app.core.plan_generator import TrainingPlanGenerator
from app.dependencies import (
    get_current_user,
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_pdf_generator,
    get_plan_generator,
    verify_plan_ownership,
)
from app.exceptions import (
    DatabaseException,
    InadequateBaseException,
    InsufficientTimeException,
    PlanGenerationException,
    ValidationException,
)
from app.models import TrainingPlan, User
from app.models.triathlon_plan import TriathlonPlan
from app.routers.plan_helpers import error_response, get_plan_or_404, plan_view_context
from app.schemas import DISTANCE_NAMES, PlanRequest, get_mileage_warning, parse_target_distance
from app.services.adaptation_service import AdaptationService
from app.services.plan_service import PlanService, user_plans_cache
from app.utils import format_pace

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["format_pace"] = format_pace


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------


@router.post("/generate-plan", response_class=HTMLResponse)
async def generate_plan(
    request: Request,
    response: Response,
    current_km: float = Form(...),
    target_distance: str = Form(...),
    weeks: int = Form(...),
    max_runs_per_week: int = Form(4),
    body_weight_kg: float = Form(70.0),
    recent_race_distance_km: Optional[float] = Form(None),
    recent_race_time: Optional[str] = Form(None),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
) -> HTMLResponse:
    """Generate a personalized training plan."""
    logger.info(
        f"Generate plan - current_user: {current_user.id if current_user else 'None'}"
    )
    logger.info(
        f"Generate plan - anonymous_user_id cookie: "
        f"{request.cookies.get('anonymous_user_id', 'NO COOKIE')}"
    )
    logger.info(
        f"Generate plan - has_access_token: "
        f"{bool(request.cookies.get('access_token'))}"
    )

    # --- Validate input via Pydantic ---
    try:
        plan_request = PlanRequest(
            current_km=current_km,
            target_distance=float(target_distance),
            weeks=weeks,
            max_runs_per_week=max_runs_per_week,
            body_weight_kg=body_weight_kg,
            recent_race_distance_km=recent_race_distance_km or None,
            recent_race_time=recent_race_time or None,
        )
    except InsufficientTimeException as e:
        return error_response(request, current_user, e.user_message, "insufficient_time", e.suggestion)
    except InadequateBaseException as e:
        return error_response(request, current_user, e.user_message, "inadequate_base", e.suggestion)
    except ValidationException as e:
        return error_response(request, current_user, e.user_message, "validation")
    except Exception as e:
        return error_response(request, current_user, f"Invalid input: {str(e)}", "general")

    # --- Duplicate detection (check before plan limit so duplicates always pass through) ---
    if current_user:
        existing = PlanService.find_duplicate(plan_request, current_user.id, db)
        if existing:
            logger.info(
                f"Returning existing plan {existing.id} for user {current_user.id}"
            )
            plan_data = json.loads(existing.plan_data)
            ctx = plan_view_context(
                request,
                current_user,
                existing,
                plan_data,
                PlanService.nutrition_for_template(existing.nutrition_plan_data),
            )
            warning = get_mileage_warning(plan_request.target_distance, plan_request.current_km)
            if warning:
                ctx["warning"] = warning
            return templates.TemplateResponse("plan.html", ctx)

    # --- 3-plan limit ---
    if current_user:
        plan_count = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.user_id == current_user.id)
            .count()
        )
        if plan_count >= 3:
            return error_response(
                request,
                current_user,
                "You've reached the maximum of 3 training plans. "
                "Please delete an existing plan before creating a new one.",
                "plan_limit",
            )

    warning_message = get_mileage_warning(
        plan_request.target_distance, plan_request.current_km
    )

    try:
        user = PlanService.get_or_create_anonymous_user(
            current_user, anonymous_user_id, db
        )
        training_plan, plan_data = PlanService.create_plan(
            plan_request, user, db, plan_generator, nutrition_engine
        )

        ctx = plan_view_context(
            request,
            current_user,
            training_plan,
            plan_data,
            PlanService.nutrition_for_template(training_plan.nutrition_plan_data),
        )
        if warning_message:
            ctx["warning"] = warning_message

        template_response = templates.TemplateResponse("plan.html", ctx)

        if not current_user:
            template_response.set_cookie(
                key="anonymous_user_id",
                value=user.id,
                max_age=30 * 24 * 60 * 60,
                httponly=True,
                samesite="lax",
                secure=not settings.debug,
            )

        return template_response

    except PlanGenerationException as e:
        db.rollback()
        return error_response(request, current_user, e.user_message, "plan_generation")
    except DatabaseException:
        db.rollback()
        return error_response(
            request, current_user, "Database error occurred. Please try again.", "database"
        )
    except Exception as e:
        logger.exception("Plan generation failed")
        db.rollback()
        return error_response(
            request, current_user, f"An unexpected error occurred: {str(e)}", "general"
        )


# ---------------------------------------------------------------------------
# Plan customization
# ---------------------------------------------------------------------------


@router.post("/customize-plan", response_class=HTMLResponse)
async def customize_plan(
    request: Request,
    plan_id: str = Form(...),
    week_number: int = Form(...),
    adjustment_type: str = Form(...),
    adjustment_value: str = Form(...),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    """Handle plan customization with simple interface."""
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        plan_data = PlanService.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )

        nutrition_plan = PlanService.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": json.loads(training_plan.plan_data) if "training_plan" in dir() else [],
                "plan_id": plan_id,
                "nutrition_plan": (
                    PlanService.nutrition_for_template(training_plan.nutrition_plan_data)
                    if "training_plan" in dir() and training_plan.nutrition_plan_data
                    else {}
                ),
                "progress_data": None,
                "error": f"Error customizing plan: {str(e)}",
            },
        )


# ---------------------------------------------------------------------------
# View plan
# ---------------------------------------------------------------------------


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
async def view_plan(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
) -> HTMLResponse:
    """View an existing training plan."""
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        plan_data = json.loads(training_plan.plan_data)

        # Generate nutrition plan for existing plans if not present
        if not training_plan.nutrition_plan_data:
            nutrition_plan_raw = nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                parse_target_distance(training_plan.target_distance),
            )
            training_plan.nutrition_plan_data = json.dumps(nutrition_plan_raw)
            db.commit()

        nutrition_plan = PlanService.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        extra = PlanService.get_plan_view_data(training_plan, current_user, db)

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan, **extra
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# My plans
# ---------------------------------------------------------------------------


@router.get("/my-plans")
async def list_my_plans(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """List all training plans for current user."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    try:
        cache_key = f"plans_{current_user.id}"

        if cache_key in user_plans_cache:
            plans = user_plans_cache[cache_key]
            logger.info(f"Using cached plans for user {current_user.id}")
        else:
            plans = (
                db.query(TrainingPlan)
                .filter(TrainingPlan.user_id == current_user.id)
                .order_by(TrainingPlan.created_at.desc())
                .all()
            )
            user_plans_cache[cache_key] = plans
            logger.info(f"Cached plans for user {current_user.id}")

        today = date.today()
        for plan in plans:
            td = parse_target_distance(plan.target_distance)
            plan.target_distance_display = DISTANCE_NAMES.get(td, f"{td}km")

            # Compute plan status for display
            if plan.start_date:
                sd = plan.start_date
                start_d = sd.date() if hasattr(sd, "date") and callable(sd.date) else sd
                delta_days = (today - start_d).days
                current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
                if current_wk > plan.weeks_duration:
                    plan.status_label = "Completed"
                elif current_wk >= 1:
                    plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
                else:
                    plan.status_label = f"Starts {start_d.strftime('%b %-d')}"
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
                "plan_count": len(plans),
                "max_plans": 3,
                "triathlon_plans": triathlon_plans,
            },
        )
    except Exception as e:
        logger.error(f"Error listing plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Performance & adaptation API endpoints
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/performance")
async def get_plan_performance(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get performance analysis for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    adaptation_service = AdaptationService()
    analysis = adaptation_service.analyze_performance(plan_id, db)
    should_adapt, reason = adaptation_service.should_adapt_plan(plan_id, db)

    return {
        **analysis,
        "should_adapt": should_adapt,
        "adaptation_reason": reason,
    }


@router.post("/api/plan/{plan_id}/adapt")
async def adapt_plan(
    plan_id: str,
    current_week: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adapt future weeks of a plan based on performance."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.adapt_future_weeks(plan_id, db, current_week)


@router.post("/api/plan/{plan_id}/adapt-from-strava")
async def adapt_plan_from_strava(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adapt future weeks of a plan based on Strava fitness metrics."""
    if not current_user.strava_athlete_id:
        raise HTTPException(status_code=400, detail="Strava not connected")

    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.adapt_plan_from_fitness(
        plan_id, current_user.id, db
    )


@router.post("/api/plan/{plan_id}/map-runs")
async def map_runs_to_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Map unlinked runs to plan workouts by date proximity."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    result = adaptation_service.map_runs_to_plan(plan_id, current_user.id, db)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/plan/{plan_id}/map-runs/preview")
async def preview_map_runs(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview which runs would be mapped to plan workouts (dry run)."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    result = adaptation_service.map_runs_to_plan(
        plan_id, current_user.id, db, dry_run=True
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/plan/{plan_id}/recalibrate")
async def recalibrate_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recalibrate future plan weeks based on actual adherence."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    result = adaptation_service.recalibrate_plan(plan_id, current_user.id, db)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/api/plan/{plan_id}/adapt-from-strava")
async def reset_strava_adaptation(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset a Strava adaptation, restoring original planned distances."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    result = adaptation_service.reset_strava_adaptation(plan_id, current_user.id, db)
    if not result.get("reset"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Reset failed"))
    return result


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
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )
    training_plan.start_date = datetime.combine(body.start_date, datetime.min.time())
    db.commit()
    return {"ok": True, "start_date": body.start_date.isoformat()}


# ---------------------------------------------------------------------------
# Save / delete plan
# ---------------------------------------------------------------------------


@router.post("/api/plan/{plan_id}/save")
async def save_plan_to_account(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save/claim a plan to the current user's account."""
    training_plan = get_plan_or_404(
        plan_id, db, check_ownership=False
    )

    if training_plan.user_id == current_user.id:
        return {"message": "Plan already saved to your account", "plan_id": plan_id}

    plan_owner = db.query(User).filter(User.id == training_plan.user_id).first()
    if plan_owner and (plan_owner.google_id or plan_owner.email):
        raise HTTPException(
            status_code=403, detail="This plan belongs to another user"
        )

    training_plan.user_id = current_user.id
    db.commit()

    return {"message": "Plan saved to your account", "plan_id": plan_id}


@router.delete("/api/plan/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a training plan owned by the current user."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    PlanService.delete_plan(training_plan, db)

    return {"message": "Plan deleted successfully"}


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------


@router.get("/download-pdf/{plan_id}")
async def download_pdf(
    plan_id: str,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    pdf_generator: PDFGenerator = Depends(get_pdf_generator),
) -> FileResponse:
    """Download training plan as PDF."""
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        if not training_plan.plan_data:
            raise HTTPException(
                status_code=400, detail="No training plan data found"
            )

        try:
            plan_data = json.loads(training_plan.plan_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid training plan data format"
            )

        if not plan_data:
            raise HTTPException(
                status_code=400, detail="Empty training plan data"
            )

        pdf_path = pdf_generator.generate_pdf(plan_data, training_plan)

        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=500,
                detail="PDF generation failed - file not created",
            )

        file_size = os.path.getsize(pdf_path)
        if file_size < 1000:
            raise HTTPException(
                status_code=500,
                detail="PDF generation failed - file too small",
            )

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"running_plan_{plan_id}.pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF generation error")
        raise HTTPException(
            status_code=500, detail=f"PDF generation failed: {str(e)}"
        )
