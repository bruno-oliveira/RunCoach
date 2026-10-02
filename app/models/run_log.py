import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.core.training.physiology.workout_inference import (
    resolve_effective_workout_type,
)
from app.models.base import Base

# Runs the runner entered by hand; anything else came from a connected platform.
MANUAL_SOURCE = "manual"
INTERVALS_SOURCE = "intervals"


if TYPE_CHECKING:
    from app.models.daily_workout import DailyWorkout
    from app.models.run_feedback import RunFeedback
    from app.models.training_plan import TrainingPlan
    from app.models.user import User


class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = (
        Index("idx_run_log_user_id", "user_id"),
        Index("idx_run_log_date", "date"),
        Index("idx_run_log_user_date", "user_id", "date"),
        Index("idx_run_log_training_plan", "training_plan_id"),
        Index("idx_run_log_single_run", "single_run_id"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    training_plan_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("training_plans.id")
    )
    daily_workout_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("daily_workouts.id")
    )
    # Set when this activity completed a one-off `SingleRun`. The run mapper
    # reads it to keep the run out of day-matching (it still counts as weekly
    # volume). A plain pointer, not a foreign key — see migration 035.
    single_run_id: Mapped[str | None] = mapped_column(String)
    date: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)
    distance_km: Mapped[float | None] = mapped_column(Float)
    duration_minutes: Mapped[float | None] = mapped_column(Float)
    avg_pace_min_km: Mapped[float | None] = mapped_column(Float)
    avg_heart_rate: Mapped[int | None] = mapped_column(Integer)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    avg_cadence: Mapped[int | None] = mapped_column(Integer)
    elevation_gain_m: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    workout_type: Mapped[str | None] = mapped_column(String)
    perceived_effort: Mapped[int | None] = mapped_column(Integer)
    intervals_activity_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    # The Intervals.icu calendar event this activity was recorded against, when
    # the runner ran it from a session we sent to their watch.
    intervals_paired_event_id: Mapped[str | None] = mapped_column(String)
    # Where the run came from: "intervals", "manual", or "strava" for history
    # imported before that integration was retired. Read via `was_imported`.
    source: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)

    effort_quality_score: Mapped[float | None] = mapped_column(Float)
    quality_label: Mapped[str | None] = mapped_column(String(20))
    planned_pace_min_km: Mapped[float | None] = mapped_column(Float)
    vdot: Mapped[float | None] = mapped_column(Float)
    predicted_time_seconds: Mapped[float | None] = mapped_column(Float)
    hr_zone_deviation: Mapped[int | None] = mapped_column(Integer)
    effort_class: Mapped[str | None] = mapped_column(String(20))

    # Run type inferred from pace/HR/distance/splits. Kept separate from the
    # raw `workout_type` (which imports default to "easy") so the user's own
    # tag is never overwritten; reconciled at read time via the property below.
    inferred_workout_type: Mapped[str | None] = mapped_column(String(20))
    inferred_type_confidence: Mapped[float | None] = mapped_column(Float)
    # Compact per-km splits: [{km, duration_s, pace_min_km, avg_hr}].
    splits: Mapped[Any | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship("User", back_populates="run_logs")
    training_plan: Mapped["TrainingPlan"] = relationship("TrainingPlan")
    daily_workout: Mapped["DailyWorkout"] = relationship("DailyWorkout")
    feedback: Mapped["RunFeedback"] = relationship(
        "RunFeedback", uselist=False, back_populates="run_log"
    )

    @property
    def was_imported(self) -> bool:
        """Whether a connected platform supplied this run rather than the runner.

        Rows predating the `source` column are identified by their provider id,
        which is what the backfill keyed on.
        """
        if self.source is not None:
            return self.source != MANUAL_SOURCE
        return self.intervals_activity_id is not None

    @property
    def effective_workout_type(self) -> "str | None":
        """Best available workout type: explicit tag or inference.

        Imported runs arrive untagged or defaulted to "easy"; this prefers the
        inferred type for those while never overriding a deliberate label —
        the runner's own, or a meaningful race/long/interval tag that came with
        the activity. Consumers that bucket logged runs by type should read
        this, not `workout_type`.
        """
        return resolve_effective_workout_type(
            self.workout_type,
            self.inferred_workout_type,
            is_imported=self.was_imported,
            confidence=self.inferred_type_confidence,
        )
