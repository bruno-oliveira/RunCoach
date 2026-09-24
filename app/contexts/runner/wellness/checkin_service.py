"""Daily readiness check-in service — capture, once-per-day upsert, scoring.

Thin application service over :class:`SQLAlchemyReadinessRepository` and the pure
:func:`app.core.coaching.readiness_checkin.score_checkin`. Owns the "one row per
user per calendar day" rule (upsert) and turns a stored log back into a
:class:`ReadinessAssessment` for the coaching voice.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.contexts.runner.wellness.repository import SQLAlchemyReadinessRepository
from app.contexts.runner.wellness.wellness_service import (
    CHECKIN,
    WEARABLE,
    WellnessService,
)
from app.core.coaching.readiness_checkin import ReadinessAssessment, score_checkin
from app.core.time_utils import local_today
from app.models import ReadinessLog


class CheckInService:
    """Capture and read daily readiness check-ins."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SQLAlchemyReadinessRepository(db)

    def record(
        self,
        user_id: str,
        *,
        sleep_hours: Optional[float] = None,
        sleep_quality: Optional[int] = None,
        energy: Optional[int] = None,
        soreness: Optional[int] = None,
        stress: Optional[int] = None,
        resting_hr: Optional[int] = None,
        hrv: Optional[float] = None,
        notes: Optional[str] = None,
        on_date: Optional[date_cls] = None,
    ) -> ReadinessLog:
        """Create or update today's check-in and (re)derive its score.

        Upserts on ``(user_id, date)`` so logging twice in a day edits the same
        row rather than stacking duplicates.
        """
        day = on_date or local_today()
        assessment = score_checkin(
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
            energy=energy,
            soreness=soreness,
            stress=stress,
            objective=WellnessService(self.db).markers_for(user_id, day),
        )

        log = self.repo.get_for_user_on(user_id, day)
        if log is None:
            log = ReadinessLog(user_id=user_id, date=day)

        log.sleep_hours = sleep_hours
        log.sleep_quality = sleep_quality
        log.energy = energy
        log.soreness = soreness
        log.stress = stress
        log.resting_hr = resting_hr
        log.hrv = hrv
        log.notes = notes
        log.score = assessment.score
        # The runner's own word replaces a watch-only row for the same morning.
        log.source = CHECKIN

        self.repo.save(log)
        return log

    def get_today(
        self, user_id: str, on_date: Optional[date_cls] = None
    ) -> Optional[ReadinessLog]:
        """Today's check-in for the user, or ``None`` if not logged yet."""
        return self.repo.get_for_user_on(user_id, on_date or local_today())

    def list_recent(
        self, user_id: str, *, days: int = 14, limit: Optional[int] = None
    ) -> List[ReadinessLog]:
        """Recent check-ins (newest first), for the adaptation readiness signal."""
        since = local_today() - timedelta(days=days)
        return self.repo.list_recent_for_user(user_id, since=since, limit=limit)

    def assess(self, log: ReadinessLog) -> ReadinessAssessment:
        """Re-derive the band/label/drivers from a stored log's inputs.

        The numeric ``score`` is persisted, but the coaching voice needs the
        band and the concrete drivers ("your legs are heavy", "your HRV is 15%
        below your usual"), which we recompute from the same inputs and the
        same watch markers rather than storing redundantly.
        """
        return assess_log(self.db, log)


def assess_log(db: Session, log: ReadinessLog) -> ReadinessAssessment:
    """Band, label and drivers for a stored readiness row — check-in or watch.

    A watch-only row carries its sleep hours from the device, which scoring
    treats as an *objective* input rather than something the runner reported.
    """
    found = WellnessService(db).markers_for(str(log.user_id), log.date)
    if (log.source or CHECKIN) == WEARABLE:
        return score_checkin(objective=found) if found else score_checkin()
    return score_checkin(
        sleep_hours=log.sleep_hours,
        sleep_quality=log.sleep_quality,
        energy=log.energy,
        soreness=log.soreness,
        stress=log.stress,
        objective=found,
    )
