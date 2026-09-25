"""One morning's objective recovery markers, as the runner's watch saw them.

Imported from Intervals.icu's wellness endpoint (which Garmin, Oura, Whoop and
friends feed), one row per user per local calendar day. Only the *objective*
markers are kept: HRV, resting HR and sleep. Intervals' own subjective fields
use different scales from our check-in and are typed by the same runner who
fills our card, so importing them would count one feeling twice.

These rows are raw material, not a verdict — ``app.core.coaching.wellness``
compares each morning against the runner's own recent baseline, because an HRV
of 45 is a great morning for one person and a warning for another.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.models.base import Base


class WellnessDay(Base):
    __tablename__ = "wellness_days"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_wellness_user_date"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = Column(Date, nullable=False)
    hrv = Column(Float, nullable=True)  # rMSSD, ms
    resting_hr = Column(Integer, nullable=True)
    sleep_hours = Column(Float, nullable=True)
    sleep_score = Column(Float, nullable=True)  # device score, 0–100
    source = Column(String(20), nullable=False, default="intervals")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
