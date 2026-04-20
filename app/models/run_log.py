from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, relationship
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = (
        Index('idx_run_log_user_id', 'user_id'),
        Index('idx_run_log_date', 'date'),
        Index('idx_run_log_user_date', 'user_id', 'date'),
        Index('idx_run_log_training_plan', 'training_plan_id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    training_plan_id = Column(String, ForeignKey("training_plans.id"), nullable=True)
    daily_workout_id = Column(String, ForeignKey("daily_workouts.id"), nullable=True)
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    distance_km = Column(Float)
    duration_minutes = Column(Float)
    avg_pace_min_km = Column(Float)
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)
    avg_cadence = Column(Integer, nullable=True)
    elevation_gain_m = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    workout_type = Column(String, nullable=True)
    perceived_effort = Column(Integer, nullable=True)
    strava_activity_id = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    effort_quality_score = Column(Float, nullable=True)
    quality_label = Column(String(20), nullable=True)
    planned_pace_min_km = Column(Float, nullable=True)
    vdot = Column(Float, nullable=True)
    predicted_time_seconds = Column(Float, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="run_logs")
    training_plan: Mapped["TrainingPlan"] = relationship("TrainingPlan")
    daily_workout: Mapped["DailyWorkout"] = relationship("DailyWorkout")
    feedback: Mapped["RunFeedback"] = relationship("RunFeedback", uselist=False, back_populates="run_log")
