"""Router for logging, editing and race-tagging runs."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.post_sync_service import recalibrate_from_race
from app.application.watch_sync_service import resync_plan_to_watch
from app.contexts.runner.enrichment.derived_fields import apply_vdot
from app.contexts.runner.enrichment.run_creation_service import RunCreationService
from app.contexts.runner.enrichment.run_enrichment_service import run_to_response
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.dependencies import (
    get_current_user,
    get_db,
    get_intervals_service,
    get_run_repository,
)
from app.exceptions import ValidationException
from app.infrastructure.integrations.intervals_service import IntervalsService
from app.models import TrainingPlan, User
from app.schemas import (
    RunLogCreate,
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

    # ``exclude_unset`` means "sent" == "write", so an explicit null would write
    # NULL into a column a run cannot do without: no distance or duration makes
    # it un-scorable, and no date makes it unplaceable on the plan calendar. A
    # client that wants to leave one of these alone should omit it.
    cleared = [
        field
        for field in ("distance_km", "duration_minutes", "date")
        if field in update_data and update_data[field] is None
    ]
    if cleared:
        raise ValidationException(
            "These fields cannot be cleared once a run has them: " + ", ".join(cleared)
        )

    for field, value in update_data.items():
        setattr(run, field, value)

    if "distance_km" in update_data or "duration_minutes" in update_data:
        # Both columns are nullable, and the values may come from an existing row
        # Recompute only when both are usable. The rule above keeps *this*
        # endpoint from clearing either, but a row written before it — or
        # straight to the database — can still be incomplete, and this used to be
        # a bare division that turned such a row into a 500 on a partial edit.
        # The truthiness check also rules out a zero distance.
        if run.distance_km and run.duration_minutes:
            run.avg_pace_min_km = run.duration_minutes / run.distance_km

    db.commit()
    db.refresh(run)

    logger.info("Run log %s updated for user %s", run_id, current_user.id)

    return run_to_response(run)


class RaceMarkRequest(BaseModel):
    is_race: bool = True


@runs_router.post("/{run_id}/race")
def mark_run_as_race(
    run_id: str,
    payload: RaceMarkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    run_repo: SQLAlchemyRunRepository = Depends(get_run_repository),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> dict:
    """Tell the coach a run was a race — and re-pace the plan from it.

    A tune-up race is the most honest fitness test a runner does, but imported
    races arrive looking like any other hard run. Marking one tags it
    ``race`` (which the race predictor already weights above training
    efforts) and immediately recalibrates the plan in progress from that
    run's VDOT, then re-mirrors the watch. Unmarking only removes the tag;
    paces then drift back through the normal recalibration if training
    disagrees with the race.
    """
    run = run_repo.get_for_user(run_id, current_user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run log not found"
        )

    if not payload.is_race:
        if run.workout_type == "race":
            run.workout_type = None
        db.commit()
        return {"ok": True, "is_race": False, "recalibration": None}

    run.workout_type = "race"
    if run.vdot is None:
        apply_vdot(run)

    recalibration = None
    plan = _plan_for_run(db, current_user, run)
    if plan is not None and run.vdot:
        recalibration = recalibrate_from_race(
            plan, str(current_user.id), db, float(run.vdot)
        )
    db.commit()

    if recalibration and plan is not None:
        background_tasks.add_task(
            resync_plan_to_watch, str(plan.id), str(current_user.id), intervals_service
        )
    return {
        "ok": True,
        "is_race": True,
        "run_vdot": run.vdot,
        "recalibration": (
            {
                "old_vdot": recalibration["old_vdot"],
                "new_vdot": recalibration["new_vdot"],
                "direction": recalibration["direction"],
                "reason": (plan.last_change_plan or {}).get("reason"),
            }
            if recalibration and plan is not None
            else None
        ),
    }


def _plan_for_run(db: Session, user: User, run) -> Optional[TrainingPlan]:
    """The plan this run belongs to, or the one in progress."""
    from app.contexts.plan.plan_helpers import current_active_plan, plan_statuses
    from app.contexts.plan.repositories import SQLAlchemyPlanRepository
    from app.core.time_utils import local_today

    repo = SQLAlchemyPlanRepository(db)
    if run.training_plan_id:
        plan = repo.get_for_user(run.training_plan_id, user.id)
        if plan is not None:
            return plan
    plans = repo.list_by_user_recent_first(user.id)
    statuses = plan_statuses(plans, local_today())
    plan = current_active_plan(plans, statuses)
    if plan is None or statuses[plan.id].completed:
        return None
    return plan


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
