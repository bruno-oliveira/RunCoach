"""Daily readiness check-in endpoints.

The user answers four 1-5 scale questions each morning; we store a composite
score and let the plan page swap tomorrow's hard session for an easy run
when the score is low.
"""

import logging
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import DailyWorkout, ReadinessLog, TrainingPlan, User, WeeklyPlan
from app.utils import persist_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/readiness", tags=["readiness"])


class ReadinessCreate(BaseModel):
    sleep: int = Field(..., ge=1, le=5)
    soreness: int = Field(..., ge=1, le=5)
    energy: int = Field(..., ge=1, le=5)
    stress: int = Field(..., ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=500)


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    log_date: date_cls
    sleep: int
    soreness: int
    energy: int
    stress: int
    score: int
    status: str
    notes: Optional[str]


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


# ---------------------------------------------------------------------------
# Readiness-based workout adaptation
# ---------------------------------------------------------------------------

class AdaptRequest(BaseModel):
    plan_id: str


_HARD_TYPES = {"tempo", "interval", "threshold", "speed", "race", "long", "vo2max", "race_pace", "fartlek"}


def _find_todays_workout(plan: TrainingPlan):
    """Return (week_number, day_of_week, week_data, workout_data) or None."""
    start = plan.start_date or plan.created_at
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    start_d = start.date() if isinstance(start, datetime) else start
    days_elapsed = (today - start_d).days
    if days_elapsed < 0:
        return None

    week = days_elapsed // 7 + 1
    day_of_week = days_elapsed % 7 + 1  # 1=Mon .. 7=Sun

    plan_data = plan.plan_data if plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week), None)
    if not week_data:
        return None

    workout = next(
        (w for w in week_data.get("daily_workouts", []) if w.get("day") == day_of_week),
        None,
    )
    return week, day_of_week, week_data, workout, plan_data


@router.post("/adapt")
def adapt_todays_workout(
    body: AdaptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adjust today's workout based on this morning's readiness check-in.

    * **caution** → keep the run but reduce distance ~15 % and drop to easy.
    * **rest** → convert to rest day (0 km).
    """
    # 1. Today's readiness must exist and not be "ready"
    today = date_cls.today()
    readiness = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == current_user.id,
            ReadinessLog.log_date == today,
        )
        .first()
    )
    if not readiness:
        raise HTTPException(status_code=400, detail="Complete today's check-in first.")
    if readiness.status == "ready":
        raise HTTPException(status_code=400, detail="Readiness is green — no adjustment needed.")

    # 2. Load the plan
    plan = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.id == body.plan_id,
            TrainingPlan.user_id == current_user.id,
        )
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # 3. Locate today's workout in plan_data
    result = _find_todays_workout(plan)
    if result is None:
        raise HTTPException(status_code=400, detail="No active workout for today.")
    week_num, day_of_week, week_data, workout, plan_data = result

    if workout is None or workout.get("type") == "rest":
        raise HTTPException(status_code=400, detail="Today is already a rest day.")

    # 4. Snapshot the original for the response
    original = {
        "type": workout.get("type"),
        "distance": workout.get("distance"),
        "intensity": workout.get("intensity"),
        "notes": workout.get("notes"),
    }

    # 5. Apply the adaptation
    if readiness.status == "rest":
        workout["type"] = "rest"
        workout["distance"] = 0
        workout["intensity"] = "low"
        workout["notes"] = "Rest day — readiness check-in flagged recovery needed."
    else:  # caution
        if workout.get("type") in _HARD_TYPES:
            workout["type"] = "easy"
        old_dist = workout.get("distance") or 0
        workout["distance"] = round(old_dist * 0.85, 1)
        workout["intensity"] = "low"
        workout["notes"] = (
            "Eased from readiness check-in. "
            "Keep effort conversational."
        )

    # Recompute week total
    week_data["total_km"] = round(
        sum(w.get("distance", 0) for w in week_data.get("daily_workouts", [])), 1
    )

    # 6. Persist plan_data JSON
    plan.plan_data = plan_data
    persist_json(plan, "plan_data")

    # 7. Also update the DailyWorkout DB row if it exists
    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week_num,
        )
        .first()
    )
    if weekly_plan:
        db_workout = (
            db.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == weekly_plan.id,
                DailyWorkout.day_of_week == day_of_week,
            )
            .first()
        )
        if db_workout:
            if not db_workout.baseline_distance_km:
                db_workout.baseline_distance_km = db_workout.distance_km
            db_workout.workout_type = workout["type"]
            db_workout.distance_km = workout["distance"]
            db_workout.intensity = workout["intensity"]
            db_workout.notes = workout["notes"]

    db.commit()

    return {
        "ok": True,
        "status": readiness.status,
        "week": week_num,
        "day": day_of_week,
        "original": original,
        "adapted": {
            "type": workout["type"],
            "distance": workout["distance"],
            "intensity": workout["intensity"],
            "notes": workout["notes"],
        },
    }
