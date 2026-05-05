from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.orm import Mapped, relationship
from datetime import datetime, timezone
import uuid

from app.models.base import Base
from app.models.encrypted_type import EncryptedString


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
    age = Column(Integer, nullable=True)
    strava_athlete_id = Column(String, unique=True, nullable=True, index=True)
    strava_access_token = Column(EncryptedString, nullable=True)
    strava_refresh_token = Column(EncryptedString, nullable=True)
    strava_token_expires_at = Column(Integer, nullable=True)
    strava_last_synced_at = Column(Integer, nullable=True)

    training_plans: Mapped[list["TrainingPlan"]] = relationship("TrainingPlan", back_populates="user", cascade="all, delete-orphan")
    run_logs: Mapped[list["RunLog"]] = relationship("RunLog", back_populates="user", cascade="all, delete-orphan")
    favorite_recipes: Mapped[list["FavoriteRecipe"]] = relationship("FavoriteRecipe", back_populates="user", cascade="all, delete-orphan")
    readiness_logs: Mapped[list["ReadinessLog"]] = relationship("ReadinessLog", back_populates="user", cascade="all, delete-orphan")
