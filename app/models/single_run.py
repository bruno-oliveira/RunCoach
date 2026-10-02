"""A one-off workout the runner asked for, outside any training plan.

A plan is a commitment of weeks; sometimes a runner just wants today's session
— between blocks, on holiday, or as an extra on top of the plan they have. A
``SingleRun`` is that session: one generated workout on one calendar day, paced
from the runner's current fitness.

It deliberately has no ``training_plan_id``. The completed activity still
arrives through the normal Intervals.icu import as a ``RunLog``, which is what
the dashboards read; ``RunLog.single_run_id`` points back here so the run
mapper counts it as training load without ever spending it on a planned day.

The generated workout is stored whole (``workout``, the same day-dict shape as
a ``plan_data`` day) rather than rebuilt on read: the paces it was prescribed
at are part of the record, and a later fitness change must not rewrite a
session the runner has already been sent.
"""

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SingleRun(Base):
    __tablename__ = "single_runs"
    __table_args__ = (Index("idx_single_run_user_date", "user_id", "date"),)

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE")
    )
    # Calendar day the session is for (user-local). Imported as `date_type`
    # because a bare `date` here would resolve to this very column.
    date: Mapped[date_type] = mapped_column(Date)
    run_type: Mapped[str] = mapped_column(String(20))
    distance_km: Mapped[float] = mapped_column(Float)
    # The generated day dict: type, distance, description, structured steps.
    workout: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Fitness the paces were set from. NULL means there was none to read — the
    # session was prescribed by effort, and the page says so.
    vdot: Mapped[float | None] = mapped_column(Float)

    # Hash of the calendar event we last pushed; NULL until it has been sent.
    watch_event_hash: Mapped[str | None] = mapped_column(String(32))
    watch_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Intervals.icu's id for that event. An activity recorded from it comes
    # back carrying the same id, which is the one exact way to know a run was
    # this session. Replaced on every re-send (a re-send is delete + create).
    watch_event_id: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)

    user: Mapped["User"] = relationship("User", back_populates="single_runs")
