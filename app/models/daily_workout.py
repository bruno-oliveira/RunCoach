from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, Boolean, Index
import uuid

from app.models.base import Base


class DailyWorkout(Base):
    __tablename__ = "daily_workouts"
    __table_args__ = (
        Index('idx_daily_workout_weekly_plan_id', 'weekly_plan_id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    weekly_plan_id = Column(String, ForeignKey("weekly_plans.id"))
    day_of_week = Column(Integer)  # 1-7 (Monday-Sunday)
    workout_type = Column(String)  # 'easy', 'tempo', 'interval', 'long', 'rest', 'strength'
    distance_km = Column(Float)
    intensity = Column(String)  # 'low', 'medium', 'high'
    notes = Column(Text)
    is_customized = Column(Boolean, default=False)  # Track if workout was customized
    original_workout_type = Column(String)  # Store original type for reference
