import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.training.workout_inference import resolve_effective_workout_type
from app.models.base import Base

# Runs the runner entered by hand; anything else came from a connected platform.
MANUAL_SOURCE = "manual"
INTERVALS_SOURCE = "intervals"


class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = (
        Index("idx_run_log_user_id", "user_id"),
        Index("idx_run_log_date", "date"),
        Index("idx_run_log_user_date", "user_id", "date"),
        Index("idx_run_log_training_plan", "training_plan_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    training_plan_id = Column(String, ForeignKey("training_plans.id"), nullable=True)
    daily_workout_id = Column(String, ForeignKey("daily_workouts.id"), nullable=True)
    date = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    distance_km = Column(Float)
    duration_minutes = Column(Float)
    avg_pace_min_km = Column(Float)
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)
    avg_cadence = Column(Integer, nullable=True)
    elevation_gain_m = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    workout_type = Column(String, nullable=True)
    perceived_effort = Column(Integer, nullable=True)
    intervals_activity_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    # Where the run came from: "intervals", "manual", or "strava" for history
    # imported before that integration was retired. Read via `was_imported`.
    source = Column(String(20), nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    effort_quality_score = Column(Float, nullable=True)
    quality_label = Column(String(20), nullable=True)
    planned_pace_min_km = Column(Float, nullable=True)
    vdot = Column(Float, nullable=True)
    predicted_time_seconds = Column(Float, nullable=True)
    hr_zone_deviation = Column(Integer, nullable=True)
    effort_class = Column(String(20), nullable=True)

    # Run type inferred from pace/HR/distance/splits. Kept separate from the
    # raw `workout_type` (which imports default to "easy") so the user's own
    # tag is never overwritten; reconciled at read time via the property below.
    inferred_workout_type = Column(String(20), nullable=True)
    inferred_type_confidence = Column(Float, nullable=True)
    # Compact per-km splits: [{km, duration_s, pace_min_km, avg_hr}].
    splits = Column(JSON, nullable=True)

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
