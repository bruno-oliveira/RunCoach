import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.daily_workout import DailyWorkout
    from app.models.training_plan import TrainingPlan


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (Index("idx_weekly_plan_training_plan_id", "training_plan_id"),)

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    training_plan_id: Mapped[str] = mapped_column(
        String, ForeignKey("training_plans.id")
    )
    week_number: Mapped[int | None] = mapped_column(Integer)
    total_km: Mapped[float | None] = mapped_column(Float)
    workout_types: Mapped[Any | None] = mapped_column(JSON)
    pace_zones_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    training_plan: Mapped["TrainingPlan"] = relationship(
        "TrainingPlan", back_populates="weekly_plans"
    )
    daily_workouts: Mapped[list["DailyWorkout"]] = relationship(
        "DailyWorkout", back_populates="weekly_plan", cascade="all, delete-orphan"
    )
