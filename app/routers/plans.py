"""Plan generation and management endpoints."""

import json
import logging
import os
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.export.pdf_generator import PDFGenerator
from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.runner_profile import build_profile
from app.dependencies import (
    get_current_user,
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_pdf_generator,
    get_plan_generator,
    get_plan_service,
    verify_plan_ownership,
)
from app.exceptions import (
    DatabaseException,
    InadequateBaseException,
    InsufficientTimeException,
    PlanGenerationException,
    ValidationException,
    ZeroMileageUnsupportedException,
)
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.models.triathlon_plan import TriathlonPlan
from app.services.plan_helpers import error_response, get_plan_or_404, plan_view_context
from app.schemas import DISTANCE_NAMES, PlanRequest, get_mileage_warning
from app.services.adaptation_service import AdaptationService
from app.services.gap_analysis_service import GapAnalysisService
from app.services.hr_zone_service import HRZoneService
from app.services.plan_service import PlanService
from app.services.readiness_service import ReadinessService
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


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
    terrain: Optional[str] = Form(None),
    body_weight_kg: float = Form(70.0),
    recent_race_distance_km: Optional[float] = Form(None),
    recent_race_time: Optional[str] = Form(None),
    use_profile: Optional[str] = Form(None),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_service: PlanService = Depends(get_plan_service),
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
            terrain=terrain if float(target_distance) == 30.0 else None,
            body_weight_kg=body_weight_kg,
            recent_race_distance_km=recent_race_distance_km or None,
            recent_race_time=recent_race_time or None,
        )
    except InsufficientTimeException as e:
        return error_response(request, current_user, e.user_message, "insufficient_time", e.suggestion)
    except InadequateBaseException as e:
        return error_response(request, current_user, e.user_message, "inadequate_base", e.suggestion)
    except ZeroMileageUnsupportedException as e:
        return error_response(request, current_user, e.user_message, "zero_mileage_unsupported", e.suggestion)
    except ValidationException as e:
        return error_response(request, current_user, e.user_message, "validation")
    except Exception as e:
        return error_response(request, current_user, f"Invalid input: {str(e)}", "general")

    # --- Duplicate detection (check before plan limit so duplicates always pass through) ---
    if current_user:
        existing = plan_service.find_duplicate(plan_request, current_user.id, db)
        if existing:
            logger.info(
                f"Returning existing plan {existing.id} for user {current_user.id}"
            )
            plan_data = json.loads(existing.plan_data)
            plan_data = plan_service.enrich_plan_data_with_ids(
                plan_data, existing.id, db
            )
            extra = plan_service.get_plan_view_data(existing, current_user, db)
            ctx = plan_view_context(
                request,
                current_user,
                existing,
                plan_data,
                plan_service.nutrition_for_template(existing.nutrition_plan_data),
                **extra,
            )
            warning = get_mileage_warning(plan_request.target_distance, plan_request.current_km)
            if warning:
                ctx["warning"] = warning
            return templates.TemplateResponse("plan.html", ctx)

    # --- 3-plan limit ---
    if current_user:
        if plan_service.has_reached_plan_limit(current_user.id, db):
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
        user = plan_service.get_or_create_anonymous_user(
            current_user, anonymous_user_id, db
        )
        # Build runner profile if toggle is on and user is authenticated
        runner_profile = None
        if use_profile == "on" and current_user:
            rp = build_profile(current_user.id, db)
            if rp.has_sufficient_data:
                runner_profile = rp.to_dict()

        training_plan, plan_data = plan_service.create_plan(
            plan_request, user, db, plan_generator, nutrition_engine,
            profile=runner_profile,
        )
        plan_data = plan_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        extra = plan_service.get_plan_view_data(training_plan, current_user, db)
        ctx = plan_view_context(
            request,
            current_user,
            training_plan,
            plan_data,
            plan_service.nutrition_for_template(training_plan.nutrition_plan_data),
            **extra,
        )
        if warning_message:
            ctx["warning"] = warning_message

        template_response = templates.TemplateResponse("plan.html", ctx)

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
    plan_service: PlanService = Depends(get_plan_service),
) -> HTMLResponse:
    """Handle plan customization with simple interface."""
    training_plan = None
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        plan_data = plan_service.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )
        plan_data = plan_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        nutrition_plan = plan_service.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        extra = plan_service.get_plan_view_data(training_plan, current_user, db)
        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan,
            **extra,
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error customizing plan")
        return templates.TemplateResponse(
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": json.loads(training_plan.plan_data) if training_plan and training_plan.plan_data else [],
                "plan_id": plan_id,
                "nutrition_plan": (
                    plan_service.nutrition_for_template(training_plan.nutrition_plan_data)
                    if training_plan and training_plan.nutrition_plan_data
                    else {}
                ),
                "progress_data": None,
                "error": "An error occurred while customizing the plan.",
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
    plan_service: PlanService = Depends(get_plan_service),
) -> HTMLResponse:
    """View an existing training plan."""
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        # Auto-map any unmapped Strava runs and re-evaluate alerts
        if current_user and training_plan.start_date:
            try:
                adaptation_service = AdaptationService()
                adaptation_service.map_runs_to_plan(
                    plan_id, current_user.id, db
                )
                adaptation_service.check_alerts(
                    plan_id, current_user.id, db
                )
            except Exception as e:
                logger.warning(f"Auto-map/alert on view failed: {e}")

        plan_data = json.loads(training_plan.plan_data)
        plan_data = plan_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        # Generate nutrition plan for existing plans if not present
        if not training_plan.nutrition_plan_data:
            nutrition_plan_raw = nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                training_plan.target_distance_km,
            )
            training_plan.nutrition_plan_data = json.dumps(nutrition_plan_raw)
            db.commit()

        nutrition_plan = plan_service.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        # Retroactive HR zone computation for existing plans
        if not training_plan.hr_zones_data:
            try:
                user = current_user or db.query(User).filter(
                    User.id == training_plan.user_id
                ).first()
                if user:
                    zones = HRZoneService.compute_and_store_zones(
                        training_plan, user, db
                    )
                    HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
                    training_plan.plan_data = json.dumps(plan_data)
                    db.commit()
            except Exception as e:
                logger.warning(f"Retroactive HR zone computation failed: {e}")

        extra = plan_service.get_plan_view_data(training_plan, current_user, db)

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan, **extra
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while generating the plan")


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
        plans = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.user_id == current_user.id)
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )

        adaptation_service = AdaptationService()
        today = date.today()
        for plan in plans:
            td = plan.target_distance_km
            plan.target_distance_display = DISTANCE_NAMES.get(td, f"{td}km")

            # Compute plan status for display
            if plan.start_date:
                sd = plan.start_date
                start_d = sd.date() if isinstance(sd, datetime) else sd
                delta_days = (today - start_d).days
                current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
                if current_wk > plan.weeks_duration:
                    plan.status_label = "Completed"
                elif current_wk >= 1:
                    plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
                    # Evaluate recalibration alerts for active plans
                    try:
                        adaptation_service.check_alerts(
                            plan.id, current_user.id, db
                        )
                    except Exception:
                        logger.warning(f"Alert check failed for plan {plan.id}", exc_info=True)
                else:
                    plan.status_label = f"Starts {start_d.strftime('%b')} {start_d.day}"
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
        logger.error(f"Error listing plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while listing plans")


