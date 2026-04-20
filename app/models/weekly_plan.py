from sqlalchemy import Column, String, Integer, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.types import JSON
import uuid

from app.models.base import Base


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        Index('idx_weekly_plan_training_plan_id', 'training_plan_id'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    training_plan_id = Column(String, ForeignKey("training_plans.id"), nullable=False)
    week_number = Column(Integer)
    total_km = Column(Float)
    workout_types = Column(JSON)

    training_plan: Mapped["TrainingPlan"] = relationship("TrainingPlan", back_populates="weekly_plans")
    daily_workouts: Mapped[list["DailyWorkout"]] = relationship("DailyWorkout", back_populates="weekly_plan", cascade="all, delete-orphan")
