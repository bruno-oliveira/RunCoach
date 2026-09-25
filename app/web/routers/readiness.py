"""Router for the daily readiness check-in (the morning card)."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.wellness_sync_service import refresh_wellness
from app.contexts.runner.wellness.checkin_service import CheckInService
from app.contexts.runner.wellness.wellness_service import WellnessService
from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_intervals_service
from app.infrastructure.integrations.intervals_service import (
    IntervalsService,
    has_wellness_scope,
)
from app.models import ReadinessLog, User
from app.rate_limit import wellness_prefill_limiter
from app.schemas import ReadinessCheckInCreate, ReadinessCheckInResponse

logger = logging.getLogger(__name__)

readiness_router = APIRouter(prefix="/api/readiness", tags=["readiness"])


def _to_response(db: Session, log: ReadinessLog) -> ReadinessCheckInResponse:
    """Serialize a stored log, re-deriving its band/label/drivers for the voice."""
    assessment = CheckInService(db).assess(log)
    return ReadinessCheckInResponse(
        id=log.id,
        date=log.date,
        sleep_hours=log.sleep_hours,
        sleep_quality=log.sleep_quality,
        energy=log.energy,
        soreness=log.soreness,
        stress=log.stress,
        resting_hr=log.resting_hr,
        hrv=log.hrv,
        notes=log.notes,
        score=log.score,
        band=assessment.band,
        label=assessment.label,
        drivers=assessment.drivers,
        source=log.source or "checkin",
    )


@readiness_router.post(
    "", response_model=ReadinessCheckInResponse, status_code=status.HTTP_201_CREATED
)
def record_checkin(
    payload: ReadinessCheckInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record (or update) today's readiness check-in — one row per day."""
    try:
        log = CheckInService(db).record(
            current_user.id,
            sleep_hours=payload.sleep_hours,
            sleep_quality=payload.sleep_quality,
            energy=payload.energy,
            soreness=payload.soreness,
            stress=payload.stress,
            resting_hr=payload.resting_hr,
            hrv=payload.hrv,
            notes=payload.notes,
            on_date=payload.date,
        )
        return _to_response(db, log)
    except SQLAlchemyError:
        logger.exception("Failed to record readiness for user %s", current_user.id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save your check-in",
        )


@readiness_router.get("/today")
def get_today_checkin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Today's check-in for the current user, if one has been logged."""
    log = CheckInService(db).get_today(current_user.id)
    if log is None:
        return {"logged": False, "checkin": None}
    return {
        "logged": True,
        # A watch-only row isn't the runner having checked in: the card should
        # still invite them to, pre-filled with what the watch saw.
        "self_reported": (log.source or "checkin") != "wearable",
        "checkin": _to_response(db, log).model_dump(mode="json"),
    }


@readiness_router.get("/prefill")
async def get_checkin_prefill(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> Dict[str, Any]:
    """What the watch recorded overnight, to pre-fill this morning's card.

    Pulls fresh wellness from Intervals.icu first (last night's sleep usually
    lands after the daily sync), best-effort — with no connection, no grant, or
    a slow provider the card simply opens empty. ``reconnect_for_wellness``
    tells the card to offer the one-tap reconnect instead.
    """
    wellness_prefill_limiter.check(request)
    today = local_today()
    try:
        await refresh_wellness(current_user, db, intervals_service, today=today)
        db.commit()
    except Exception:
        logger.warning("Wellness refresh for prefill failed", exc_info=True)
        db.rollback()
    data = WellnessService(db).prefill(current_user.id, today)
    data["reconnect_for_wellness"] = bool(
        current_user.intervals_athlete_id and not has_wellness_scope(current_user)
    )
    return data
