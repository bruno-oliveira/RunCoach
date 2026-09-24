"""The watch's overnight markers: storage, baseline, and the passive check-in.

Two jobs:

* **Store** what Intervals.icu reports (one ``WellnessDay`` per local date,
  upserted — Garmin revises last night's sleep during the morning).
* **Stand in for the card.** When the runner hasn't checked in but their watch
  has something to say, write a ``ReadinessLog`` with ``source="wearable"``
  from the objective markers alone. That is what finally gives the adaptation
  engine's readiness signal data for the ~everyone who never fills a form. The
  runner's own check-in always wins: :meth:`ensure_wearable_log` never touches
  a ``"checkin"`` row, and a later check-in overwrites a wearable one.

The judgement itself (baseline, ratios, points) is pure and lives in
:mod:`app.core.coaching.wellness`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.core.coaching.readiness_checkin import score_checkin
from app.core.coaching.wellness import (
    BASELINE_WINDOW_DAYS,
    ObjectiveMarkers,
    WellnessPoint,
    baseline,
    markers,
)
from app.models import ReadinessLog, WellnessDay

WEARABLE = "wearable"
CHECKIN = "checkin"


class WellnessService:
    """Per-runner wellness storage and the markers readiness scoring reads."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- storage ----------------------------------------------------------

    def upsert_days(self, user_id: str, rows: Iterable[Dict[str, Any]]) -> int:
        """Store parsed wellness rows; returns how many days were written.

        Flushes, doesn't commit — the caller owns the transaction.
        """
        rows = list(rows)
        if not rows:
            return 0
        days = [r["date"] for r in rows]
        existing = {
            w.date: w
            for w in self.db.query(WellnessDay)
            .filter(
                WellnessDay.user_id == user_id,
                WellnessDay.date >= min(days),
                WellnessDay.date <= max(days),
            )
            .all()
        }
        written = 0
        for row in rows:
            record = existing.get(row["date"])
            if record is None:
                record = WellnessDay(user_id=user_id, date=row["date"])
                self.db.add(record)
                existing[row["date"]] = record
            changed = False
            for field in ("hrv", "resting_hr", "sleep_hours", "sleep_score"):
                value = row.get(field)
                # A later partial record (sleep synced, HRV not yet) must not
                # blank a value we already hold.
                if value is not None and getattr(record, field) != value:
                    setattr(record, field, value)
                    changed = True
            written += int(changed)
        self.db.flush()
        return written

    def day(self, user_id: str, on: date) -> Optional[WellnessDay]:
        return (
            self.db.query(WellnessDay)
            .filter(WellnessDay.user_id == user_id, WellnessDay.date == on)
            .first()
        )

    def has_any(self, user_id: str) -> bool:
        return (
            self.db.query(WellnessDay.id).filter(WellnessDay.user_id == user_id).first()
            is not None
        )

    def history(self, user_id: str, today: date) -> List[WellnessPoint]:
        since = today - timedelta(days=BASELINE_WINDOW_DAYS)
        rows = (
            self.db.query(WellnessDay.date, WellnessDay.hrv, WellnessDay.resting_hr)
            .filter(
                WellnessDay.user_id == user_id,
                WellnessDay.date >= since,
                WellnessDay.date <= today,
            )
            .all()
        )
        return [(r[0], r[1], r[2]) for r in rows]

    # ---- judgement --------------------------------------------------------

    def markers_for(self, user_id: str, on: date) -> Optional[ObjectiveMarkers]:
        """This morning's markers against the runner's baseline, or ``None``."""
        today_row = self.day(user_id, on)
        if today_row is None:
            return None
        base = baseline(self.history(user_id, on), on)
        found = markers(
            hrv=today_row.hrv,
            resting_hr=today_row.resting_hr,
            sleep_hours=today_row.sleep_hours,
            base=base,
        )
        return found if found.has_signal else None

    def ensure_wearable_log(self, user_id: str, on: date) -> Optional[ReadinessLog]:
        """Write (or refresh) the watch-only readiness row for ``on``.

        Returns the row, or ``None`` when the runner already checked in (their
        word stands) or the watch has nothing judgeable yet.
        """
        log = (
            self.db.query(ReadinessLog)
            .filter(ReadinessLog.user_id == user_id, ReadinessLog.date == on)
            .first()
        )
        if log is not None and (log.source or CHECKIN) != WEARABLE:
            return None
        found = self.markers_for(user_id, on)
        if found is None:
            return None
        assessment = score_checkin(objective=found)
        if assessment.score is None:
            return None
        if log is None:
            log = ReadinessLog(user_id=user_id, date=on, source=WEARABLE)
            self.db.add(log)
        log.sleep_hours = found.sleep_hours
        log.resting_hr = int(found.resting_hr) if found.resting_hr else None
        log.hrv = found.hrv
        log.score = assessment.score
        self.db.flush()
        return log

    def prefill(self, user_id: str, on: date) -> Dict[str, Any]:
        """What the check-in card can pre-fill from the watch, plus the verdict."""
        row = self.day(user_id, on)
        if row is None:
            return {"available": False}
        found = self.markers_for(user_id, on)
        return {
            "available": True,
            "sleep_hours": row.sleep_hours,
            "resting_hr": row.resting_hr,
            "hrv": row.hrv,
            "hrv_ratio": found.hrv_ratio if found else None,
            "rhr_delta": found.rhr_delta if found else None,
            "has_baseline": bool(
                found and (found.hrv_ratio is not None or found.rhr_delta is not None)
            ),
        }
