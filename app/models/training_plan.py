import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        Index("idx_training_plan_user_id", "user_id"),
        Index("idx_training_plan_created_at", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    current_weekly_km = Column(Float)
    target_distance = Column(String)
    weeks_duration = Column(Integer)
    max_runs_per_week = Column(Integer, default=4)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    plan_data = Column(JSON)
    nutrition_plan_data = Column(JSON)

    plan_type = Column(String, default="distance")
    current_pace = Column(Float)
    goal_pace = Column(Float)
    current_time = Column(String)
    goal_time = Column(String)

    max_heart_rate = Column(Integer, nullable=True)
    start_date = Column(DateTime, nullable=True)
    adjustment_multiplier = Column(Float, nullable=True)

    body_weight_kg = Column(Float, nullable=True)
    recent_race_distance_km = Column(Float, nullable=True)
    recent_race_time_seconds = Column(Integer, nullable=True)
    vdot = Column(Float, nullable=True)

    # Trail / ultra parameters (replaces the legacy `terrain` request field).
    is_trail = Column(Boolean, nullable=False, default=False)
    target_elevation_gain_m = Column(Float, nullable=True)
    training_terrain = Column(String, nullable=True)

    hr_zones_data = Column(JSON, nullable=True)
    nutrition_phases_data = Column(JSON, nullable=True)
    race_protocol_data = Column(JSON, nullable=True)

    CURRENT_SCHEMA_VERSION = 1
    plan_data_version = Column(Integer, default=CURRENT_SCHEMA_VERSION)

    adaptation_history = Column(JSON, nullable=True)
    last_adjusted_at = Column(DateTime, nullable=True)
    last_recalibrated_at = Column(DateTime, nullable=True)
    last_change_plan = Column(JSON, nullable=True)
    # Last proactive adaptation nudge surfaced to the user (suggest-only). Shape:
    # {"signature": str, "kind": str, "dismissed": bool, ...}. A nudge is only
    # re-shown when its signature changes, so a dismissed suggestion stays quiet
    # until the underlying situation materially moves.
    last_proactive_nudge = Column(JSON, nullable=True)
    # Write-through cache for the AI Coach's Note: {"signature": str, "payload": dict}.
    # Regenerated only when the run signature changes (a new run is logged), so the
    # note survives scale-to-zero cold starts instead of being rebuilt each wake.
    coach_note_cache = Column(JSON, nullable=True)
    # Monotonic counter bumped on every distance-mutating apply. Clients send
    # the revision they rendered with so the server can reject stale writes.
    adaptation_revision = Column(Integer, nullable=False, default=0, server_default="0")
    # When we last mirrored this plan onto the athlete's Intervals.icu calendar.
    # Display only — `watch_sync_enabled` is what authorises a mirror.
    watch_synced_at = Column(DateTime, nullable=True)
    # The runner's standing "keep my watch in sync" opt-in, set on the first
    # send. It authorises the reconciler to create *and delete* events on their
    # calendar, so an adaptation reaches the wrist instead of leaving the watch
    # beeping out a session we've since changed.
    watch_sync_enabled = Column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # {external_id: hash of the event body we last pushed}. Two jobs: it makes
    # re-mirroring idempotent (unchanged days cost no API writes), and it is our
    # record of which calendar events are ours — the only events the reconciler
    # is ever allowed to delete.
    watch_event_hashes = Column(JSON, nullable=True)
    # Why the last mirror failed ("auth" | "provider"), or None when it worked.
    # The mirror runs in the background, so without this a revoked token is just
    # a log line and a watch that quietly stops updating.
    watch_sync_error = Column(String, nullable=True)
    share_token = Column(String, unique=True, nullable=True, index=True)

    user: Mapped["User"] = relationship("User", back_populates="training_plans")
    weekly_plans: Mapped[list["WeeklyPlan"]] = relationship(
        "WeeklyPlan", back_populates="training_plan", cascade="all, delete-orphan"
    )

    @property
    def target_distance_km(self) -> float:
        if self.target_distance is None:
            return 0.0
        try:
            if isinstance(self.target_distance, (int, float)):
                return float(self.target_distance)
            if self.target_distance.lower() == "trail":
                return 30.0
            return float(self.target_distance)
        except (ValueError, AttributeError):
            return 0.0
