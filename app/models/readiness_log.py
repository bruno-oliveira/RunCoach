"""Daily readiness check-in — how the runner *feels* on a given morning.

One row per user per calendar day (upsert). The self-reported sub-scores are
distilled into a single 0–100 ``score`` by
:func:`app.core.coaching.readiness_checkin.score_checkin`; that score is what the
adaptation engine's readiness signal
(:func:`app.contexts.plan.adaptation.signal_computer.signals._readiness_signal`)
consumes once at least ``READINESS_MIN_LOGS`` recent logs exist.

The morning card is deliberately a 15-second capture: every field is optional so
a runner can log just "slept 5h, legs heavy" without filling a whole form.
"""

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReadinessLog(Base):
    __tablename__ = "readiness_logs"
    __table_args__ = (
        # One check-in per runner per calendar day; the service upserts on it.
        UniqueConstraint("user_id", "date", name="uq_readiness_user_date"),
        Index("idx_readiness_user_date", "user_id", "date"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE")
    )
    # Calendar day the check-in describes (user-local). Not a timestamp: the
    # unique constraint above enforces the one-per-day upsert.
    # The type is imported as `date_type` because a bare `date` here would
    # resolve to this very column inside the class body.
    date: Mapped[date_type] = mapped_column(Date)

    # Self-reported inputs. All optional so the card can be a partial 15-second
    # capture. 1–5 Likert scales unless noted.
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    energy: Mapped[int | None] = mapped_column(Integer)
    soreness: Mapped[int | None] = mapped_column(Integer)
    stress: Mapped[int | None] = mapped_column(Integer)

    # Optional objective inputs (from a wearable, entered manually for now).
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    hrv: Mapped[float | None] = mapped_column(Float)

    notes: Mapped[str | None] = mapped_column(Text)

    # "checkin" when the runner filled the card; "wearable" when we wrote the
    # row ourselves from their watch's overnight HRV / resting HR / sleep
    # because they didn't. A later check-in the same day overwrites a wearable
    # row (the runner's own word wins) and flips this back to "checkin".
    source: Mapped[str] = mapped_column(String(20), default="checkin")

    # Derived 0–100 readiness score. Persisted (not computed at read time) so the
    # adaptation signal reads a stable value and old check-ins keep the score
    # they were logged with even if the scoring formula later changes.
    score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    user: Mapped["User"] = relationship("User", back_populates="readiness_logs")
