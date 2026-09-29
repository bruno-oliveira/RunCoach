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
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time_utils import utcnow_naive
from app.models.base import Base


class WellnessDay(Base):
    __tablename__ = "wellness_days"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_wellness_user_date"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The type is imported as `date_type` because a bare `date` here would
    # resolve to this very column inside the class body.
    date: Mapped[date_type] = mapped_column(Date)
    hrv: Mapped[float | None] = mapped_column(Float)
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="intervals")
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
