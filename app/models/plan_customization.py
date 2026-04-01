from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class PlanCustomization(Base):
    __tablename__ = "plan_customizations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    training_plan_id = Column(String, ForeignKey("training_plans.id"), nullable=False, index=True)
    week_number = Column(Integer, nullable=False)
    adjustment_type = Column(String, nullable=False)
    adjustment_value = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
