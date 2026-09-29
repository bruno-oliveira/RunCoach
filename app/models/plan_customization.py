import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.training_plan import TrainingPlan


class PlanCustomization(Base):
    __tablename__ = "plan_customizations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    training_plan_id: Mapped[str] = mapped_column(
        String, ForeignKey("training_plans.id"), index=True
    )
    week_number: Mapped[int] = mapped_column(Integer)
    adjustment_type: Mapped[str] = mapped_column(String)
    adjustment_value: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)

    training_plan: Mapped["TrainingPlan"] = relationship("TrainingPlan")
