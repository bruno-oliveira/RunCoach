"""Router for the daily readiness check-in (the morning card)."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contexts.runner.wellness.checkin_service import CheckInService
from app.dependencies import get_current_user, get_db
from app.models import ReadinessLog, User
from app.schemas import ReadinessCheckInCreate, ReadinessCheckInResponse

logger = logging.getLogger(__name__)

readiness_router = APIRouter(prefix="/api/readiness", tags=["readiness"])


def _to_response(log: ReadinessLog) -> ReadinessCheckInResponse:
    """Serialize a stored log, re-deriving its band/label/drivers for the voice."""
    assessment = CheckInService.assess(log)
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
        return _to_response(log)
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
    return {"logged": True, "checkin": _to_response(log).model_dump(mode="json")}
