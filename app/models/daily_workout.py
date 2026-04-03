from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, Index
import uuid

from app.models.base import Base


class DailyWorkout(Base):
    __tablename__ = "daily_workouts"
    __table_args__ = (
        Index('idx_daily_workout_weekly_plan_id', 'weekly_plan_id'),
        Index('idx_daily_workout_plan_day', 'weekly_plan_id', 'day_of_week'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    weekly_plan_id = Column(String, ForeignKey("weekly_plans.id"), nullable=False)
    day_of_week = Column(Integer)  # 1-7 (Monday-Sunday)
    workout_type = Column(String)  # 'easy', 'tempo', 'interval', 'long', 'rest', 'strength'
    distance_km = Column(Float)
    intensity = Column(String)  # 'low', 'medium', 'high'
    notes = Column(Text)
    coaching_rationale = Column(Text, nullable=True)
    baseline_distance_km = Column(Float, nullable=True)
    hr_zone_target = Column(Integer, nullable=True)  # Target HR zone (1-5)
    key_workout_id = Column(String, nullable=True)  # ID from KeyWorkoutLibrary
