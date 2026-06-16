import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Mapped, relationship

from app.models.base import Base
from app.models.encrypted_type import EncryptedString


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    last_activity = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=True,
    )
    plans_generated = Column(Integer, default=0)
    age = Column(Integer, nullable=True)
    # Optional resting heart rate (BPM). Enables Heart Rate Reserve (Karvonen)
    # zone math; when null we estimate from run data or fall back to %max HR.
    resting_hr = Column(Integer, nullable=True)
    # Optional lactate-threshold heart rate (BPM). When set, the zone bands are
    # re-anchored so the threshold (Zone 3/4) edge equals it; when null we
    # estimate it from threshold-effort runs or leave the formula bands as-is.
    threshold_hr = Column(Integer, nullable=True)
    strava_athlete_id = Column(String, unique=True, nullable=True, index=True)
    strava_access_token = Column(EncryptedString, nullable=True)
    strava_refresh_token = Column(EncryptedString, nullable=True)
    strava_token_expires_at = Column(Integer, nullable=True)
    strava_last_synced_at = Column(Integer, nullable=True)

    training_plans: Mapped[list["TrainingPlan"]] = relationship(
        "TrainingPlan", back_populates="user", cascade="all, delete-orphan"
    )
    run_logs: Mapped[list["RunLog"]] = relationship(
        "RunLog", back_populates="user", cascade="all, delete-orphan"
    )
    favorite_recipes: Mapped[list["FavoriteRecipe"]] = relationship(
        "FavoriteRecipe", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
