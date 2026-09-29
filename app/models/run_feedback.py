"""Run feedback model — stores automated coaching feedback per logged run."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.run_log import RunLog
    from app.models.user import User


class RunFeedback(Base):
    __tablename__ = "run_feedback"
    __table_args__ = (
        Index("idx_run_feedback_run_log_id", "run_log_id"),
        Index("idx_run_feedback_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_log_id: Mapped[str] = mapped_column(String, ForeignKey("run_logs.id"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))

    pace_feedback: Mapped[str | None] = mapped_column(Text)
    hr_zone_feedback: Mapped[str | None] = mapped_column(Text)
    effort_feedback: Mapped[str | None] = mapped_column(Text)
    volume_feedback: Mapped[str | None] = mapped_column(Text)
    pattern_feedback: Mapped[str | None] = mapped_column(Text)

    overall_sentiment: Mapped[str] = mapped_column(String(10), default="info")

    planned_workout_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("daily_workouts.id")
    )

    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)

    run_log: Mapped["RunLog"] = relationship("RunLog", back_populates="feedback")
    user: Mapped["User"] = relationship("User")
