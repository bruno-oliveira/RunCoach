from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class TriathlonPlan(Base):
    __tablename__ = "triathlon_plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    distance = Column(String)
    weeks_duration = Column(Integer)
    plan_data = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user: Mapped["User"] = relationship("User", back_populates="triathlon_plans")
