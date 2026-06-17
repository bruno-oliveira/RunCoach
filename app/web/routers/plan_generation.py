"""Plan generation and customization endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application.plan_view_service import PlanViewService
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_helpers import error_response, get_plan_or_404
from app.contexts.plan.plan_service import PlanService
from app.contexts.runner.fitness.fitness_service import FitnessService
from app.contexts.runner.fitness.performance_service import PerformanceService
from app.contexts.runner.profile.profile_builder import build_profile
from app.dependencies import (
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_plan_generator,
    get_plan_service,
    get_plan_view_service,
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
from app.infrastructure.config import settings
from app.models import User
from app.rate_limit import plan_generation_limiter
from app.schemas import FitnessPlanRequest, PlanRequest
from app.template_helpers import create_templates
from app.utils import parse_time_to_pace

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


_VALUE_ERROR_PREFIX = "Value error, "

# Kept in sync with the configured limit so the copy never drifts from the
# enforced ``settings.max_plans_per_user``.
_PLAN_LIMIT_MESSAGE = (
    f"You've reached the maximum of {settings.max_plans_per_user} active "
    "training plans. Please delete or complete an existing plan before "
    "creating a new one."
)


def _extract_validation_message(exc: ValidationError) -> Optional[str]:
    """Pull the first human-readable message out of a Pydantic ValidationError.

    Our schema validators raise plain ValueError with user-facing text;
    Pydantic V2 wraps those into ValidationError and prefixes the message
    with "Value error, ". Strip the prefix so the original text reaches the UI.
    """
    for err in exc.errors():
        msg = err.get("msg") or ""
        if msg.startswith(_VALUE_ERROR_PREFIX):
            return msg[len(_VALUE_ERROR_PREFIX) :]
        if msg:
            return msg
    return None


def _is_truthy(value: Optional[str]) -> bool:
    """Interpret an HTML form/checkbox value as a boolean."""
    return (value or "").lower() in ("on", "true", "1", "yes")


def _plan_request_from_form(
    request: Request,
    current_user: Optional[User],
    *,
    current_km: float,
    target_distance: str,
    weeks: int,
    max_runs_per_week: int,
    terrain: Optional[str],
    is_trail: Optional[str],
    target_elevation_gain_m: Optional[str],
    training_terrain: Optional[str],
    trail_distance_km: Optional[str],
    intensive_weekend: Optional[str],
    body_weight_kg: float,
    recent_race_distance_km: Optional[str],
    recent_race_time: Optional[str],
    goal_time: Optional[str],
) -> "PlanRequest | Response":
    """Coerce distance-mode form fields into a validated ``PlanRequest``.

    Returns an :class:`error_response` (a ``Response``) on any parse or
    validation failure so the caller can short-circuit; otherwise the built
    ``PlanRequest``.
    """
    race_dist = float(recent_race_distance_km) if recent_race_distance_km else None
    is_trail_flag = _is_truthy(is_trail)
    intensive_weekend_flag = _is_truthy(intensive_weekend)

    if is_trail_flag and target_distance == "trail":
        if not trail_distance_km:
            return error_response(
                request,
                current_user,
                "Please enter the trail/ultra distance in kilometres.",
                "validation",
            )
        try:
            target_distance_f = float(trail_distance_km)
        except ValueError:
            return error_response(
                request,
                current_user,
                "Trail/ultra distance must be a number in kilometres.",
                "validation",
            )
    else:
        try:
            target_distance_f = float(target_distance)
        except ValueError:
            return error_response(
                request,
                current_user,
                "Race goal distance is invalid.",
                "validation",
            )

    elevation_f: Optional[float] = None
    if target_elevation_gain_m not in (None, ""):
        try:
            elevation_f = float(target_elevation_gain_m)
        except ValueError:
            return error_response(
                request,
                current_user,
                "Elevation gain must be a number in metres.",
                "validation",
            )

    # Trail-only fields linger in the form when the user switches back to a
    # road preset (the inputs are hidden but not disabled). Drop them so the
    # schema doesn't validate stale values for non-trail plans.
    if not is_trail_flag:
        elevation_f = None
        training_terrain = None
        terrain = None
        intensive_weekend_flag = False

    try:
        return PlanRequest(
            current_km=current_km,
            target_distance=target_distance_f,
            weeks=weeks,
            max_runs_per_week=max_runs_per_week,
            is_trail=is_trail_flag,
            target_elevation_gain_m=elevation_f,
            training_terrain=training_terrain,
            terrain=terrain,
            intensive_weekend_enabled=intensive_weekend_flag,
            body_weight_kg=body_weight_kg,
            recent_race_distance_km=race_dist,
            recent_race_time=recent_race_time or None,
            goal_time=goal_time or None,
        )
    except InsufficientTimeException as e:
        return error_response(
            request, current_user, e.user_message, "insufficient_time", e.suggestion
        )
    except InadequateBaseException as e:
        return error_response(
            request, current_user, e.user_message, "inadequate_base", e.suggestion
        )
    except ZeroMileageUnsupportedException as e:
        return error_response(
            request,
            current_user,
            e.user_message,
            "zero_mileage_unsupported",
            e.suggestion,
        )
    except ValidationException as e:
        return error_response(request, current_user, e.user_message, "validation")
    except ValidationError as e:
        message = (
            _extract_validation_message(e) or "Please check your values and try again."
        )
        return error_response(request, current_user, message, "validation")
    except Exception:
        logger.exception("Plan request validation failed")
        return error_response(
            request,
            current_user,
            "Invalid input. Please check your values and try again.",
            "general",
        )


@router.post("/generate-plan", response_class=HTMLResponse)
async def generate_plan(
    request: Request,
    response: Response,
    current_km: float = Form(...),
    target_distance: str = Form(...),
    weeks: int = Form(...),
    max_runs_per_week: int = Form(4),
    terrain: Optional[str] = Form(None),
    is_trail: Optional[str] = Form(None),
    target_elevation_gain_m: Optional[str] = Form(None),
    training_terrain: Optional[str] = Form(None),
    trail_distance_km: Optional[str] = Form(None),
    intensive_weekend: Optional[str] = Form(None),
    body_weight_kg: float = Form(70.0),
    recent_race_distance_km: Optional[str] = Form(None),
    recent_race_time: Optional[str] = Form(None),
    goal_time: Optional[str] = Form(None),
    use_profile: Optional[str] = Form(None),
    plan_mode: Optional[str] = Form("distance"),
    goal_time_required: Optional[str] = Form(None),
    current_time: Optional[str] = Form(None),
    max_heart_rate: Optional[str] = Form(None),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_service: PlanService = Depends(get_plan_service),
) -> Response:
    """Generate a personalized training plan."""
    plan_generation_limiter.check(request)
    hr_max = int(max_heart_rate) if max_heart_rate else None

    if plan_mode == "time":
        return await _generate_time_goal_plan(
            request=request,
            current_km=current_km,
            target_distance=float(target_distance),
            weeks=weeks,
            runs_per_week=max_runs_per_week,
            goal_time=goal_time_required or "",
            current_time=current_time,
            max_heart_rate=hr_max,
            current_user=current_user,
            db=db,
            plan_service=plan_service,
        )

    logger.info(
        "Generate plan - current_user=%s, anon_cookie=%s, has_access_token=%s",
        current_user.id if current_user else "None",
        request.cookies.get("anonymous_user_id", "NO COOKIE"),
        bool(request.cookies.get("access_token")),
    )

    if not anonymous_user_id:
        anonymous_user_id = getattr(request.state, "anonymous_user_id", None)

    plan_request = _plan_request_from_form(
        request,
        current_user,
        current_km=current_km,
        target_distance=target_distance,
        weeks=weeks,
        max_runs_per_week=max_runs_per_week,
        terrain=terrain,
        is_trail=is_trail,
        target_elevation_gain_m=target_elevation_gain_m,
        training_terrain=training_terrain,
        trail_distance_km=trail_distance_km,
        intensive_weekend=intensive_weekend,
        body_weight_kg=body_weight_kg,
        recent_race_distance_km=recent_race_distance_km,
        recent_race_time=recent_race_time,
        goal_time=goal_time,
    )
    if isinstance(plan_request, Response):
        return plan_request

    if current_user:
        existing = plan_service.find_duplicate(plan_request, str(current_user.id), db)
        if existing:
            logger.info(
                "Returning existing plan %s for user %s",
                existing.id,
                current_user.id,
            )
            return RedirectResponse(url=f"/plan/{existing.id}", status_code=303)

    if current_user:
        if plan_service.has_reached_plan_limit(str(current_user.id), db):
            return error_response(
                request,
                current_user,
                _PLAN_LIMIT_MESSAGE,
                "plan_limit",
            )

    try:
        user = plan_service.get_or_create_anonymous_user(
            current_user, anonymous_user_id, db
        )
        runner_profile = None
        if use_profile == "on" and current_user:
            rp = build_profile(str(current_user.id), db)
            if rp.has_sufficient_data:
                runner_profile = rp.to_dict()

        training_plan, plan_data = plan_service.create_plan(
            plan_request,
            user,
            db,
            plan_generator,
            nutrition_engine,
            profile=runner_profile,
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

    except PlanGenerationException as e:
        db.rollback()
        return error_response(request, current_user, e.user_message, "plan_generation")
    except DatabaseException:
        db.rollback()
        return error_response(
            request,
            current_user,
            "Database error occurred. Please try again.",
            "database",
        )
    except Exception:
        logger.exception("Plan generation failed")
        db.rollback()
        return error_response(
            request,
            current_user,
            "An unexpected error occurred. Please try again.",
            "general",
        )


@router.post("/generate-fitness-plan", response_class=HTMLResponse)
def generate_fitness_plan(
    request: Request,
    response: Response,
    current_km: float = Form(...),
    weeks: int = Form(...),
    runs_per_week: int = Form(...),
    focus_area: str = Form("vo2max"),
    focus_distance: Optional[str] = Form(None),
    body_weight_kg: float = Form(70.0),
    max_heart_rate: Optional[str] = Form(None),
    recent_race_distance_km: Optional[str] = Form(None),
    recent_race_time: Optional[str] = Form(None),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_service: PlanService = Depends(get_plan_service),
) -> Response:
    """Generate a fitness-focused training plan."""
    plan_generation_limiter.check(request)
    race_dist = float(recent_race_distance_km) if recent_race_distance_km else None
    hr_max = int(max_heart_rate) if max_heart_rate else None
    focus_dist = float(focus_distance) if focus_distance else None

    if not anonymous_user_id:
        anonymous_user_id = getattr(request.state, "anonymous_user_id", None)

    try:
        plan_request = FitnessPlanRequest(
            current_km=current_km,
            weeks=weeks,
            runs_per_week=runs_per_week,
            focus_area=focus_area,
            focus_distance=focus_dist,
            body_weight_kg=body_weight_kg,
            max_heart_rate=hr_max,
            recent_race_distance_km=race_dist,
            recent_race_time=recent_race_time or None,
        )
    except ValidationException as e:
        return error_response(request, current_user, e.user_message, "validation")
    except ValidationError as e:
        message = (
            _extract_validation_message(e) or "Please check your values and try again."
        )
        return error_response(request, current_user, message, "validation")
    except Exception:
        logger.exception("Fitness plan request validation failed")
        return error_response(
            request,
            current_user,
            "Invalid input. Please check your values and try again.",
            "general",
        )

    if current_user:
        if plan_service.has_reached_plan_limit(str(current_user.id), db):
            return error_response(
                request,
                current_user,
                _PLAN_LIMIT_MESSAGE,
                "plan_limit",
            )

    try:
        user = plan_service.get_or_create_anonymous_user(
            current_user, anonymous_user_id, db
        )

        fitness_service = FitnessService(db)
        training_plan, plan_data = fitness_service.create_fitness_plan(
            user=user,
            plan_request=plan_request,
            nutrition_engine=nutrition_engine,
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

    except ValueError as e:
        return error_response(request, current_user, str(e), "validation")
    except DatabaseException:
        db.rollback()
        return error_response(
            request,
            current_user,
            "Database error occurred. Please try again.",
            "database",
        )
    except RunCoachException as e:
        db.rollback()
        return error_response(
            request,
            current_user,
            e.user_message,
            "validation",
            getattr(e, "suggestion", None),
        )
    except Exception:
        logger.exception("Fitness plan generation failed")
        db.rollback()
        return error_response(
            request,
            current_user,
            "An unexpected error occurred. Please try again.",
            "general",
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
    if not current_user:
        return error_response(
            request,
            None,
            "Time-goal plans require a logged-in account so we can track your progress.",
            "auth_required",
        )

    if plan_service.has_reached_plan_limit(str(current_user.id), db):
        return error_response(
            request,
            current_user,
            _PLAN_LIMIT_MESSAGE,
            "plan_limit",
        )

    try:
        goal_pace = parse_time_to_pace(goal_time, target_distance)
        current_pace = None
        if current_time:
            current_pace = parse_time_to_pace(current_time, target_distance)

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
        return error_response(
            request,
            current_user,
            e.user_message,
            "validation",
            getattr(e, "suggestion", None),
        )
    except ValueError as e:
        return error_response(request, current_user, str(e), "validation")
    except Exception:
        logger.exception("Time-goal plan generation failed")
        return error_response(
            request,
            current_user,
            "An unexpected error occurred while generating your plan. Please try again.",
            "general",
        )


@router.get("/assess-long-run")
def assess_long_run(
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs_per_week: int = 4,
    is_trail: bool = False,
    target_elevation_gain_m: Optional[float] = None,
    training_terrain: Optional[str] = None,
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
) -> Response:
    """Pre-submit estimate of whether the long run will reach race specificity.

    A pure calculator (no DB, no persistence): it generates the plan, measures
    the peak long run, and runs the *same* adequacy check the plan view shows,
    so the live form hint matches the banner the runner sees after generating.
    Any bad/edge input simply yields ``{"long_run_warning": null}`` (no hint)
    rather than an error — this is advisory, never blocking.
    """
    from fastapi.responses import JSONResponse

    from app.core.training.long_run_calculator import assess_long_run_adequacy
    from app.core.training.strength_plan import derive_experience_level

    try:
        if current_km <= 0 or target_distance <= 0 or weeks <= 0:
            return JSONResponse({"long_run_warning": None})

        trail_profile = None
        if is_trail:
            from app.core.training.trail_profile import classify_trail

            trail_profile = classify_trail(
                target_distance, target_elevation_gain_m or 0.0
            )

        plan_data = plan_generator.generate_plan(
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
            terrain=training_terrain,
            trail_profile=trail_profile,
        )

        peak_long_run = 0.0
        for week in plan_data:
            if week.get("is_recovery"):
                continue
            for workout in week.get("daily_workouts", []) or []:
                if workout.get("type") == "long":
                    peak_long_run = max(peak_long_run, workout.get("distance", 0) or 0)

        warning = assess_long_run_adequacy(
            peak_long_run,
            target_distance,
            experience_level=derive_experience_level(current_km),
            trail_profile=trail_profile,
            training_terrain=training_terrain,
            weeks=weeks,
        )
        return JSONResponse({"long_run_warning": warning})
    except Exception:
        logger.debug("assess-long-run estimate failed", exc_info=True)
        return JSONResponse({"long_run_warning": None})


@router.post("/customize-plan", response_class=HTMLResponse)
def customize_plan(
    request: Request,
    plan_id: str = Form(...),
    week_number: int = Form(...),
    adjustment_type: str = Form(...),
    adjustment_value: str = Form(...),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_service: PlanService = Depends(get_plan_service),
    plan_view_service: PlanViewService = Depends(get_plan_view_service),
) -> Response:
    """Handle plan customization with simple interface."""
    training_plan = None
    try:
        training_plan = get_plan_or_404(plan_id, db, current_user, anonymous_user_id)

        plan_service.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )

        return RedirectResponse(url=f"/plan/{training_plan.id}", status_code=303)

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error customizing plan")
        # getattr returns Any, side-stepping the SQLAlchemy Column[...] typing
        # while preserving the original truthiness checks at runtime.
        plan_data = getattr(training_plan, "plan_data", None) if training_plan else None
        nutrition_data = (
            getattr(training_plan, "nutrition_plan_data", None)
            if training_plan
            else None
        )
        return templates.TemplateResponse(
            request,
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": plan_data if plan_data else [],
                "plan_id": plan_id,
                "nutrition_plan": (
                    plan_view_service.nutrition_for_template(nutrition_data)
                    if nutrition_data
                    else {}
                ),
                "progress_data": None,
                "error": "An error occurred while customizing the plan.",
            },
        )
