from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Index, Boolean
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        Index('idx_training_plan_user_id', 'user_id'),
        Index('idx_training_plan_created_at', 'created_at'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    current_weekly_km = Column(Float)
    target_distance = Column(String)  # in km as string (e.g., "30.0" for Trail Running)
    weeks_duration = Column(Integer)
    max_runs_per_week = Column(Integer, default=4)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    plan_data = Column(Text)  # JSON string of the generated plan
    nutrition_plan_data = Column(Text)  # JSON string of the nutrition plan

    # Performance training fields
    plan_type = Column(String, default="distance")  # "distance" or "performance"
    current_pace = Column(Float)  # min/km
    goal_pace = Column(Float)  # min/km
    current_time = Column(String)  # formatted time string (e.g., "55:00")
    goal_time = Column(String)  # formatted time string (e.g., "50:00")

    # Heart rate training fields
    max_heart_rate = Column(Integer, nullable=True)  # Maximum heart rate in BPM
    resting_heart_rate = Column(Integer, nullable=True)  # Resting heart rate in BPM (for future Karvonen method)
    hr_zone_method = Column(String, default="simple_percent")  # HR zone calculation method
    start_date = Column(DateTime, nullable=True)
    # Tracks the last Strava-fitness multiplier applied so re-runs can reverse it
    strava_adapted_multiplier = Column(Float, nullable=True)
