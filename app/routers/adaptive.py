"""Router for adaptive training plan generation and fitness metrics."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.adaptive_plan_generator import AdaptivePlanGenerator
from app.dependencies import get_db, get_current_user
from app.models import User
from app.schemas import AdaptivePlanRequest, WeeklyPlanResponse

logger = logging.getLogger(__name__)

adaptive_router = APIRouter(prefix="/api/adaptive", tags=["adaptive-plans"])
adaptive_generator = AdaptivePlanGenerator()


@adaptive_router.get("/metrics")
async def get_fitness_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user's current fitness metrics based on run logs.

    Returns:
        - Average weekly distance
        - Current pace
        - Average heart rate
        - Improvement trend
        - Fitness score (0-100)
        - Preferred workout types
    """
    metrics = adaptive_generator.calculate_current_fitness_metrics(current_user.id, db)
    return metrics


@adaptive_router.get("/suggestions")
async def get_training_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get personalized training suggestions based on recent performance.

    Returns prioritized recommendations for:
    - Volume adjustments
    - Speed work
    - Recovery
    - Consistency
    - Balance
    """
    suggestions = adaptive_generator.get_training_suggestions(current_user.id, db)
    return {"suggestions": suggestions}


@adaptive_router.get("/performance-gaps")
async def get_performance_gaps(
    target_distance: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze gaps between current performance and race requirements.

    Provides:
        - Mileage gap
        - Target race pace
        - Key weaknesses
        - Specific recommendations
    """
    gaps = adaptive_generator.analyze_performance_gaps(
        current_user.id, target_distance, db
    )
    return gaps


@adaptive_router.post("/generate-plan", response_model=List[WeeklyPlanResponse])
async def generate_adaptive_plan(
    request: AdaptivePlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate an adaptive training plan based on user's performance data.

    The plan is personalized based on:
        - Current weekly mileage from run logs
        - Average pace and improvement trend
        - Fitness score
        - Preferred workout types
        - Heart rate data
    """
    try:
        plan = adaptive_generator.generate_adaptive_plan(
            user_id=current_user.id,
            target_distance=request.target_distance,
            weeks=request.weeks,
            max_runs_per_week=request.max_runs_per_week,
            db=db,
        )

        logger.info(
            f"Adaptive plan generated for user {current_user.id}: "
            f"{request.weeks} weeks for {request.target_distance}km"
        )

        # Convert to response format
        return [
            WeeklyPlanResponse(
                week=week["week"],
                total_km=week["total_km"],
                workout_distribution=week["workout_distribution"],
                daily_workouts=[
                    {
                        "day": workout["day"],
                        "type": workout["type"],
                        "distance": workout["distance"],
                        "intensity": workout["intensity"],
                        "notes": workout["notes"],
                    }
                    for workout in week["daily_workouts"]
                ],
                strength_training=week["strength_training"],
                training_tips=week["training_tips"],
            )
            for week in plan
        ]
    except Exception as e:
        logger.error(f"Error generating adaptive plan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate adaptive plan",
        )
