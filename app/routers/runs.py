"""Router for run logging and performance tracking."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.quality_scorer import calculate_quality_score
from app.core.vdot_calculator import VDOTCalculator
from app.dependencies import get_db, get_current_user
from app.models import RunLog, User, DailyWorkout
from app.schemas import (
    RunLogCreate,
    RunLogResponse,
)
from app.services.race_predictor_service import RacePredictorService

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/runs", tags=["runs"])


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

        # Auto-calculate VDOT for all runs with sufficient distance
        if run_log.distance_km >= 2.0 and run_log.duration_minutes > 0:
            vdot = VDOTCalculator.calculate_vdot(
                run_log.distance_km, int(run_log.duration_minutes * 60)
            )
            if vdot:
                new_run.vdot = vdot

        # Snapshot the pre-run prediction based on prior fitness
        if run_log.distance_km >= 2.0:
            try:
                pre_race_vdot = RacePredictorService.get_best_recent_vdot(
                    current_user.id, weeks=12, db=db
                )
                if pre_race_vdot:
                    predicted_seconds = VDOTCalculator.predict_time_for_distance(
                        pre_race_vdot, run_log.distance_km
                    )
                    if predicted_seconds:
                        new_run.predicted_time_seconds = float(predicted_seconds)
            except Exception as e:
                logger.warning("Failed to snapshot prediction for run: %s", e)

        db.add(new_run)
        db.commit()

        # Generate predictions for the toast if VDOT was calculated
        race_predictions = None
        if new_run.vdot:
            race_predictions = VDOTCalculator.predict_times(new_run.vdot)

        # Generate coaching feedback (non-fatal)
        try:
            from app.services.feedback_service import FeedbackService
            FeedbackService.generate_and_store(new_run, db)
        except Exception as e:
            logger.warning("Feedback generation failed for run %s: %s", new_run.id, e)

        logger.info("Run log created for user %s: %skm in %smin", current_user.id, run_log.distance_km, run_log.duration_minutes)

        response_data = _run_to_response(new_run)
        if race_predictions:
            response_data.predictions = race_predictions
        # Include comparison data when a prediction was available
        if new_run.predicted_time_seconds:
            actual_seconds = int(run_log.duration_minutes * 60)
            predicted_seconds = int(new_run.predicted_time_seconds)
            delta = actual_seconds - predicted_seconds
            response_data.race_comparison = {
                "predicted_seconds": predicted_seconds,
                "predicted_formatted": VDOTCalculator.format_duration(predicted_seconds),
                "actual_seconds": actual_seconds,
                "actual_formatted": VDOTCalculator.format_duration(actual_seconds),
                "delta_seconds": delta,
                "delta_formatted": VDOTCalculator.format_duration(abs(delta)),
                "faster_than_predicted": delta < 0,
            }
        return response_data
    except SQLAlchemyError as e:
        logger.error("Error creating run log: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create run log",
        )


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

    logger.info("Run log %s deleted for user %s", run_id, current_user.id)




