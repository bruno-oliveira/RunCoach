from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text, Index
import uuid

from app.models.base import Base


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        Index('idx_weekly_plan_training_plan_id', 'training_plan_id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    training_plan_id = Column(String, ForeignKey("training_plans.id"))
    week_number = Column(Integer)
    total_km = Column(Float)
    workout_types = Column(Text)  # JSON string of workout distribution
