"""Router for run logging and performance tracking."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.training.quality_scorer import calculate_quality_score
from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import get_db, get_current_user, validate_plan_ownership
from app.models import RunLog, User, DailyWorkout, TrainingPlan, WeeklyPlan
from app.schemas import (
    RunLogCreate,
    RunLogListResponse,
    RunLogResponse,
    RunLogUpdate,
)
from app.services.fitness.feedback_service import FeedbackService
from app.services.fitness.race_predictor_service import RacePredictorService
from app.services.runs.run_enrichment_service import (
    build_race_comparison,
    enrich_vdot_and_prediction,
    run_to_response,
)

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/runs", tags=["runs"])


@runs_router.post("", response_model=RunLogResponse, status_code=status.HTTP_201_CREATED)
async def create_run_log(
    run_log: RunLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new run log entry."""
    try:
        if run_log.training_plan_id:
            validate_plan_ownership(run_log.training_plan_id, db, current_user)

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

        db.add(new_run)
        db.flush()

        vdot_recalibration = enrich_vdot_and_prediction(
            new_run, run_log.distance_km, run_log.duration_minutes, current_user.id, db,
        )

        db.commit()

        # Best-effort post-commit hooks: never fail the request if these throw,
        # but capture full traceback so unexpected failures are debuggable.
        try:
            FeedbackService.generate_and_store(new_run, db)
        except Exception:
            logger.warning("Feedback generation failed for run %s", new_run.id, exc_info=True)

        auto_adjust_result = None
        if new_run.training_plan_id:
            try:
                from app.services.adaptation import AdaptationService
                service = AdaptationService()
                evaluation = service.evaluate_on_run_logged(
                    new_run.training_plan_id, current_user.id, db,
                )
                if evaluation is not None:
                    auto_adjust_result = service.apply_or_park(
                        new_run.training_plan_id,
                        current_user.id,
                        db,
                        evaluation,
                        auto_enabled=bool(current_user.auto_adjust_enabled),
                    )
                else:
                    # `evaluate_on_run_logged` returns None when the
                    # multiplier is within 2% of neutral. Surface this so
                    # the UI can confirm the engine actually looked.
                    auto_adjust_result = {"action": "no_change_needed"}
            except Exception:
                logger.warning(
                    "Per-run recommendation evaluation failed for run %s",
                    new_run.id, exc_info=True,
                )

        logger.info(f"Run log created for user {current_user.id}: {run_log.distance_km}km in {run_log.duration_minutes}min")

        response_data = run_to_response(new_run)
        if new_run.vdot:
            elevation_map = None
            trail_count = None
            if (
                new_run.elevation_gain_m
                and new_run.distance_km > 0
                and new_run.elevation_gain_m / new_run.distance_km >= 20.0
            ):
                from app.services.runs.run_enrichment_service import (
                    _count_prior_trail_runs,
                )
                trail_count = _count_prior_trail_runs(current_user.id, db)
                elevation_map = {"trail": new_run.elevation_gain_m}
            response_data.predictions = VDOTCalculator.predict_times(
                new_run.vdot,
                trail_runs_count=trail_count,
                elevation_map=elevation_map,
            )
        response_data.race_comparison = build_race_comparison(new_run, run_log.duration_minutes)
        if vdot_recalibration:
            response_data.vdot_recalibration = vdot_recalibration
        if auto_adjust_result:
            response_data.auto_adjust = auto_adjust_result
        return response_data
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Database error creating run log for user %s", current_user.id)
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
    """Get paginated list of user's run logs with optional filtering."""
    try:
        query = db.query(RunLog).filter(RunLog.user_id == current_user.id)

        if workout_type:
            query = query.filter(RunLog.workout_type == workout_type)
        if start_date:
            query = query.filter(RunLog.date >= start_date)
        if end_date:
            query = query.filter(RunLog.date <= end_date)

        total = query.count()

        offset = (page - 1) * page_size
        run_logs = query.order_by(RunLog.date.desc()).offset(offset).limit(page_size).all()

        return RunLogListResponse(
            runs=[run_to_response(run) for run in run_logs],
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError:
        logger.exception("Database error fetching run logs for user %s", current_user.id)
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
    """Get race predictions based on user's best recent VDOT from all runs."""
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

    return run_to_response(run)


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

    update_data = run_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(run, field, value)

    if "distance_km" in update_data or "duration_minutes" in update_data:
        run.avg_pace_min_km = run.duration_minutes / run.distance_km

    db.commit()
    db.refresh(run)

    logger.info(f"Run log {run_id} updated for user {current_user.id}")

    return run_to_response(run)


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