# ---------------------------------------------------------------------------
# Performance & adaptation API endpoints
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/readiness")
async def get_plan_readiness(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get race readiness assessment for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    readiness = ReadinessService.compute_readiness(
        training_plan, current_user.id, db
    )

    if readiness is None:
        return {"available": False, "reason": "Set a start date and log some runs first."}

    return {"available": True, **readiness}


@router.get("/api/plan/{plan_id}/gaps")
async def get_plan_gaps(
    plan_id: str,
    weekly: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get gap analysis report for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    if weekly:
        data = GapAnalysisService.analyze_gaps_weekly(
            training_plan, current_user.id, db
        )
        if data is None:
            return {"available": False, "reason": "Set a start date and log some runs first."}
        return {"available": True, "weeks": data}

    gaps = GapAnalysisService.analyze_gaps(
        training_plan, current_user.id, db
    )

    if gaps is None:
        return {"available": False, "reason": "Set a start date and log some runs first."}

    return {"available": True, **gaps}


@router.post("/api/plan/{plan_id}/adjust")
async def adjust_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adjust future plan weeks based on recent performance data."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.adjust_plan(plan_id, current_user.id, db)


@router.get("/api/plan/{plan_id}/suggestions")
async def get_plan_suggestions(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get per-week adaptive suggestions for upcoming plan weeks."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    suggestions = adaptation_service.get_weekly_suggestions(
        plan_id, current_user.id, db
    )
    return {"suggestions": suggestions}


class RecalibrateRequest(BaseModel):
    strategy: str  # "time_off" | "ahead"


@router.post("/api/plan/{plan_id}/recalibrate")
async def recalibrate_plan(
    plan_id: str,
    body: RecalibrateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recalibrate remaining plan weeks based on user-chosen strategy."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.recalibrate(
        plan_id, current_user.id, body.strategy, db
    )


@router.post("/api/plan/{plan_id}/dismiss-alert")
async def dismiss_alert(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss an active adaptation alert."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )
    training_plan.adaptation_alert = None
    db.commit()
    return {"ok": True}


class WeekOverrideRequest(BaseModel):
    action: str  # "skip_bump" | "reduce_30" | "bump" | "ease_deficit" | "extend_long_run" | "reset_week"


@router.post("/api/plan/{plan_id}/week/{week_number}/override")
async def override_plan_week(
    plan_id: str,
    week_number: int,
    body: WeekOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a per-week override to the plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    if body.action == "skip_bump":
        # Preserve baseline distances for this week (undo any adjustment)
        weekly_plan = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )
        if weekly_plan:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                .all()
            )
            for wo in workouts:
                if wo.baseline_distance_km:
                    wo.distance_km = wo.baseline_distance_km
            # Sync plan_data
            for wo_data in week_data.get("daily_workouts", []):
                for db_wo in workouts:
                    if db_wo.day_of_week == wo_data.get("day"):
                        wo_data["distance"] = db_wo.distance_km
            week_data["total_km"] = round(
                sum(wo.distance_km for wo in workouts if wo.distance_km), 1
            )

    elif body.action == "reduce_30":
        # Reduce this week and the next by 30%
        factor = 0.7
        for target_week in range(week_number, min(week_number + 2, len(plan_data) + 1)):
            tw_data = next((w for w in plan_data if w.get("week") == target_week), None)
            if not tw_data:
                continue
            weekly_plan = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan_id,
                    WeeklyPlan.week_number == target_week,
                )
                .first()
            )
            if weekly_plan:
                workouts = (
                    db.query(DailyWorkout)
                    .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                    .all()
                )
                for wo in workouts:
                    if wo.distance_km:
                        wo.distance_km = round(wo.distance_km * factor, 1)
                for wo_data in tw_data.get("daily_workouts", []):
                    if "distance" in wo_data:
                        wo_data["distance"] = round(wo_data["distance"] * factor, 1)
                tw_data["total_km"] = round(
                    sum(wo.distance_km for wo in workouts if wo.distance_km), 1
                )
    elif body.action == "bump":
        # Bump distances for this week (user exceeding targets)
        multiplier = training_plan.adjustment_multiplier or 1.08
        weekly_plan = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )
        if weekly_plan:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                .all()
            )
            for wo in workouts:
                if wo.distance_km:
                    if not wo.baseline_distance_km:
                        wo.baseline_distance_km = wo.distance_km
                    wo.distance_km = round(wo.distance_km * multiplier, 1)
            for wo_data in week_data.get("daily_workouts", []):
                if "distance" in wo_data:
                    wo_data["distance"] = round(wo_data["distance"] * multiplier, 1)
            week_data["total_km"] = round(
                sum(wo.distance_km for wo in workouts if wo.distance_km), 1
            )

    elif body.action == "ease_deficit":
        # Reduce distances by 15% (user below target)
        factor = 0.85
        weekly_plan = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )
        if weekly_plan:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                .all()
            )
            for wo in workouts:
                if wo.distance_km:
                    if not wo.baseline_distance_km:
                        wo.baseline_distance_km = wo.distance_km
                    wo.distance_km = round(wo.distance_km * factor, 1)
            for wo_data in week_data.get("daily_workouts", []):
                if "distance" in wo_data:
                    wo_data["distance"] = round(wo_data["distance"] * factor, 1)
            week_data["total_km"] = round(
                sum(wo.distance_km for wo in workouts if wo.distance_km), 1
            )

    elif body.action == "extend_long_run":
        # Extend the long run by 2km
        weekly_plan = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )
        if weekly_plan:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                .all()
            )
            long_wo = next(
                (wo for wo in workouts if wo.workout_type == "long"), None
            )
            if long_wo and long_wo.distance_km:
                if not long_wo.baseline_distance_km:
                    long_wo.baseline_distance_km = long_wo.distance_km
                long_wo.distance_km = round(long_wo.distance_km + 2, 1)
            for wo_data in week_data.get("daily_workouts", []):
                if wo_data.get("type") == "long" and "distance" in wo_data:
                    wo_data["distance"] = round(wo_data["distance"] + 2, 1)
                    break
            week_data["total_km"] = round(
                sum(wo.distance_km for wo in workouts if wo.distance_km), 1
            )

    elif body.action == "reset_week":
        # Restore all workouts to their baseline distances and clear baselines
        weekly_plan = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )
        if weekly_plan:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
                .all()
            )
            for wo in workouts:
                if wo.baseline_distance_km is not None:
                    wo.distance_km = wo.baseline_distance_km
                    wo.baseline_distance_km = None
            for wo_data in week_data.get("daily_workouts", []):
                for db_wo in workouts:
                    if db_wo.day_of_week == wo_data.get("day"):
                        wo_data["distance"] = db_wo.distance_km
            week_data["total_km"] = round(
                sum(wo.distance_km for wo in workouts if wo.distance_km), 1
            )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    training_plan.plan_data = json.dumps(plan_data)
    db.commit()

    return {"ok": True, "action": body.action, "week": week_number}


