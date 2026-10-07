"""What a runner's heart rate says their training runs are worth.

The I/O half of ``core/training/physiology/submaximal_vdot``: it finds the
threshold heart rate the runner or their watch supplied and the runs of the
window, and the pure module turns them into a fitness reading.

Only a *measured* threshold counts. The fallback estimate of LTHR is itself
read off the runner's VDOT (``estimate_threshold_hr_from_pace_hr_fit``), so
using it here would have fitness vouching for the number that produced it —
and, since that estimator calls the fitness estimate, never return.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.hr_zone_service import get_user_max_hr
from app.core.training.physiology.hr_zone_calculator import resolve_lthr_anchor
from app.core.training.physiology.submaximal_vdot import TrainingRun, aerobic_vdot
from app.models import RunLog, User


def measured_threshold_hr(user: User, db: Session) -> Optional[int]:
    """LTHR from the runner's own entry, else their watch — never an estimate.

    ``None`` too when the value is implausible against their max heart rate:
    the zones ignore such a number, and so does this.
    """
    lthr = user.threshold_hr or user.intervals_lthr
    if not lthr or lthr <= 0:
        return None
    max_hr, _ = get_user_max_hr(user.id, db, user_age=user.age, user_max_hr=user.max_hr)
    return int(lthr) if resolve_lthr_anchor(max_hr, lthr) == lthr else None


def aerobic_vdot_for(user_id: str, weeks: int, db: Session) -> Optional[float]:
    """Heart-rate fitness reading over the last ``weeks``, or ``None``."""
    user = db.get(User, user_id)
    if user is None:
        return None
    lthr = measured_threshold_hr(user, db)
    if lthr is None:
        return None
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=weeks)
    rows = (
        db.query(
            RunLog.avg_pace_min_km,
            RunLog.avg_heart_rate,
            RunLog.duration_minutes,
            RunLog.distance_km,
            RunLog.elevation_gain_m,
        )
        .filter(
            RunLog.user_id == user_id,
            RunLog.avg_heart_rate.isnot(None),
            RunLog.date >= cutoff,
        )
        .all()
    )
    return aerobic_vdot((TrainingRun(*row) for row in rows), lthr)
