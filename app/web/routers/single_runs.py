"""Single runs: one generated workout, outside any training plan."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.application.single_run_service import (
    SingleRunView,
    create_single_run,
    delete_single_run,
    recent_views,
    send_to_watch,
    view_of,
)
from app.contexts.runner.single_runs import SQLAlchemySingleRunRepository
from app.dependencies import get_current_user, get_db, get_intervals_service
from app.infrastructure.integrations.intervals_service import IntervalsService
from app.models import SingleRun, User
from app.rate_limit import intervals_push_limiter, single_run_limiter
from app.schemas import SingleRunCreate, SingleRunListResponse, SingleRunResponse
from app.schemas.single_run_schemas import SingleRunCompletedRun

logger = logging.getLogger(__name__)

single_runs_router = APIRouter(prefix="/api/single-runs", tags=["single-runs"])


def _response(view: SingleRunView, watch_error: str | None = None) -> SingleRunResponse:
    single_run, run = view.single_run, view.completed_run
    workout = single_run.workout
    return SingleRunResponse(
        id=single_run.id,
        date=single_run.date,
        run_type=single_run.run_type,
        name=str(workout.get("key_workout_name") or single_run.run_type.title()),
        distance_km=single_run.distance_km,
        description=str(workout.get("description") or ""),
        steps=list(workout.get("steps") or []),
        vdot=single_run.vdot,
        estimated_minutes=view.estimated_minutes,
        on_watch=view.on_watch,
        completed_run=(
            SingleRunCompletedRun(
                id=run.id,
                distance_km=run.distance_km,
                duration_minutes=run.duration_minutes,
                avg_pace_min_km=run.avg_pace_min_km,
            )
            if run is not None
            else None
        ),
        watch_error=watch_error,
    )


def _owned_or_404(single_run_id: str, user: User, db: Session) -> SingleRun:
    single_run = SQLAlchemySingleRunRepository(db).get_for_user(single_run_id, user.id)
    if single_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Single run not found"
        )
    return single_run


@single_runs_router.post(
    "", response_model=SingleRunResponse, status_code=status.HTTP_201_CREATED
)
async def create(
    payload: SingleRunCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
):
    """Generate a one-off workout, optionally sending it to the watch.

    A watch push that fails still answers 201: the workout exists, and
    ``watch_error`` says why it isn't on the wrist yet.
    """
    single_run_limiter.check(request)
    single_run = create_single_run(
        current_user,
        db,
        run_type=payload.run_type,
        distance_km=payload.distance_km,
        duration_minutes=payload.duration_minutes,
        on_date=payload.date,
    )
    watch_error = None
    if payload.send_to_watch:
        watch_error = await send_to_watch(
            single_run, current_user, db, intervals_service
        )
    return _response(view_of(single_run, db), watch_error)


@single_runs_router.get("", response_model=SingleRunListResponse)
def list_recent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The runner's upcoming and recent single runs, newest first."""
    return SingleRunListResponse(
        single_runs=[_response(view) for view in recent_views(current_user, db)]
    )


@single_runs_router.post("/{single_run_id}/send-to-watch")
async def send(
    single_run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> SingleRunResponse:
    """Send (or re-send) a single run to the runner's watch calendar."""
    intervals_push_limiter.check(request)
    single_run = _owned_or_404(single_run_id, current_user, db)
    watch_error = await send_to_watch(single_run, current_user, db, intervals_service)
    return _response(view_of(single_run, db), watch_error)


@single_runs_router.delete("/{single_run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    single_run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> None:
    """Delete a single run. A run already logged against it is kept."""
    single_run = _owned_or_404(single_run_id, current_user, db)
    await delete_single_run(single_run, current_user, db, intervals_service)
