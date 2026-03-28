from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text

from app.models.base import Base


class TriathlonPlan(Base):
    __tablename__ = "triathlon_plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    distance = Column(String)       # 'sprint' | 'olympic' | 'half_ironman'
    weeks_duration = Column(Integer)
    plan_data = Column(Text)        # JSON list of weekly dicts
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
