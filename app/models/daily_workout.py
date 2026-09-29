import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.weekly_plan import WeeklyPlan


class DailyWorkout(Base):
    __tablename__ = "daily_workouts"
    __table_args__ = (Index("idx_daily_workout_weekly_plan_id", "weekly_plan_id"),)

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    weekly_plan_id: Mapped[str] = mapped_column(String, ForeignKey("weekly_plans.id"))
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    workout_type: Mapped[str | None] = mapped_column(String)
    distance_km: Mapped[float | None] = mapped_column(Float)
    intensity: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    coaching_rationale: Mapped[str | None] = mapped_column(Text)
    baseline_distance_km: Mapped[float | None] = mapped_column(Float)
    hr_zone_target: Mapped[int | None] = mapped_column(Integer)
    key_workout_id: Mapped[str | None] = mapped_column(String)

    weekly_plan: Mapped["WeeklyPlan"] = relationship(
        "WeeklyPlan", back_populates="daily_workouts"
    )
