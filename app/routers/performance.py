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
from app.exceptions import RunCoachException
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
    if current_user:
        try:
            service = PerformanceService(db)
            # Default to 10K for initial calculation
            fitness_data = service.calculate_fitness_from_runs(
                user_id=current_user.id,
                target_distance=10.0
            )
        except Exception as e:
            logger.warning(f"Could not auto-calculate fitness: {e}")

    return templates.TemplateResponse(
        "performance_training.html",
        {
            "request": request,
            "user": current_user,
            "fitness_data": fitness_data,
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


@router.post("/api/performance/generate-plan")
async def generate_performance_plan(
    target_distance: float = Form(...),
    goal_time: str = Form(...),
    weeks: int = Form(...),
    current_time: Optional[str] = Form(None),
    current_pace: Optional[float] = Form(None),
    current_weekly_km: Optional[float] = Form(None),
    auto_calculate: bool = Form(True),
    runs_per_week: int = Form(5),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a performance training plan."""
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
            auto_calculate=auto_calculate,
            runs_per_week=runs_per_week,
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
        )

        # Redirect to plan display
        return RedirectResponse(
            url=f"/performance-plan/{training_plan.id}",
            status_code=303
        )

    except RunCoachException as e:
        logger.warning(f"Validation error: {e.user_message}")
        raise HTTPException(status_code=400, detail={
            "message": e.user_message,
            "suggestion": e.suggestion
        })
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating performance plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate plan")


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
            raise HTTPException(status_code=404, detail="Plan not found")

        training_plan, plan_data = result

        # Add formatted versions
        for zone_name, zone_data in plan_data['training_zones'].items():
            pace_min = zone_data['pace']
            zone_data['pace_formatted'] = f"{int(pace_min)}:{int((pace_min % 1) * 60):02d}/km"

            if 'pace_range' in zone_data:
                pace_range = zone_data['pace_range']
                zone_data['pace_range_formatted'] = (
                    f"{int(pace_range[0])}:{int((pace_range[0] % 1) * 60):02d} - "
                    f"{int(pace_range[1])}:{int((pace_range[1] % 1) * 60):02d}/km"
                )

        # Parse nutrition plan
        nutrition_plan = None
        if training_plan.nutrition_plan_data:
            nutrition_plan = json.loads(training_plan.nutrition_plan_data)

        return templates.TemplateResponse(
            "performance_plan.html",
            {
                "request": request,
                "user": current_user,
                "plan": training_plan,
                "plan_data": plan_data,
                "nutrition_plan": nutrition_plan,
                "distance_name": DISTANCE_NAMES.get(
                    float(training_plan.target_distance),
                    f"{training_plan.target_distance}km"
                ),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error displaying performance plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load plan")
