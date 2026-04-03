from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Index
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        Index('idx_training_plan_user_id', 'user_id'),
        Index('idx_training_plan_created_at', 'created_at'),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    current_weekly_km = Column(Float)
    target_distance = Column(String)  # in km as string (e.g., "30.0" for Trail Running)
    weeks_duration = Column(Integer)
    max_runs_per_week = Column(Integer, default=4)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    plan_data = Column(Text)  # JSON string of the generated plan
    nutrition_plan_data = Column(Text)  # JSON string of the nutrition plan

    # Performance training fields
    plan_type = Column(String, default="distance")  # "distance" or "performance"
    current_pace = Column(Float)  # min/km
    goal_pace = Column(Float)  # min/km
    current_time = Column(String)  # formatted time string (e.g., "55:00")
    goal_time = Column(String)  # formatted time string (e.g., "50:00")

    # Heart rate training fields
    max_heart_rate = Column(Integer, nullable=True)  # Maximum heart rate in BPM
    start_date = Column(DateTime, nullable=True)
    # Unified adaptation multiplier (replaces strava_adapted_multiplier
    # and recalibration_multiplier which still exist in the DB but are no
    # longer mapped by SQLAlchemy — they will be removed in a future phase).
    adjustment_multiplier = Column(Float, nullable=True)

    # VDOT / pace zone fields
    body_weight_kg = Column(Float, nullable=True)
    recent_race_distance_km = Column(Float, nullable=True)
    recent_race_time_seconds = Column(Integer, nullable=True)
    vdot = Column(Float, nullable=True)

    # Heart rate zones (JSON: {max_hr, source, zones: [...]})
    hr_zones_data = Column(Text, nullable=True)

    # Phase-specific nutrition data (JSON)
    nutrition_phases_data = Column(Text, nullable=True)

    # Race-day protocol (JSON)
    race_protocol_data = Column(Text, nullable=True)

    # JSON schema version for plan_data / nutrition_plan_data / etc.
    # Increment when the JSON structure changes in a breaking way.
    CURRENT_SCHEMA_VERSION = 1
    plan_data_version = Column(Integer, default=CURRENT_SCHEMA_VERSION)

    # Shareable link token
    share_token = Column(String, unique=True, nullable=True, index=True)

    @property
    def target_distance_km(self) -> float:
        """Parse target_distance string to float, handling legacy values."""
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
