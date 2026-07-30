import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    # Optional max heart rate (BPM). When set it anchors the top of the HR
    # zones directly; otherwise we detect it from run data, then fall back to an
    # age formula and a conservative default.
    max_hr = Column(Integer, nullable=True)
    # Optional resting heart rate (BPM). In the LTHR-anchored model it only
    # raises the Zone 1 (recovery) floor; left null we omit that refinement.
    resting_hr = Column(Integer, nullable=True)
    # Optional lactate-threshold heart rate (BPM). The primary zone anchor: the
    # Zone 3/4 edge sits on it. When null we estimate it from threshold-effort
    # runs, and failing that derive it from max HR (population-average 88%).
    threshold_hr = Column(Integer, nullable=True)
    intervals_athlete_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    intervals_access_token: Mapped[str | None] = mapped_column(
        EncryptedString(), nullable=True
    )
    intervals_last_synced_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # HR anchors as configured in Intervals.icu, refreshed on every sync. Kept
    # separate from the manual ``max_hr`` / ``threshold_hr`` / ``resting_hr``
    # above so a runner's own entry always wins and a re-sync never clobbers it;
    # these are the second source in the anchor-resolution order (see
    # ``hr_zone_service`` resolvers).
    intervals_max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intervals_lthr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intervals_resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When the runner confirmed they finished the two Intervals.icu toggles that
    # forward planned workouts to their watch. Those toggles live on a platform
    # we can't inspect, so this records what they told us — which is still far
    # better than firing a "sent!" toast at someone whose watch will stay empty.
    watch_setup_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # Outbound coaching nudges — the only surface that can reach a runner who
    # hasn't opened the app. Opt-in: these people signed up for a plan
    # generator, not a mailing list. The timestamp and signature are the rate
    # limit and the repeat guard; both live here rather than in memory so they
    # survive a restart and hold across however many machines run the job.
    nudge_email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    last_nudge_email_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_nudge_email_signature: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

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
    readiness_logs: Mapped[list["ReadinessLog"]] = relationship(
        "ReadinessLog", back_populates="user", cascade="all, delete-orphan"
    )
