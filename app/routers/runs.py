"""Router for run logging and performance tracking."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.training.quality_scorer import calculate_quality_score
from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import get_db, get_current_user
from app.models import RunLog, User, DailyWorkout, TrainingPlan, WeeklyPlan
from app.schemas import (
    RunLogCreate,
    RunLogListResponse,
    RunLogResponse,
    RunLogUpdate,
)
from app.services.feedback_service import FeedbackService
from app.services.race_predictor_service import RacePredictorService

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/runs", tags=["runs"])


def _enrich_vdot_and_prediction(
    new_run: RunLog, distance_km: float, duration_minutes: float, user_id: str, db: Session
) -> None:
    """Calculate VDOT and snapshot pre-run prediction onto the run."""
    if distance_km >= 2.0 and duration_minutes > 0:
        vdot = VDOTCalculator.calculate_vdot(distance_km, int(duration_minutes * 60))
        if vdot:
            new_run.vdot = vdot

    if distance_km >= 2.0:
        try:
            pre_race_vdot = RacePredictorService.get_best_recent_vdot(user_id, weeks=12, db=db)
            if pre_race_vdot:
                predicted_seconds = VDOTCalculator.predict_time_for_distance(pre_race_vdot, distance_km)
                if predicted_seconds:
                    new_run.predicted_time_seconds = float(predicted_seconds)
        except Exception as e:
            logger.warning(f"Failed to snapshot prediction for run: {e}")


def _build_race_comparison(run: RunLog, duration_minutes: float) -> Optional[dict]:
    """Build predicted vs actual comparison dict if prediction data is available."""
    if not run.predicted_time_seconds:
        return None
    actual_seconds = int(duration_minutes * 60)
    predicted_seconds = int(run.predicted_time_seconds)
    delta = actual_seconds - predicted_seconds
    return {
        "predicted_seconds": predicted_seconds,
        "predicted_formatted": VDOTCalculator.format_duration(predicted_seconds),
        "actual_seconds": actual_seconds,
        "actual_formatted": VDOTCalculator.format_duration(actual_seconds),
        "delta_seconds": delta,
        "delta_formatted": VDOTCalculator.format_duration(abs(delta)),
        "faster_than_predicted": delta < 0,
    }


def _run_to_response(run: RunLog) -> RunLogResponse:
    """Convert a RunLog model instance to a RunLogResponse schema."""
    return RunLogResponse(
        id=run.id,
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
        predicted_time_seconds=run.predicted_time_seconds,
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
        # Validate plan ownership to prevent IDOR
        if run_log.training_plan_id:
            plan = db.query(TrainingPlan).filter(
                TrainingPlan.id == run_log.training_plan_id,
                TrainingPlan.user_id == current_user.id,
            ).first()
            if not plan:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Training plan not found or access denied",
                )

        validated_workout: Optional[DailyWorkout] = None
        if run_log.daily_workout_id:
            validated_workout = (
                db.query(DailyWorkout)
                .join(WeeklyPlan, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
                .join(TrainingPlan, WeeklyPlan.training_plan_id == TrainingPlan.id)
                .filter(
                    DailyWorkout.id == run_log.daily_workout_id,
                    TrainingPlan.user_id == current_user.id,
                )
                .first()
            )
            if not validated_workout:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Workout not found or access denied",
                )

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
        if validated_workout and run_log.perceived_effort:
            workout_type = validated_workout.workout_type or run_log.workout_type or "easy"
            score, label = calculate_quality_score(
                actual_effort=run_log.perceived_effort,
                actual_pace_min_km=avg_pace_min_km,
                workout_type=workout_type,
                planned_pace_min_km=validated_workout.planned_pace_min_km if hasattr(validated_workout, "planned_pace_min_km") else None,
            )
            new_run.effort_quality_score = score
            new_run.quality_label = label

        _enrich_vdot_and_prediction(new_run, run_log.distance_km, run_log.duration_minutes, current_user.id, db)

        db.add(new_run)
        db.commit()

        try:
            FeedbackService.generate_and_store(new_run, db)
        except Exception as e:
            logger.warning(f"Feedback generation failed for run {new_run.id}: {e}")

        logger.info(f"Run log created for user {current_user.id}: {run_log.distance_km}km in {run_log.duration_minutes}min")

        response_data = _run_to_response(new_run)
        if new_run.vdot:
            response_data.predictions = VDOTCalculator.predict_times(new_run.vdot)
        response_data.race_comparison = _build_race_comparison(new_run, run_log.duration_minutes)
        return response_data
    except SQLAlchemyError as e:
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


@runs_router.get("/race-history")
async def get_race_history(
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent runs with predicted vs actual comparison data."""
    return RacePredictorService.get_race_history(current_user.id, limit, db)


@runs_router.get("/predictions")
async def get_race_predictions(
    target_distance: Optional[float] = Query(None, description="Target race distance in km"),
    goal_time: Optional[str] = Query(None, description="Goal time in HH:MM:SS or MM:SS"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get race predictions based on user's best recent VDOT from all runs.

    Returns predictions for all standard distances unless target_distance is specified.
    When goal_time is provided, performs gap analysis.
    """
    predictions_data = RacePredictorService.get_predictions_for_user(current_user.id, db)

    if not predictions_data.get("has_sufficient_data"):
        return {
            "current_vdot": None,
            "vdot_trend": "stable",
            "predictions": {},
            "best_effort": None,
            "has_sufficient_data": False,
            "message": "Log some runs to get predictions",
        }

    result = {
        "current_vdot": predictions_data["current_vdot"],
        "vdot_trend": predictions_data["vdot_trend"],
        "predictions": {},
        "best_effort": predictions_data["best_effort"],
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


@runs_router.get("/feedback/plan/{plan_id}")
async def get_plan_feedback(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all coaching feedback for runs logged against a plan."""
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


@runs_router.get("/{run_id}/feedback")
async def get_run_feedback(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get coaching feedback for a specific run."""
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