class SwapDaysRequest(BaseModel):
    source_day: int
    target_day: int


@router.post("/api/plan/{plan_id}/week/{week_number}/swap-days")
async def swap_plan_days(
    plan_id: str,
    week_number: int,
    body: SwapDaysRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Swap two workouts within the same week."""
    from app.services.plan_adjustments import swap_days

    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    if body.source_day == body.target_day:
        return {"ok": True}

    plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    plan_data = swap_days(plan_data, week_number, body.source_day, body.target_day)

    # Sync day_of_week in DailyWorkout DB records
    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .first()
    )
    if weekly_plan:
        db_workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
            .all()
        )
        src_db = next(
            (wo for wo in db_workouts if wo.day_of_week == body.source_day), None
        )
        tgt_db = next(
            (wo for wo in db_workouts if wo.day_of_week == body.target_day), None
        )
        if src_db and tgt_db:
            src_db.day_of_week, tgt_db.day_of_week = (
                tgt_db.day_of_week,
                src_db.day_of_week,
            )

    training_plan.plan_data = json.dumps(plan_data)
    db.commit()

    return {"ok": True}


@router.post("/api/plan/{plan_id}/reset-adjustment")
async def reset_plan_adjustment(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset plan adjustment, restoring original baseline distances."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.reset_adjustment(plan_id, current_user.id, db)


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
# Share plan
# ---------------------------------------------------------------------------


@router.post("/api/plan/{plan_id}/share")
async def toggle_share_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate or revoke a share link for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    if training_plan.share_token:
        # Revoke: clear the token
        training_plan.share_token = None
        db.commit()
        return {"shared": False, "share_token": None, "share_url": None}

    # Generate a new token
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
    training_plan = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.share_token == share_token)
        .first()
    )
    if not training_plan:
        raise HTTPException(status_code=404, detail="Shared plan not found")

    plan_data = json.loads(training_plan.plan_data)
    plan_data = plan_service.enrich_plan_data_with_ids(
        plan_data, training_plan.id, db
    )

    nutrition_plan = plan_service.nutrition_for_template(
        training_plan.nutrition_plan_data
    )

    # Get the plan owner for display
    owner = db.query(User).filter(User.id == training_plan.user_id).first()

    # Build view data using the plan owner so progress_data is populated
    extra = plan_service.get_plan_view_data(training_plan, owner, db)

    ctx = plan_view_context(
        request, current_user, training_plan, plan_data, nutrition_plan, **extra
    )
    ctx["shared_view"] = True
    ctx["plan_owner"] = owner
    ctx["share_token"] = share_token
    td = training_plan.target_distance_km
    ctx["distance_display"] = DISTANCE_NAMES.get(td, f"{td} km")

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

    # Verify the requesting session actually owns this anonymous plan
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
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    plan_service.delete_plan(training_plan, db)

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
