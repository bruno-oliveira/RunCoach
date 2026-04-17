"""Performance training endpoints.

Legacy endpoints redirect to the unified plan system.
The /api/performance/* endpoints remain for direct API callers.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_optional_user, get_plan_service
from app.exceptions import RunCoachException, InadequateBaseException
from app.models import User
from app.schemas import PerformancePlanRequest, DISTANCE_NAMES
from app.services.performance_service import PerformanceService
from app.services.plan_helpers import error_response
from app.services.plan_service import PlanService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance"])


def _parse_time_to_pace(time_str: str, distance_km: float) -> float:
    """
    Convert time string (HH:MM:SS or MM:SS) to pace in min/km.

    Args:
        time_str: Time string like "50:00" or "1:50:00"
        distance_km: Distance in km

    Returns:
        Pace in min/km
    """
    parts = time_str.strip().split(':')
    if len(parts) == 2:
        # MM:SS format
        minutes = int(parts[0])
        seconds = int(parts[1])
        total_minutes = minutes + seconds / 60
    elif len(parts) == 3:
        # HH:MM:SS format
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        total_minutes = hours * 60 + minutes + seconds / 60
    else:
        raise ValueError("Time must be in MM:SS or HH:MM:SS format")

    pace = total_minutes / distance_km
    return pace


def _perf_error_response(
    request: Request,
    user: User,
    error: str,
    error_type: str = "general",
    *,
    fitness_data=None,
    hr_data=None,
    suggestion: Optional[str] = None,
):
    """Build an error TemplateResponse using the unified index.html form."""
    return error_response(request, user, error, error_type, suggestion)


@router.get("/performance-training")
async def performance_training_page():
    """Redirect to unified home with time-goal mode."""
    return RedirectResponse(url="/?mode=time", status_code=302)


@router.get("/api/performance/calculate-fitness")
async def calculate_fitness(
    distance: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Calculate current fitness metrics from run logs."""
    try:
        service = PerformanceService(db)
        fitness = service.calculate_fitness_from_runs(
            user_id=current_user.id,
            target_distance=distance
        )
        return fitness
    except Exception as e:
        logger.error(f"Error calculating fitness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/performance/generate-plan", response_class=HTMLResponse)
async def generate_performance_plan(
    request: Request,
    target_distance: float = Form(...),
    goal_time: str = Form(...),
    weeks: int = Form(...),
    current_time: Optional[str] = Form(None),
    current_pace: Optional[float] = Form(None),
    current_weekly_km: Optional[float] = Form(None),
    auto_calculate: Optional[str] = Form(None),
    runs_per_week: int = Form(5),
    max_heart_rate: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_service: PlanService = Depends(get_plan_service),
):
    """Generate a performance training plan (API endpoint, kept for direct callers)."""
    if not current_user:
        return error_response(
            request, None,
            "You must be logged in to create a performance training plan.",
            "auth_required",
        )

    # Convert auto_calculate string to boolean
    auto_calculate_bool = auto_calculate == "true" if auto_calculate else False

    # Check 3-plan limit
    if plan_service.has_reached_plan_limit(current_user.id, db):
        fitness_data = None
        try:
            fitness_data = PerformanceService(db).calculate_fitness_from_runs(
                user_id=current_user.id, target_distance=target_distance
            )
        except Exception as e:
            logger.warning(f"Could not load fitness data for plan-limit error page: {e}")
        return _perf_error_response(
            request, current_user,
            "You've reached the maximum of 3 training plans. "
            "Please delete an existing plan before creating a new one.",
            "plan_limit",
            fitness_data=fitness_data,
        )

    goal_pace = None
    try:
        # Parse goal time to pace
        goal_pace = _parse_time_to_pace(goal_time, target_distance)

        # Parse current time to pace if provided
        if current_time and not current_pace:
            current_pace = _parse_time_to_pace(current_time, target_distance)

        # Create request schema for validation
        request_data = PerformancePlanRequest(
            target_distance=target_distance,
            goal_pace=goal_pace,
            goal_time=goal_time,
            current_pace=current_pace,
            current_time=current_time,
            weeks=weeks,
            current_weekly_km=current_weekly_km,
            auto_calculate=auto_calculate_bool,
            runs_per_week=runs_per_week,
            max_heart_rate=max_heart_rate,
        )

        # Create the plan
        service = PerformanceService(db)
        training_plan, plan_data = service.create_performance_plan(
            user=current_user,
            target_distance=request_data.target_distance,
            goal_pace=request_data.goal_pace,
            weeks=request_data.weeks,
            current_pace=request_data.current_pace,
            current_weekly_km=request_data.current_weekly_km,
            goal_time=request_data.goal_time,
            current_time=request_data.current_time,
            runs_per_week=request_data.runs_per_week,
            auto_calculate=request_data.auto_calculate,
            max_heart_rate=request_data.max_heart_rate,
        )

        # Redirect to plan display
        return RedirectResponse(
            url=f"/plan/{training_plan.id}",
            status_code=303
        )

    except RunCoachException as e:
        logger.warning(f"Validation error: {e.user_message}")
        fitness_data = None
        hr_data = None
        try:
            service = PerformanceService(db)
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id, target_distance=target_distance
            )
            hr_data = service.calculate_max_heart_rate(
                user_id=current_user.id, goal_pace=goal_pace
            )
        except Exception as ctx_err:
            logger.warning(f"Could not load context for validation error page: {ctx_err}")

        error_type = "validation"
        if isinstance(e, InadequateBaseException):
            error_type = "inadequate_base"
        elif "unrealistic" in e.user_message.lower():
            error_type = "unrealistic_goal"

        return _perf_error_response(
            request, current_user, e.user_message, error_type,
            fitness_data=fitness_data, hr_data=hr_data,
            suggestion=e.suggestion if hasattr(e, 'suggestion') else None,
        )
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        fitness_data = None
        hr_data = None
        try:
            service = PerformanceService(db)
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id, target_distance=target_distance
            )
            hr_data = service.calculate_max_heart_rate(
                user_id=current_user.id, goal_pace=goal_pace
            )
        except Exception as ctx_err:
            logger.warning(f"Could not load context for ValueError page: {ctx_err}")
        return _perf_error_response(
            request, current_user, str(e), "validation",
            fitness_data=fitness_data, hr_data=hr_data,
        )
    except Exception as e:
        logger.error(f"Error generating performance plan: {e}", exc_info=True)
        return _perf_error_response(
            request, current_user,
            "An unexpected error occurred while generating your plan. Please try again.",
        )


@router.get("/performance-plan/{plan_id}")
async def view_performance_plan(plan_id: str):
    """Redirect to unified plan view."""
    return RedirectResponse(url=f"/plan/{plan_id}", status_code=302)
