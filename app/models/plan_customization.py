from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class PlanCustomization(Base):
    __tablename__ = "plan_customizations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    training_plan_id = Column(String, ForeignKey("training_plans.id"), index=True)
    week_number = Column(Integer)
    adjustment_type = Column(String)
    adjustment_value = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
