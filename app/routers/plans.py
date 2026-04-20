"""Plan generation, customization, viewing, and listing endpoints."""

import json
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.runner_profile import build_profile
from app.dependencies import (
    get_current_user,
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_plan_generator,
    get_plan_service,
)
from app.exceptions import (
    DatabaseException,
    InadequateBaseException,
    InsufficientTimeException,
    PlanGenerationException,
    RunCoachException,
    ValidationException,
    ZeroMileageUnsupportedException,
)
from app.models import TrainingPlan, User
from app.models.triathlon_plan import TriathlonPlan
from app.schemas import DISTANCE_NAMES, PlanRequest
from app.services.adaptation_service import AdaptationService
from app.services.hr_zone_service import HRZoneService
from app.services.performance_service import PerformanceService
from app.services.plan_helpers import error_response, get_plan_or_404, plan_view_context
from app.services.plan_service import PlanService
from app.template_helpers import create_templates
from app.utils import format_pace

# Sub-routers
from app.routers.plan_adjustments import router as adjustments_router
from app.routers.plan_sharing import router as sharing_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
router.include_router(adjustments_router)
router.include_router(sharing_router)
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
    goal_time: Optional[str] = Form(None),
    use_profile: Optional[str] = Form(None),
    plan_mode: Optional[str] = Form("distance"),
    goal_time_required: Optional[str] = Form(None),
    current_time: Optional[str] = Form(None),
    max_heart_rate: Optional[int] = Form(None),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_service: PlanService = Depends(get_plan_service),
) -> HTMLResponse:
    """Generate a personalized training plan."""
    if plan_mode == "time":
        return await _generate_time_goal_plan(
            request=request,
            current_km=current_km,
            target_distance=float(target_distance),
            weeks=weeks,
            runs_per_week=max_runs_per_week,
            goal_time=goal_time_required or "",
            current_time=current_time,
            max_heart_rate=max_heart_rate,
            current_user=current_user,
            db=db,
            plan_service=plan_service,
        )

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

    if not anonymous_user_id:
        anonymous_user_id = getattr(request.state, "anonymous_user_id", None)

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
            goal_time=goal_time or None,
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

    if current_user:
        existing = plan_service.find_duplicate(plan_request, current_user.id, db)
        if existing:
            logger.info(
                f"Returning existing plan {existing.id} for user {current_user.id}"
            )
            return RedirectResponse(url=f"/plan/{existing.id}", status_code=303)

    if current_user:
        if plan_service.has_reached_plan_limit(current_user.id, db):
            return error_response(
                request,
                current_user,
                "You've reached the maximum of 3 active training plans. "
                "Please delete or complete an existing plan before creating a new one.",
                "plan_limit",
            )

    try:
        user = plan_service.get_or_create_anonymous_user(
            current_user, anonymous_user_id, db
        )
        runner_profile = None
        if use_profile == "on" and current_user:
            rp = build_profile(current_user.id, db)
            if rp.has_sufficient_data:
                runner_profile = rp.to_dict()

        training_plan, plan_data = plan_service.create_plan(
            plan_request, user, db, plan_generator, nutrition_engine,
            profile=runner_profile,
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

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


async def _generate_time_goal_plan(
    request: Request,
    current_km: float,
    target_distance: float,
    weeks: int,
    runs_per_week: int,
    goal_time: str,
    current_time: Optional[str],
    max_heart_rate: Optional[int],
    current_user: Optional[User],
    db: Session,
    plan_service: PlanService,
):
    """Dispatch performance (time-goal) plan creation from the unified form."""
    from app.routers.performance import _parse_time_to_pace

    if not current_user:
        return error_response(
            request, None,
            "Time-goal plans require a logged-in account so we can track your progress.",
            "auth_required",
        )

    if plan_service.has_reached_plan_limit(current_user.id, db):
        return error_response(
            request, current_user,
            "You've reached the maximum of 3 active training plans. "
            "Please delete or complete an existing plan before creating a new one.",
            "plan_limit",
        )

    try:
        goal_pace = _parse_time_to_pace(goal_time, target_distance)
        current_pace = None
        if current_time:
            current_pace = _parse_time_to_pace(current_time, target_distance)

        service = PerformanceService(db)
        training_plan, _ = service.create_performance_plan(
            user=current_user,
            target_distance=target_distance,
            goal_pace=goal_pace,
            weeks=weeks,
            current_pace=current_pace,
            current_weekly_km=current_km if current_km > 0 else None,
            goal_time=goal_time,
            current_time=current_time,
            runs_per_week=runs_per_week,
            auto_calculate=current_km == 0,
            max_heart_rate=max_heart_rate,
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

    except RunCoachException as e:
        return error_response(request, current_user, e.user_message, "validation",
                              e.suggestion if hasattr(e, "suggestion") else None)
    except ValueError as e:
        return error_response(request, current_user, str(e), "validation")
    except Exception as e:
        logger.exception("Time-goal plan generation failed")
        return error_response(
            request, current_user,
            "An unexpected error occurred while generating your plan. Please try again.",
            "general",
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

        plan_service.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

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

        # Performance plans: add training zones + progress data
        if training_plan.plan_type == "performance":
            try:
                perf_service = PerformanceService(db)
                from app.core.generators.performance_plan_generator import PerformancePlanGenerator
                gen = PerformancePlanGenerator()
                zones = gen.calculate_training_zones(
                    training_plan.goal_pace, training_plan.max_heart_rate
                )
                for zone_data in zones.values():
                    zone_data["pace_formatted"] = format_pace(zone_data["pace"])
                    if "pace_range" in zone_data:
                        pr = zone_data["pace_range"]
                        zone_data["pace_range_formatted"] = (
                            f"{format_pace(pr[0])} - {format_pace(pr[1])}"
                        )
                extra["training_zones"] = zones
                extra["today_workout"] = perf_service.get_todays_workout(training_plan)
                extra["perf_progress_data"] = perf_service.get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Performance context enrichment failed: {e}")

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

            if plan.start_date:
                sd = plan.start_date
                start_d = sd.date() if isinstance(sd, datetime) else sd
                delta_days = (today - start_d).days
                current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
                if current_wk > plan.weeks_duration:
                    plan.status_label = "Completed"
                elif current_wk >= 1:
                    plan.status_label = f"Week {current_wk} of {plan.weeks_duration}"
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
                "plan_count": sum(1 for p in plans if p.status_label != "Completed"),
                "max_plans": 3,
                "triathlon_plans": triathlon_plans,
            },
        )
    except Exception as e:
        logger.error(f"Error listing plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while listing plans")
