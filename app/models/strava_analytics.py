from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON as SQLAlchemyJSON
from sqlalchemy.orm import relationship

from app.models.base import Base


class StravaAnalytics(Base):
    __tablename__ = "strava_analytics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    total_activities = Column(Integer, default=0)
    summary_data = Column(SQLAlchemyJSON, nullable=True)

    activities = relationship("StravaActivity", back_populates="analytics", cascade="all, delete-orphan")


class StravaActivity(Base):
    __tablename__ = "strava_activities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analytics_id = Column(String, ForeignKey("strava_analytics.id", ondelete="CASCADE"), nullable=False)

    activity_id = Column(String)
    date = Column(DateTime)
    activity_type = Column(String)
    distance_km = Column(Integer, nullable=True)
    moving_time_seconds = Column(Integer, nullable=True)
    elapsed_time_seconds = Column(Integer, nullable=True)

    avg_speed = Column(Integer, nullable=True)
    max_speed = Column(Integer, nullable=True)
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)

    elevation_gain_meters = Column(Integer, nullable=True)
    elevation_loss_meters = Column(Integer, nullable=True)

    calories = Column(Integer, nullable=True)

    raw_data = Column(SQLAlchemyJSON, nullable=True)

    analytics = relationship("StravaAnalytics", back_populates="activities")