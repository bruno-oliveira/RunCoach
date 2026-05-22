"""Router for run logging and performance tracking."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contexts.runner.enrichment.run_creation_service import RunCreationService
from app.contexts.runner.enrichment.run_enrichment_service import run_to_response
from app.contexts.runner.fitness.feedback_service import FeedbackService
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import get_current_user, get_db, get_run_repository
from app.models import User
from app.schemas import (
    RunLogCreate,
    RunLogListResponse,
    RunLogResponse,
    RunLogUpdate,
)

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/runs", tags=["runs"])


@runs_router.post(
    "", response_model=RunLogResponse, status_code=status.HTTP_201_CREATED
)
def create_run_log(
    run_log: RunLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new run log entry."""
    try:
        return RunCreationService().create_run(run_log, current_user, db)
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
def get_run_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    workout_type: Optional[str] = Query(None, description="Filter by workout type"),
    start_date: Optional[datetime] = Query(
        None, description="Filter runs after this date"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Filter runs before this date"
    ),
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
):
    """Get paginated list of user's run logs with optional filtering."""
    try:
        run_logs, total = run_repo.list_paginated_for_user(
            current_user.id,
            page=page,
            page_size=page_size,
            workout_type=workout_type,
            start_date=start_date,
            end_date=end_date,
        )

        return RunLogListResponse(
            runs=[run_to_response(run) for run in run_logs],
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError:
        logger.exception(
            "Database error fetching run logs for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch run logs",
        )


@runs_router.get("/race-history")
def get_race_history(
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent runs with predicted vs actual comparison data."""
    return RacePredictorService.get_race_history(current_user.id, limit, db)


@runs_router.get("/predictions")
def get_race_predictions(
    target_distance: Optional[float] = Query(
        None, description="Target race distance in km"
    ),
    goal_time: Optional[str] = Query(
        None, description="Goal time in HH:MM:SS or MM:SS"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get race predictions based on user's best recent VDOT from all runs."""
    predictions_data = RacePredictorService.get_predictions_for_user(
        current_user.id, db
    )

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
            predicted = VDOTCalculator.predict_time_for_distance(
                current_vdot, target_distance
            )
            range_data = VDOTCalculator.get_confidence_range(
                current_vdot, target_distance
            )
            result["predicted_time"] = (
                VDOTCalculator.format_duration(predicted) if predicted else None
            )
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
def get_plan_feedback(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all coaching feedback for runs logged against a plan."""
    feedbacks = FeedbackService.get_feedback_for_plan(plan_id, current_user.id, db)
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
def get_run_log(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
):
    """Get a specific run log by ID."""
    run = run_repo.get_for_user(run_id, current_user.id)

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    return run_to_response(run)


@runs_router.put("/{run_id}", response_model=RunLogResponse)
def update_run_log(
    run_id: str,
    run_update: RunLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
):
    """Update an existing run log."""
    run = run_repo.get_for_user(run_id, current_user.id)

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

    logger.info("Run log %s updated for user %s", run_id, current_user.id)

    return run_to_response(run)


@runs_router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run_log(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
):
    """Delete a run log."""
    run = run_repo.get_for_user(run_id, current_user.id)

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found",
        )

    db.delete(run)
    db.commit()

    logger.info("Run log %s deleted for user %s", run_id, current_user.id)


@runs_router.get("/{run_id}/feedback")
def get_run_feedback(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
):
    """Get coaching feedback for a specific run."""
    run = run_repo.get_for_user(run_id, current_user.id)
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
