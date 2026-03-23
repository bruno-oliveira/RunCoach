"""Router for run logging and performance tracking."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.adaptive_plan_generator import AdaptivePlanGenerator
from app.core.quality_scorer import calculate_quality_score
from app.core.vdot_calculator import VDOTCalculator
from app.dependencies import get_db, get_current_user
from app.models import RunLog, User, DailyWorkout, WeeklyPlan, TrainingPlan
from app.schemas import (
    RunLogCreate,
    RunLogListResponse,
    RunLogResponse,
    RunLogUpdate,
    AdaptivePlanRequest,
    WeeklyPlanResponse,
)

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/runs", tags=["runs"])
adaptive_router = APIRouter(prefix="/api/adaptive", tags=["adaptive-plans"])
adaptive_generator = AdaptivePlanGenerator()


def _run_to_response(run: RunLog) -> RunLogResponse:
    """Convert a RunLog model instance to a RunLogResponse schema."""
    return RunLogResponse(
        id=run.id,
        user_id=run.user_id,
        date=run.date,
        distance_km=run.distance_km,
        duration_minutes=run.duration_minutes,
        avg_pace_min_km=round(run.avg_pace_min_km, 2) if run.avg_pace_min_km else None,
        avg_heart_rate=run.avg_heart_rate,
        max_heart_rate=run.max_heart_rate,
        avg_cadence=run.avg_cadence,
        elevation_gain_m=run.elevation_gain_m,
        notes=run.notes,
        workout_type=run.workout_type,
        perceived_effort=run.perceived_effort,
        effort_quality_score=round(run.effort_quality_score, 1) if run.effort_quality_score else None,
        quality_label=run.quality_label,
        vdot=run.vdot,
        created_at=run.created_at,
    )


@runs_router.post("", response_model=RunLogResponse, status_code=status.HTTP_201_CREATED)
async def create_run_log(
    run_log: RunLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new run log entry.

    Allows users to track their runs with detailed metrics including:
    - Distance and duration
    - Heart rate data (average and maximum)
    - Cadence and elevation
    - Workout type and perceived effort
    - Notes
    """
    try:
        # Calculate average pace (min/km)
        avg_pace_min_km = run_log.duration_minutes / run_log.distance_km

        new_run = RunLog(
            user_id=current_user.id,
            training_plan_id=run_log.training_plan_id,
            daily_workout_id=run_log.daily_workout_id,
            date=run_log.date or datetime.now(timezone.utc).replace(tzinfo=None),
            distance_km=run_log.distance_km,
            duration_minutes=run_log.duration_minutes,
            avg_pace_min_km=avg_pace_min_km,
            avg_heart_rate=run_log.avg_heart_rate,
            max_heart_rate=run_log.max_heart_rate,
            avg_cadence=run_log.avg_cadence,
            elevation_gain_m=run_log.elevation_gain_m,
            notes=run_log.notes,
            workout_type=run_log.workout_type,
            perceived_effort=run_log.perceived_effort,
        )

        # Calculate effort quality score if we have enough data
        if run_log.daily_workout_id and run_log.perceived_effort:
            planned_workout = db.query(DailyWorkout).filter(
                DailyWorkout.id == run_log.daily_workout_id
            ).first()
            if planned_workout:
                workout_type = planned_workout.workout_type or run_log.workout_type or "easy"
                score, label = calculate_quality_score(
                    actual_effort=run_log.perceived_effort,
                    actual_pace_min_km=avg_pace_min_km,
                    workout_type=workout_type,
                    planned_pace_min_km=planned_workout.planned_pace_min_km if hasattr(planned_workout, "planned_pace_min_km") else None,
                )
                new_run.effort_quality_score = score
                new_run.quality_label = label

        db.add(new_run)
        db.commit()

        # Auto-calculate VDOT for race-type runs
        race_predictions = None
        if run_log.workout_type == "race":
            vdot = VDOTCalculator.calculate_vdot(
                run_log.distance_km, int(run_log.duration_minutes * 60)
            )
            if vdot:
                new_run.vdot = vdot
                db.commit()
                db.refresh(new_run)
                # Generate predictions for the toast
                race_predictions = VDOTCalculator.predict_times(vdot)

        # Generate coaching feedback (non-fatal)
        try:
            from app.services.feedback_service import FeedbackService
            FeedbackService.generate_and_store(new_run, db)
        except Exception as e:
            logger.warning(f"Feedback generation failed for run {new_run.id}: {e}")

        logger.info(f"Run log created for user {current_user.id}: {run_log.distance_km}km in {run_log.duration_minutes}min")

        response_data = _run_to_response(new_run)
        if race_predictions:
            response_data.predictions = race_predictions
        return response_data
    except Exception as e:
        logger.error(f"Error creating run log: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create run log",
        )


