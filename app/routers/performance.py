"""Performance training endpoints."""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_optional_user,
    get_performance_plan_generator,
)
from app.models import User
from app.schemas import PerformancePlanRequest, DISTANCE_NAMES
from app.services.performance_service import PerformanceService
from app.exceptions import RunCoachException, InadequateBaseException
from app.core.performance_plan_generator import PerformancePlanGenerator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance"])
templates = Jinja2Templates(directory="app/templates")


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


def _format_time(total_minutes: float) -> str:
    """Format decimal minutes to HH:MM:SS or MM:SS."""
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)
    seconds = int((total_minutes % 1) * 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


@router.get("/performance-training", response_class=HTMLResponse)
async def performance_training_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Render the performance training input page."""
    # Auto-calculate fitness if user is logged in
    fitness_data = None
    hr_data = None
    if current_user:
        try:
            service = PerformanceService(db)
            # Default to 10K for initial calculation
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id,
                target_distance=10.0
            )

            # Auto-calculate max heart rate (use a reasonable default pace for initial estimate)
            default_goal_pace = 5.5  # Average 10K pace
            if fitness_data and fitness_data.get('has_sufficient_data'):
                default_goal_pace = fitness_data.get('avg_pace', 5.5)

            hr_data = service.calculate_max_heart_rate(
                user_id=current_user.id,
                goal_pace=default_goal_pace
            )
        except Exception as e:
            logger.warning(f"Could not auto-calculate fitness: {e}")

    return templates.TemplateResponse(
        "performance_training.html",
        {
            "request": request,
            "user": current_user,
            "fitness_data": fitness_data,
            "hr_data": hr_data,
            "distance_names": DISTANCE_NAMES,
        }
    )


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
):
    """Generate a performance training plan."""
    # Check if user is logged in (required for performance training)
    if not current_user:
        return templates.TemplateResponse(
            "performance_training.html",
            {
                "request": request,
                "user": None,
                "fitness_data": None,
                "hr_data": None,
                "distance_names": DISTANCE_NAMES,
                "error": "You must be logged in to create a performance training plan.",
                "error_type": "auth_required",
            },
        )

    # Convert auto_calculate string to boolean
    auto_calculate_bool = auto_calculate == "true" if auto_calculate else False

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
            url=f"/performance-plan/{training_plan.id}",
            status_code=303
        )

    except RunCoachException as e:
        logger.warning(f"Validation error: {e.user_message}")
        # Get fitness and HR data for the form
        fitness_data = None
        hr_data = None
        try:
            service = PerformanceService(db)
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id,
                target_distance=target_distance
            )
            hr_data = service.calculate_max_heart_rate(
                user_id=current_user.id,
                goal_pace=goal_pace
            )
        except Exception:
            pass

        # Determine error type for better styling
        error_type = "validation"
        if isinstance(e, InadequateBaseException):
            error_type = "inadequate_base"
        elif "unrealistic" in e.user_message.lower():
            error_type = "unrealistic_goal"

        return templates.TemplateResponse(
            "performance_training.html",
            {
                "request": request,
                "user": current_user,
                "fitness_data": fitness_data,
                "hr_data": hr_data,
                "distance_names": DISTANCE_NAMES,
                "error": e.user_message,
                "error_type": error_type,
                "suggestion": e.suggestion if hasattr(e, 'suggestion') else None,
            },
        )
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        # Get fitness and HR data for the form
        fitness_data = None
        hr_data = None
        try:
            service = PerformanceService(db)
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id,
                target_distance=target_distance
            )
            hr_data = service.calculate_max_heart_rate(
                user_id=current_user.id,
                goal_pace=goal_pace
            )
        except Exception:
            pass

        return templates.TemplateResponse(
            "performance_training.html",
            {
                "request": request,
                "user": current_user,
                "fitness_data": fitness_data,
                "hr_data": hr_data,
                "distance_names": DISTANCE_NAMES,
                "error": str(e),
                "error_type": "validation",
            },
        )
    except Exception as e:
        logger.error(f"Error generating performance plan: {e}", exc_info=True)
        return templates.TemplateResponse(
            "performance_training.html",
            {
                "request": request,
                "user": current_user,
                "fitness_data": None,
                "hr_data": None,
                "distance_names": DISTANCE_NAMES,
                "error": "An unexpected error occurred while generating your plan. Please try again.",
                "error_type": "general",
            },
        )


@router.get("/performance-plan/{plan_id}", response_class=HTMLResponse)
async def view_performance_plan(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Display a performance training plan."""
    try:
        service = PerformanceService(db)
        result = service.get_plan_with_data(plan_id)

        if not result:
            return templates.TemplateResponse(
                "performance_training.html",
                {
                    "request": request,
                    "user": current_user,
                    "fitness_data": None,
                    "distance_names": DISTANCE_NAMES,
                    "error": "Training plan not found.",
                    "error_type": "not_found",
                },
                status_code=404,
            )

        training_plan, plan_data = result

        # Add formatted versions for zones
        for zone_name, zone_data in plan_data['training_zones'].items():
            pace_min = zone_data['pace']
            zone_data['pace_formatted'] = f"{int(pace_min)}:{int((pace_min % 1) * 60):02d}/km"

            if 'pace_range' in zone_data:
                pace_range = zone_data['pace_range']
                zone_data['pace_range_formatted'] = (
                    f"{int(pace_range[0])}:{int((pace_range[0] % 1) * 60):02d} - "
                    f"{int(pace_range[1])}:{int((pace_range[1] % 1) * 60):02d}/km"
                )

        # Ensure all workouts have formatted pace (generator should already add this, but double-check)
        for week in plan_data['weekly_plans']:
            for workout in week.get('daily_workouts', []):
                if 'target_pace' in workout and 'target_pace_formatted' not in workout:
                    pace_min = workout['target_pace']
                    workout['target_pace_formatted'] = f"{int(pace_min)}:{int((pace_min % 1) * 60):02d}/km"

        # Parse and transform nutrition plan
        nutrition_plan = None
        if training_plan.nutrition_plan_data:
            try:
                raw_nutrition = json.loads(training_plan.nutrition_plan_data)

                # Transform to performance template format
                if isinstance(raw_nutrition, dict):
                    targets = raw_nutrition.get('nutrition_targets', {})
                    meal_options = raw_nutrition.get('meal_options', {})

                    nutrition_plan = {
                        'daily_calories': targets.get('calories', 0),
                        'protein_grams': targets.get('protein', 0),
                        'carbs_grams': targets.get('carbs', 0),
                        'fat_grams': targets.get('fat', 0),
                        'meals': meal_options  # Already in the right format
                    }
            except Exception as e:
                logger.warning(f"Failed to parse nutrition plan: {e}")
                # Nutrition plan is optional, continue without it
                nutrition_plan = None

        logger.info(f"Rendering performance plan {plan_id} with {len(plan_data['weekly_plans'])} weeks")

        return templates.TemplateResponse(
            "performance_plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": training_plan,
                "plan_data": plan_data,
                "nutrition_plan": nutrition_plan,
                "distance_name": DISTANCE_NAMES.get(
                    float(training_plan.target_distance),
                    f"{training_plan.target_distance}km"
                ),
            }
        )

    except Exception as e:
        logger.error(f"Error displaying performance plan: {e}", exc_info=True)
        return templates.TemplateResponse(
            "performance_training.html",
            {
                "request": request,
                "user": current_user,
                "fitness_data": None,
                "distance_names": DISTANCE_NAMES,
                "error": f"Failed to load training plan: {str(e)}",
                "error_type": "general",
            },
            status_code=500,
        )
