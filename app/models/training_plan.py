import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.weekly_plan import WeeklyPlan


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        Index("idx_training_plan_user_id", "user_id"),
        Index("idx_training_plan_created_at", "created_at"),
        Index("idx_training_plan_follows_plan_id", "follows_plan_id"),
    )
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    current_weekly_km: Mapped[float | None] = mapped_column(Float)
    target_distance: Mapped[str | None] = mapped_column(String)
    weeks_duration: Mapped[int | None] = mapped_column(Integer)
    max_runs_per_week: Mapped[int | None] = mapped_column(Integer, default=4)
    frequency_composer: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)
    plan_data: Mapped[Any | None] = mapped_column(JSON)
    nutrition_plan_data: Mapped[Any | None] = mapped_column(JSON)

    plan_type: Mapped[str | None] = mapped_column(String, default="distance")
    current_pace: Mapped[float | None] = mapped_column(Float)
    goal_pace: Mapped[float | None] = mapped_column(Float)
    current_time: Mapped[str | None] = mapped_column(String)
    goal_time: Mapped[str | None] = mapped_column(String)

    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    adjustment_multiplier: Mapped[float | None] = mapped_column(Float)

    body_weight_kg: Mapped[float | None] = mapped_column(Float)
    recent_race_distance_km: Mapped[float | None] = mapped_column(Float)
    recent_race_time_seconds: Mapped[int | None] = mapped_column(Integer)
    vdot: Mapped[float | None] = mapped_column(Float)
    # The runner's measured easy pace the easy band was built around; NULL
    # while there is none, and the band is then the one ``vdot`` implies.
    easy_pace_min_km: Mapped[float | None] = mapped_column(Float)

    # Trail / ultra parameters (replaces the legacy `terrain` request field).
    is_trail: Mapped[bool] = mapped_column(Boolean, default=False)
    target_elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    training_terrain: Mapped[str | None] = mapped_column(String)

    # Backyard ultra parameters. A backyard goal is a loop count, not a distance:
    # `target_distance` / `target_elevation_gain_m` hold the ultra projection
    # the engine periodises against (see BackyardProfile), and these three
    # columns hold what the runner actually signed up for. They are what every
    # display surface should read — the projection is an implementation detail
    # and is clamped, so it does not round-trip to a loop count.
    is_backyard: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    backyard_target_loops: Mapped[int | None] = mapped_column(Integer)
    backyard_loop_km: Mapped[float | None] = mapped_column(Float)
    backyard_loop_elevation_gain_m: Mapped[float | None] = mapped_column(Float)

    hr_zones_data: Mapped[Any | None] = mapped_column(JSON)
    nutrition_phases_data: Mapped[Any | None] = mapped_column(JSON)
    race_protocol_data: Mapped[Any | None] = mapped_column(JSON)

    CURRENT_SCHEMA_VERSION = 1
    plan_data_version: Mapped[int | None] = mapped_column(
        Integer, default=CURRENT_SCHEMA_VERSION
    )

    adaptation_history: Mapped[Any | None] = mapped_column(JSON)
    last_adjusted_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_recalibrated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_change_plan: Mapped[Any | None] = mapped_column(JSON)
    # Last proactive adaptation nudge surfaced to the user (suggest-only). Shape:
    # {"signature": str, "kind": str, "dismissed": bool, ...}. A nudge is only
    # re-shown when its signature changes, so a dismissed suggestion stays quiet
    # until the underlying situation materially moves.
    last_proactive_nudge: Mapped[Any | None] = mapped_column(JSON)
    # Write-through cache for the AI Coach's Note: {"signature": str, "payload": dict}.
    # Regenerated only when the run signature changes (a new run is logged), so the
    # note survives scale-to-zero cold starts instead of being rebuilt each wake.
    coach_note_cache: Mapped[Any | None] = mapped_column(JSON)
    # Monotonic counter bumped on every distance-mutating apply. Clients send
    # the revision they rendered with so the server can reject stale writes.
    adaptation_revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    # When we last mirrored this plan onto the athlete's Intervals.icu calendar.
    # Display only — `watch_sync_enabled` is what authorises a mirror.
    watch_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    # The runner's standing "keep my watch in sync" opt-in, set on the first
    # send. It authorises the reconciler to create *and delete* events on their
    # calendar, so an adaptation reaches the wrist instead of leaving the watch
    # beeping out a session we've since changed.
    watch_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    # {external_id: hash of the event body we last pushed}. Two jobs: it makes
    # re-mirroring idempotent (unchanged days cost no API writes), and it is our
    # record of which calendar events are ours — the only events the reconciler
    # is ever allowed to delete.
    watch_event_hashes: Mapped[Any | None] = mapped_column(JSON)
    # Why the last mirror failed ("auth" | "provider"), or None when it worked.
    # The mirror runs in the background, so without this a revoked token is just
    # a log line and a watch that quietly stops updating.
    watch_sync_error: Mapped[str | None] = mapped_column(String)
    # The plan this one follows on from — set on a recovery block, pointing at
    # the race plan it was built from. Not a foreign key: deleting the race plan
    # leaves the block standing, and ``delete_plan`` clears the pointer.
    follows_plan_id: Mapped[str | None] = mapped_column(String)
    share_token: Mapped[str | None] = mapped_column(String, unique=True, index=True)

    user: Mapped["User"] = relationship("User", back_populates="training_plans")
    weekly_plans: Mapped[list["WeeklyPlan"]] = relationship(
        "WeeklyPlan", back_populates="training_plan", cascade="all, delete-orphan"
    )

    def backyard_profile(self):
        """Rebuild the stored backyard goal, or ``None`` for other plans.

        Returns a :class:`~app.core.training.backyard_profile.BackyardProfile`.
        Imported lazily so the ORM layer carries no import-time dependency on
        the training core.
        """
        if not self.is_backyard or not self.backyard_target_loops:
            return None
        from app.core.training.profiles.backyard_profile import (
            BACKYARD_LOOP_KM,
            classify_backyard,
        )

        return classify_backyard(
            int(self.backyard_target_loops),
            float(self.backyard_loop_km or BACKYARD_LOOP_KM),
            float(self.backyard_loop_elevation_gain_m or 0.0),
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
