"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES, WORKOUT_TYPES
from app.exceptions import InadequateBaseException, InsufficientTimeException, ZeroMileageUnsupportedException
from app.utils import format_pace_bare


def parse_target_distance(value: str | float) -> float:
    """
    Convert target_distance from database (string) to float.
    Handles legacy "trail" values by converting to 30.0.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if value.lower() == "trail":
        return 30.0
    return float(value)


_MILEAGE_CONFIG = {
    5.0: {
        "min": settings.min_mileage_5k,
        "max": 40,
        "low_msg": (
            "Your current mileage is quite low for 5K training. "
            "Consider building a base with 2-3 weeks of easy running first."
        ),
        "high_msg": (
            "You're already running high mileage for 5K. "
            "Consider focusing on speed work rather than volume."
        ),
    },
    10.0: {
        "min": settings.min_mileage_10k,
        "max": 50,
        "low_msg": (
            "Your current mileage may be insufficient for 10K training. "
            "Build to at least 10km/week for 2-3 weeks first."
        ),
        "high_msg": (
            "High mileage for 10K. "
            "You might benefit from focusing on quality over quantity."
        ),
    },
    21.1: {
        "min": settings.min_mileage_half,
        "max": 70,
        "low_msg": (
            "Half marathon training requires a stronger base. "
            "Build to 15km/week for 3-4 weeks before starting."
        ),
        "high_msg": (
            "Very high mileage for half marathon. "
            "Ensure adequate recovery and consider periodization."
        ),
    },
    30.0: {
        "min": settings.min_mileage_30k,
        "max": 60,
        "low_msg": (
            "Trail running requires good base fitness. "
            "Build to 8km/week with some trail experience first."
        ),
        "high_msg": (
            "High mileage for trail running. "
            "Focus on time on feet rather than distance."
        ),
    },
    42.2: {
        "min": settings.min_mileage_marathon,
        "max": 100,
        "low_msg": (
            "Marathon training requires significant base fitness. "
            "Build to 25km/week for 4-6 weeks before beginning."
        ),
        "high_msg": (
            "Extremely high mileage. "
            "Be cautious about injury risk and ensure proper recovery."
        ),
    },
}


class PlanRequest(BaseModel):
    """Request schema for generating a training plan."""

    current_km: float = Field(
        ..., ge=0, le=200, description="Current weekly mileage in km"
    )
    target_distance: float = Field(
        ..., description="Target race distance in km (30.0 = Trail Running)"
    )
    weeks: int = Field(..., ge=4, le=24, description="Training duration in weeks")
    max_runs_per_week: int = Field(default=4, ge=3, le=6, description="Maximum runs per week")

    # Body weight — used for personalised nutrition
    body_weight_kg: float = Field(
        default=70.0, ge=30.0, le=250.0, description="Body weight in kg"
    )

    # Optional: recent race result for VDOT-based pace zones
    recent_race_distance_km: Optional[float] = Field(
        default=None, description="Recent race distance in km (for VDOT calculation)"
    )
    recent_race_time: Optional[str] = Field(
        default=None, description="Recent race finish time (HH:MM:SS or MM:SS)"
    )

    # Auto-computed from race result — not a user input
    vdot: Optional[float] = Field(default=None, exclude=True)

    @field_validator("target_distance")
    @classmethod
    def validate_target_distance(cls, v: float) -> float:
        """Validate that target distance is a supported race distance."""
        if v not in SUPPORTED_DISTANCES:
            valid_names = [DISTANCE_NAMES[d] for d in SUPPORTED_DISTANCES]
            raise ValueError(f"Please select a valid distance: {', '.join(valid_names)}")
        return v

    @model_validator(mode="after")
    def validate_weeks_for_distance(self) -> "PlanRequest":
        """Validate that training duration is appropriate for target distance."""
        target = self.target_distance
        weeks = self.weeks

        min_weeks_requirements = {
            5.0: (
                settings.min_weeks_5k,
                "4 weeks provides a solid foundation for 5K improvement",
            ),
            10.0: (
                settings.min_weeks_10k,
                "6 weeks allows for proper 10K preparation",
            ),
            21.1: (
                settings.min_weeks_half,
                "Half marathon training needs time to build endurance safely",
            ),
            30.0: (
                settings.min_weeks_30k,
                "Trail running requires building strength and technical skills over time",
            ),
            42.2: (
                settings.min_weeks_marathon,
                "Marathon training requires adequate time to prevent injury",
            ),
        }

        max_weeks_requirements = {
            5.0: (settings.max_weeks_5k, "Training beyond 16 weeks for 5K can lead to burnout"),
            10.0: (settings.max_weeks_10k, "16 weeks is optimal for 10K preparation"),
            21.1: (
                settings.max_weeks_half,
                "Half marathon training beyond 20 weeks may cause fatigue",
            ),
            30.0: (
                settings.max_weeks_30k,
                "Trail running training beyond 20 weeks may cause fatigue",
            ),
            42.2: (
                settings.max_weeks_marathon,
                "24 weeks is the maximum recommended for marathon training",
            ),
        }

        if target in min_weeks_requirements:
            min_weeks, reason = min_weeks_requirements[target]
            if weeks < min_weeks:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise InsufficientTimeException(
                    f"Training for {target_display} requires at least {min_weeks} weeks",
                    f"Consider extending your training to {min_weeks} weeks. {reason}",
                )

        if target in max_weeks_requirements:
            max_weeks, reason = max_weeks_requirements[target]
            if weeks > max_weeks:
                raise ValueError(f"{reason}. Consider a shorter training period.")

        return self

    @field_validator("max_runs_per_week")
    @classmethod
    def validate_runs_per_week(cls, v: int, info) -> int:
        """Validate max runs per week based on target distance."""
        values = info.data if isinstance(info.data, dict) else {}
        target_distance = values.get("target_distance")

        if target_distance:
            if target_distance >= 30.0 and v < 4:
                distance_name = DISTANCE_NAMES.get(target_distance, f"{target_distance}km")
                raise ValueError(
                    f"{distance_name} training typically requires at least 4 runs per week. "
                    f"Consider 4-5 runs per week for {distance_name.lower()} preparation."
                )
        return v

    @model_validator(mode="after")
    def validate_current_mileage(self) -> "PlanRequest":
        """Validate that current mileage is appropriate for target distance."""
        target = self.target_distance
        current_km = self.current_km
        weeks = self.weeks

        if current_km == 0:
            supported_distances = [5.0, 10.0]
            if target not in supported_distances:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise ZeroMileageUnsupportedException(
                    f"Starting from zero for {target_display} is not recommended.",
                    f"Starting from zero mileage for a {target_display} requires building a running base first. "
                    f"Consider training for a 5K or 10K first to build your fitness foundation."
                )
            
            if weeks < 8:
                raise InsufficientTimeException(
                    "Beginner plans require at least 8 weeks for safe progression.",
                    "Couch to 5K programs need 8+ weeks to build fitness safely. "
                    "Consider extending your training to at least 8 weeks."
                )
            
            return self

        if target in _MILEAGE_CONFIG:
            req = _MILEAGE_CONFIG[target]

            if current_km < req["min"]:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise InadequateBaseException(
                    f"Current mileage ({current_km}km/week) is below recommended "
                    f"minimum ({req['min']}km/week) for {target_display} training",
                    req["low_msg"],
                )

        return self

    @model_validator(mode="after")
    def compute_vdot(self) -> "PlanRequest":
        """Calculate VDOT from optional race result."""
        if self.recent_race_distance_km and self.recent_race_time:
            from app.core.vdot_calculator import VDOTCalculator
            seconds = VDOTCalculator.parse_time_to_seconds(self.recent_race_time)
            if seconds and seconds > 0:
                self.vdot = VDOTCalculator.calculate_vdot(
                    self.recent_race_distance_km, seconds
                )
        return self


# Response schemas
class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = Field(default_factory=lambda: settings.app_version)


# Helper functions for mileage warnings
def get_mileage_warning(target_distance: float, current_km: float) -> Optional[str]:
    """Get warning message if mileage is unusually high for target distance."""
    if target_distance in _MILEAGE_CONFIG:
        cfg = _MILEAGE_CONFIG[target_distance]
        if current_km > cfg["max"]:
            return cfg["high_msg"]
    return None


# Authentication schemas
class UserBase(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None


class UserCreate(UserBase):
    google_id: str


class UserResponse(UserBase):
    id: str
    google_id: Optional[str] = None
    created_at: datetime
    plans_generated: int
    strava_connected: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Google OAuth ID token")


# Run logging schemas
class RunLogBase(BaseModel):
    distance_km: float = Field(..., gt=0, description="Distance in kilometers")
    duration_minutes: float = Field(..., gt=0, description="Duration in minutes")
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=220, description="Average heart rate")
    max_heart_rate: Optional[int] = Field(None, ge=40, le=220, description="Maximum heart rate")
    avg_cadence: Optional[int] = Field(None, ge=100, le=220, description="Average cadence (steps per minute)")
    elevation_gain_m: Optional[int] = Field(None, ge=0, description="Elevation gain in meters")
    notes: Optional[str] = Field(None, max_length=1000, description="Run notes")
    workout_type: Optional[str] = Field(None, description="Workout type: easy, tempo, interval, long, hill")
    perceived_effort: Optional[int] = Field(None, ge=1, le=10, description="Perceived effort (1-10)")

    @field_validator("workout_type")
    @classmethod
    def validate_workout_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if v not in WORKOUT_TYPES:
                raise ValueError(f"workout_type must be one of: {', '.join(WORKOUT_TYPES)}")
        return v


class RunLogCreate(RunLogBase):
    date: Optional[datetime] = Field(None, description="Run date and time (defaults to now)")
    training_plan_id: Optional[str] = Field(None, description="Associated training plan ID")
    daily_workout_id: Optional[str] = Field(None, description="Associated daily workout ID")


class RunLogUpdate(BaseModel):
    distance_km: Optional[float] = Field(None, gt=0, le=1000)
    duration_minutes: Optional[float] = Field(None, gt=0, le=6000)
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    max_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    avg_cadence: Optional[int] = Field(None, ge=100, le=220)
    elevation_gain_m: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=1000)
    workout_type: Optional[str] = Field(None)
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    date: Optional[datetime] = None

    @field_validator("workout_type")
    @classmethod
    def validate_workout_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if v not in WORKOUT_TYPES:
                raise ValueError(f"workout_type must be one of: {', '.join(WORKOUT_TYPES)}")
        return v


class RunLogResponse(RunLogBase):
    id: str
    user_id: str
    date: datetime
    avg_pace_min_km: Optional[float] = None
    strava_activity_id: Optional[str] = None
    effort_quality_score: Optional[float] = None
    quality_label: Optional[str] = None
    vdot: Optional[float] = None
    predicted_time_seconds: Optional[float] = None
    created_at: datetime
    # Dynamically populated fields (not from DB)
    predictions: Optional[Dict[str, Dict]] = None
    race_comparison: Optional[Dict[str, Any]] = None


class RunLogListResponse(BaseModel):
    runs: List[RunLogResponse]
    total: int
    page: int
    page_size: int



class PerformancePlanRequest(BaseModel):
    """Request schema for generating a performance training plan."""

    target_distance: float = Field(
        ..., description="Target race distance in km"
    )
    current_pace: Optional[float] = Field(
        None, ge=2.5, le=10.0, description="Current pace in min/km (auto-calculated if not provided)"
    )
    goal_pace: float = Field(
        ..., ge=2.5, le=10.0, description="Goal race pace in min/km"
    )
    current_time: Optional[str] = Field(
        None, description="Current finish time (HH:MM:SS or MM:SS)"
    )
    goal_time: str = Field(
        ..., description="Goal finish time (HH:MM:SS or MM:SS)"
    )
    weeks: int = Field(
        ..., ge=6, le=16, description="Training duration in weeks (6-16)"
    )
    current_weekly_km: Optional[float] = Field(
        None, ge=0, le=200, description="Current weekly mileage in km (auto-calculated if not provided)"
    )
    auto_calculate: bool = Field(
        default=True, description="Auto-calculate fitness from run logs"
    )
    runs_per_week: int = Field(
        default=5, ge=3, le=6, description="Number of runs per week"
    )
    max_heart_rate: Optional[int] = Field(
        None, ge=120, le=220, description="Maximum heart rate in BPM (optional, auto-calculated if not provided)"
    )

    @field_validator("target_distance")
    @classmethod
    def validate_target_distance(cls, v: float) -> float:
        """Validate that target distance is a supported race distance."""
        valid_distances = [d for d in SUPPORTED_DISTANCES if d != 30.0]
        if v not in valid_distances:
            valid_names = [DISTANCE_NAMES.get(d, f"{d}km") for d in valid_distances]
            raise ValueError(f"Please select a valid distance: {', '.join(valid_names)}")
        return v

    @model_validator(mode="after")
    def validate_realistic_improvement(self) -> "PerformancePlanRequest":
        """Validate that goal pace represents realistic improvement."""
        if self.current_pace and self.goal_pace:
            if self.goal_pace >= self.current_pace:
                raise ValueError(
                    "Goal pace must be faster than current pace. "
                    "Performance training is for improving race times."
                )

            improvement = (self.current_pace - self.goal_pace) / self.current_pace
            if improvement > 0.15:
                current_formatted = format_pace_bare(self.current_pace)
                goal_formatted = format_pace_bare(self.goal_pace)
                raise ValueError(
                    f"Goal pace ({goal_formatted}/km) represents >15% improvement from current "
                    f"({current_formatted}/km). This is unrealistic for a single training cycle. "
                    "Consider a more conservative goal or extend your training timeline."
                )

        return self

    @model_validator(mode="after")
    def validate_sufficient_base(self) -> "PerformancePlanRequest":
        """Validate that current mileage is sufficient for performance training."""
        if self.current_weekly_km is not None:
            target = self.target_distance
            current_km = self.current_weekly_km

            # Minimum mileage requirements for performance training (higher than beginner plans)
            min_requirements = {
                5.0: 20,
                10.0: 25,
                21.1: 35,
                42.2: 50
            }

            if target in min_requirements:
                min_required = min_requirements[target]
                if current_km < min_required:
                    target_display = DISTANCE_NAMES.get(target, f"{target}km")
                    raise InadequateBaseException(
                        f"Performance training for {target_display} requires at least {min_required}km/week base. "
                        f"You're currently at {current_km}km/week.",
                        f"Build your weekly mileage to {min_required}km for 3-4 weeks before starting performance training. "
                        "Performance plans focus on speed/quality, so a solid mileage base is essential."
                    )

        return self


# Strava integration schemas
class StravaSyncResponse(BaseModel):
    """Response for Strava sync operation."""

    synced: int
    skipped: int
    errors: List[str] = []
    total: int = 0
    last_synced_at: Optional[int] = None
    adjustment_results: Optional[List[dict]] = None


class StravaStatusResponse(BaseModel):
    """Response for Strava connection status."""

    connected: bool
    athlete_id: Optional[str] = None
    last_synced_at: Optional[int] = None
