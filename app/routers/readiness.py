"""Daily readiness check-in endpoints.

The user answers four 1-5 scale questions each morning; we store a composite
score and let the plan page swap tomorrow's hard session for an easy run
when the score is low.
"""

import logging
from datetime import date as date_cls, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import ReadinessLog, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/readiness", tags=["readiness"])


class ReadinessCreate(BaseModel):
    sleep: int = Field(..., ge=1, le=5)
    soreness: int = Field(..., ge=1, le=5)
    energy: int = Field(..., ge=1, le=5)
    stress: int = Field(..., ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=500)


class ReadinessResponse(BaseModel):
    id: str
    log_date: date_cls
    sleep: int
    soreness: int
    energy: int
    stress: int
    score: int
    status: str
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("", response_model=ReadinessResponse)
def create_or_update_readiness(
    payload: ReadinessCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    """Upsert today's readiness check-in for the current user."""
    today = date_cls.today()
    existing = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == current_user.id,
            ReadinessLog.log_date == today,
        )
        .first()
    )

    score = ReadinessLog.compute_score(
        payload.sleep, payload.soreness, payload.energy, payload.stress
    )
    status = ReadinessLog.status_from_score(score)

    if existing:
        existing.sleep = payload.sleep
        existing.soreness = payload.soreness
        existing.energy = payload.energy
        existing.stress = payload.stress
        existing.score = score
        existing.status = status
        existing.notes = payload.notes
        log = existing
    else:
        log = ReadinessLog(
            user_id=current_user.id,
            log_date=today,
            sleep=payload.sleep,
            soreness=payload.soreness,
            energy=payload.energy,
            stress=payload.stress,
            score=score,
            status=status,
            notes=payload.notes,
        )
        db.add(log)

    db.commit()
    db.refresh(log)
    return log


@router.get("/today", response_model=Optional[ReadinessResponse])
def get_today_readiness(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return today's readiness if logged, otherwise null."""
    today = date_cls.today()
    log = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == current_user.id,
            ReadinessLog.log_date == today,
        )
        .first()
    )
    return log


@router.get("/recent", response_model=list[ReadinessResponse])
def get_recent_readiness(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReadinessResponse]:
    """Return the last N days of readiness logs (most recent first)."""
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90")
    cutoff = date_cls.today() - timedelta(days=days - 1)
    logs = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == current_user.id,
            ReadinessLog.log_date >= cutoff,
        )
        .order_by(ReadinessLog.log_date.desc())
        .all()
    )
    return logs
