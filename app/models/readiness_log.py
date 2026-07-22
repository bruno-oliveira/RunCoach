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
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
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
from sqlalchemy.orm import Mapped, relationship

from app.models.base import Base


class ReadinessLog(Base):
    __tablename__ = "readiness_logs"
    __table_args__ = (
        # One check-in per runner per calendar day; the service upserts on it.
        UniqueConstraint("user_id", "date", name="uq_readiness_user_date"),
        Index("idx_readiness_user_date", "user_id", "date"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Calendar day the check-in describes (user-local). Not a timestamp: the
    # unique constraint above enforces the one-per-day upsert.
    date = Column(Date, nullable=False)

    # Self-reported inputs. All optional so the card can be a partial 15-second
    # capture. 1–5 Likert scales unless noted.
    sleep_hours = Column(Float, nullable=True)
    sleep_quality = Column(Integer, nullable=True)  # 1 (awful) – 5 (great)
    energy = Column(Integer, nullable=True)  # 1 (drained) – 5 (buzzing)
    soreness = Column(Integer, nullable=True)  # 1 (fresh) – 5 (wrecked)
    stress = Column(Integer, nullable=True)  # 1 (calm) – 5 (frazzled)

    # Optional objective inputs (from a wearable, entered manually for now).
    resting_hr = Column(Integer, nullable=True)
    hrv = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    # Derived 0–100 readiness score. Persisted (not computed at read time) so the
    # adaptation signal reads a stable value and old check-ins keep the score
    # they were logged with even if the scoring formula later changes.
    score = Column(Float, nullable=True)

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    user: Mapped["User"] = relationship("User", back_populates="readiness_logs")
