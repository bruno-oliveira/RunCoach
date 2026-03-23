"""Run feedback model — stores automated coaching feedback per logged run."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.models.base import Base


class RunFeedback(Base):
    __tablename__ = "run_feedback"
    __table_args__ = (
        Index("idx_run_feedback_run_log_id", "run_log_id"),
        Index("idx_run_feedback_user_id", "user_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_log_id = Column(String, ForeignKey("run_logs.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Feedback categories — each nullable, populated only when applicable
    pace_feedback = Column(Text, nullable=True)
    hr_zone_feedback = Column(Text, nullable=True)
    effort_feedback = Column(Text, nullable=True)
    volume_feedback = Column(Text, nullable=True)
    pattern_feedback = Column(Text, nullable=True)

    # "positive", "warning", "info"
    overall_sentiment = Column(String(10), nullable=False, default="info")

    # Source of the planned workout comparison
    planned_workout_id = Column(
        String, ForeignKey("daily_workouts.id"), nullable=True
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
