from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Index
from datetime import datetime
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
    created_at = Column(DateTime, default=datetime.utcnow)
    plan_data = Column(Text)  # JSON string of the generated plan
    nutrition_plan_data = Column(Text)  # JSON string of the nutrition plan
