from sqlalchemy import Column, String, DateTime, Integer
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_activity = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=True)
    plans_generated = Column(Integer, default=0)
    age = Column(Integer, nullable=True)  # Age for max heart rate calculation
    strava_athlete_id = Column(String, unique=True, nullable=True, index=True)
    strava_access_token = Column(String, nullable=True)
    strava_refresh_token = Column(String, nullable=True)
    strava_token_expires_at = Column(Integer, nullable=True)  # Unix epoch
