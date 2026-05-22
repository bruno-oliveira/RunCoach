import uuid

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.models.base import Base


class DailyWorkout(Base):
    __tablename__ = "daily_workouts"
    __table_args__ = (Index("idx_daily_workout_weekly_plan_id", "weekly_plan_id"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    weekly_plan_id = Column(String, ForeignKey("weekly_plans.id"), nullable=False)
    day_of_week = Column(Integer)
    workout_type = Column(String)
    distance_km = Column(Float)
    intensity = Column(String)
    notes = Column(Text)
    coaching_rationale = Column(Text, nullable=True)
    baseline_distance_km = Column(Float, nullable=True)
    hr_zone_target = Column(Integer, nullable=True)
    key_workout_id = Column(String, nullable=True)

    weekly_plan: Mapped["WeeklyPlan"] = relationship(
        "WeeklyPlan", back_populates="daily_workouts"
    )