@runs_router.get("", response_model=RunLogListResponse)
async def get_run_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    workout_type: Optional[str] = Query(None, description="Filter by workout type"),
    start_date: Optional[datetime] = Query(None, description="Filter runs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter runs before this date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get paginated list of user's run logs with optional filtering.

    Supports filtering by:
    - Workout type (easy, tempo, interval, long, hill)
    - Date range (start_date and end_date)
    """
    try:
        query = db.query(RunLog).filter(RunLog.user_id == current_user.id)

        # Apply filters
        if workout_type:
            query = query.filter(RunLog.workout_type == workout_type)
        if start_date:
            query = query.filter(RunLog.date >= start_date)
        if end_date:
            query = query.filter(RunLog.date <= end_date)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        run_logs = query.order_by(RunLog.date.desc()).offset(offset).limit(page_size).all()

        return RunLogListResponse(
            runs=[_run_to_response(run) for run in run_logs],
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error fetching run logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch run logs",
        )


@runs_router.get("/{run_id}", response_model=RunLogResponse)
async def get_run_log(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific run log by ID."""
    run = (
        db.query(RunLog)
        .filter(RunLog.id == run_id, RunLog.user_id == current_user.id)
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    return _run_to_response(run)


@runs_router.put("/{run_id}", response_model=RunLogResponse)
async def update_run_log(
    run_id: str,
    run_update: RunLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing run log."""
    run = (
        db.query(RunLog)
        .filter(RunLog.id == run_id, RunLog.user_id == current_user.id)
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    # Update fields
    update_data = run_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(run, field, value)

    # Recalculate pace if distance or duration changed
    if "distance_km" in update_data or "duration_minutes" in update_data:
        run.avg_pace_min_km = run.duration_minutes / run.distance_km

    db.commit()
    db.refresh(run)

    logger.info(f"Run log {run_id} updated for user {current_user.id}")

    return _run_to_response(run)


@runs_router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run_log(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a run log."""
    run = (
        db.query(RunLog)
        .filter(RunLog.id == run_id, RunLog.user_id == current_user.id)
        .first()
    )

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    db.delete(run)
    db.commit()

    logger.info(f"Run log {run_id} deleted for user {current_user.id}")


@runs_router.get("/predictions")
async def get_race_predictions(
    target_distance: Optional[float] = Query(None, description="Target race distance in km"),
    goal_time: Optional[str] = Query(None, description="Goal time in HH:MM:SS or MM:SS"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get race predictions based on user's recent race VDOT.

    Returns predictions for all standard distances unless target_distance is specified.
    When goal_time is provided, performs gap analysis.
    """
    from app.services.race_predictor_service import RacePredictorService

    predictions_data = RacePredictorService.get_predictions_for_user(current_user.id, db)

    if not predictions_data.get("has_sufficient_data"):
        return {
            "current_vdot": None,
            "vdot_trend": "stable",
            "predictions": {},
            "last_race": None,
            "has_sufficient_data": False,
            "message": "Log a race-type run to get predictions",
        }

    result = {
        "current_vdot": predictions_data["current_vdot"],
        "vdot_trend": predictions_data["vdot_trend"],
        "predictions": {},
        "last_race": predictions_data["last_race"],
        "has_sufficient_data": True,
    }

    if target_distance:
        result["target_distance"] = target_distance
        if goal_time:
            goal_seconds = VDOTCalculator.parse_time_to_seconds(goal_time)
            if goal_seconds:
                gap_analysis = RacePredictorService.analyze_fitness_gap(
                    predictions_data["current_vdot"],
                    target_distance,
                    goal_seconds,
                    db,
                )
                result.update(gap_analysis)
            else:
                result["message"] = "Invalid goal_time format"
        else:
            current_vdot = predictions_data["current_vdot"]
            predicted = VDOTCalculator.predict_time_for_distance(current_vdot, target_distance)
            range_data = VDOTCalculator.get_confidence_range(current_vdot, target_distance)
            result["predicted_time"] = VDOTCalculator.format_duration(predicted) if predicted else None
            result["range"] = {
                "fast": VDOTCalculator.format_duration(range_data["fast"]),
                "slow": VDOTCalculator.format_duration(range_data["slow"]),
            }
            result["message"] = "Log a goal time to see gap analysis"
    else:
        for name, pred in predictions_data["predictions"].items():
            result["predictions"][name] = {
                "distance_km": pred["distance_km"],
                "seconds": pred["seconds"],
                "formatted": pred["formatted"],
                "range": pred.get("range", {}),
            }

    return result


@runs_router.get("/{run_id}/feedback")
async def get_run_feedback(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get coaching feedback for a specific run."""
    from app.services.feedback_service import FeedbackService

    # Verify run ownership
    run = (
        db.query(RunLog)
        .filter(RunLog.id == run_id, RunLog.user_id == current_user.id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    feedback = FeedbackService.get_feedback_for_run(run_id, db)
    if not feedback:
        return {"message": "No feedback available for this run"}

    return {
        "id": feedback.id,
        "run_log_id": feedback.run_log_id,
        "pace_feedback": feedback.pace_feedback,
        "hr_zone_feedback": feedback.hr_zone_feedback,
        "effort_feedback": feedback.effort_feedback,
        "volume_feedback": feedback.volume_feedback,
        "pattern_feedback": feedback.pattern_feedback,
        "overall_sentiment": feedback.overall_sentiment,
        "created_at": feedback.created_at,
    }


@runs_router.get("/feedback/plan/{plan_id}")
async def get_plan_feedback(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all coaching feedback for runs logged against a plan."""
    from app.services.feedback_service import FeedbackService

    feedbacks = FeedbackService.get_feedback_for_plan(
        plan_id, current_user.id, db
    )
    return [
        {
            "id": fb.id,
            "run_log_id": fb.run_log_id,
            "pace_feedback": fb.pace_feedback,
            "hr_zone_feedback": fb.hr_zone_feedback,
            "effort_feedback": fb.effort_feedback,
            "volume_feedback": fb.volume_feedback,
            "pattern_feedback": fb.pattern_feedback,
            "overall_sentiment": fb.overall_sentiment,
            "created_at": fb.created_at,
        }
        for fb in feedbacks
    ]


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



