"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.exceptions import InadequateBaseException, InsufficientTimeException

# Distance name mapping for display purposes
DISTANCE_NAMES = {
    5.0: "5K",
    10.0: "10K",
    21.1: "Half Marathon",
    30.0: "Trail Running",
    42.2: "Marathon",
}


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

    @field_validator("target_distance")
    @classmethod
    def validate_target_distance(cls, v: float) -> float:
        """Validate that target distance is a supported race distance."""
        valid_distances = [5.0, 10.0, 21.1, 30.0, 42.2]
        if v not in valid_distances:
            valid_names = [DISTANCE_NAMES[d] for d in valid_distances]
            raise ValueError(f"Please select a valid distance: {', '.join(valid_names)}")
        return v

    @model_validator(mode="after")
    def validate_weeks_for_distance(self) -> "PlanRequest":
        """Validate that training duration is appropriate for target distance."""
        target = self.target_distance
        weeks = self.weeks

        # Define minimum training weeks and user-friendly messages
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

        # Define maximum training weeks to prevent overtraining
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

        # Check minimum requirements
        if target in min_weeks_requirements:
            min_weeks, reason = min_weeks_requirements[target]
            if weeks < min_weeks:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise InsufficientTimeException(
                    f"Training for {target_display} requires at least {min_weeks} weeks",
                    f"Consider extending your training to {min_weeks} weeks. {reason}",
                )

        # Check maximum requirements
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
            # For longer races (marathon, trail), suggest more runs
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

        # Define reasonable current mileage ranges for each distance
        mileage_requirements = {
            5.0: {
                "min": settings.min_mileage_5k,
                "max": 40,
                "low_msg": "Your current mileage is quite low for 5K training. "
                "Consider building a base with 2-3 weeks of easy running first.",
                "high_msg": "You're already running high mileage for 5K. "
                "Consider focusing on speed work rather than volume.",
            },
            10.0: {
                "min": settings.min_mileage_10k,
                "max": 50,
                "low_msg": "Your current mileage may be insufficient for 10K training. "
                "Build to at least 10km/week for 2-3 weeks first.",
                "high_msg": "High mileage for 10K. "
                "You might benefit from focusing on quality over quantity.",
            },
            21.1: {
                "min": settings.min_mileage_half,
                "max": 70,
                "low_msg": "Half marathon training requires a stronger base. "
                "Build to 15km/week for 3-4 weeks before starting.",
                "high_msg": "Very high mileage for half marathon. "
                "Ensure adequate recovery and consider periodization.",
            },
            30.0: {
                "min": settings.min_mileage_30k,
                "max": 60,
                "low_msg": "Trail running requires good base fitness. "
                "Build to 8km/week with some trail experience first.",
                "high_msg": "High mileage for trail running. "
                "Focus on time on feet rather than distance.",
            },
            42.2: {
                "min": settings.min_mileage_marathon,
                "max": 100,
                "low_msg": "Marathon training requires significant base fitness. "
                "Build to 25km/week for 4-6 weeks before beginning.",
                "high_msg": "Extremely high mileage. "
                "Be cautious about injury risk and ensure proper recovery.",
            },
        }

        if target in mileage_requirements:
            req = mileage_requirements[target]

            # Check if mileage is too low (but allow 0 for new runners)
            if current_km > 0 and current_km < req["min"]:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise InadequateBaseException(
                    f"Current mileage ({current_km}km/week) is below recommended "
                    f"minimum ({req['min']}km/week) for {target_display} training",
                    req["low_msg"],
                )

        return self


class WorkoutAdjustment(BaseModel):
    """Schema for adjusting a single workout."""

    day: int = Field(..., ge=1, le=7, description="Day of week (1-7)")
    workout_type: Optional[str] = Field(None, description="New workout type")
    distance: Optional[float] = Field(None, ge=0, description="New distance in km")
    intensity: Optional[str] = Field(None, description="New intensity level")
    notes: Optional[str] = Field(None, description="Updated workout notes")


class PlanCustomizationRequest(BaseModel):
    """Schema for customizing a training plan."""

    plan_id: str = Field(..., description="Training plan ID")
    week_number: int = Field(..., ge=1, description="Week number to customize")
    adjustments: List[WorkoutAdjustment] = Field(
        ..., description="List of workout adjustments"
    )
    preference_notes: Optional[str] = Field(
        None, description="User preferences for AI suggestions"
    )


# Response schemas
class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = Field(default_factory=lambda: settings.app_version)


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str
    error_type: str
    suggestion: Optional[str] = None


class WorkoutResponse(BaseModel):
    """Single workout response."""

    day: int
    type: str
    distance: float
    intensity: str
    notes: str


class WeeklyPlanResponse(BaseModel):
    """Weekly plan response."""

    week: int
    total_km: float
    workout_distribution: dict[str, int]
    daily_workouts: List[WorkoutResponse]
    strength_training: List[dict[str, Any]]
    training_tips: List[str]


class NutritionTargets(BaseModel):
    """Nutrition targets response."""

    calories: float
    protein: float
    fiber: float
    carbs: float
    fat: float


class MealOption(BaseModel):
    """Meal option response."""

    name: str
    description: str
    calories: int
    protein: int
    fiber: int
    carbs: int
    fat: int


class NutritionPlanResponse(BaseModel):
    """Nutrition plan response."""

    nutrition_targets: NutritionTargets
    meal_options: dict[str, List[MealOption]]
    general_tips: List[str]
    hydration_guide: dict[str, Any]


# Helper functions for mileage warnings
def get_mileage_warning(target_distance: float, current_km: float) -> Optional[str]:
    """Get warning message if mileage is unusually high for target distance."""
    mileage_warnings = {
        5.0: {
            "max": 40,
            "msg": "You're already running high mileage for 5K. "
            "Consider focusing on speed work rather than volume.",
        },
        10.0: {
            "max": 50,
            "msg": "High mileage for 10K. "
            "You might benefit from focusing on quality over quantity.",
        },
        21.1: {
            "max": 70,
            "msg": "Very high mileage for half marathon. "
            "Ensure adequate recovery and consider periodization.",
        },
        30.0: {
            "max": 60,
            "msg": "High mileage for trail running. "
            "Focus on time on feet rather than distance.",
        },
        42.2: {
            "max": 100,
            "msg": "Extremely high mileage. "
            "Be cautious about injury risk and ensure proper recovery.",
        },
    }

    if target_distance in mileage_warnings:
        warning_data = mileage_warnings[target_distance]
        if current_km > warning_data["max"]:
            return warning_data["msg"]
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
            valid_types = ["easy", "tempo", "interval", "long", "hill", "rest"]
            if v not in valid_types:
                raise ValueError(f"workout_type must be one of: {', '.join(valid_types)}")
        return v


class RunLogCreate(RunLogBase):
    date: Optional[datetime] = Field(None, description="Run date and time (defaults to now)")
    training_plan_id: Optional[str] = Field(None, description="Associated training plan ID")
    daily_workout_id: Optional[str] = Field(None, description="Associated daily workout ID")


class RunLogUpdate(BaseModel):
    distance_km: Optional[float] = Field(None, gt=0)
    duration_minutes: Optional[float] = Field(None, gt=0)
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    max_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    avg_cadence: Optional[int] = Field(None, ge=100, le=220)
    elevation_gain_m: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=1000)
    workout_type: Optional[str] = Field(None)
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    date: Optional[datetime] = None


class RunLogResponse(RunLogBase):
    id: str
    user_id: str
    date: datetime
    avg_pace_min_km: Optional[float] = None
    created_at: datetime


class RunLogListResponse(BaseModel):
    runs: List[RunLogResponse]
    total: int
    page: int
    page_size: int


class AdaptivePlanRequest(BaseModel):
    target_distance: float = Field(..., description="Target race distance in km (30.0 = Trail Running)")
    weeks: int = Field(..., ge=4, le=24, description="Training duration in weeks")
    max_runs_per_week: int = Field(default=4, ge=3, le=6, description="Maximum runs per week")

    @field_validator("target_distance")
    @classmethod
    def validate_target_distance(cls, v: float) -> float:
        valid_distances = [5.0, 10.0, 21.1, 30.0, 42.2]
        if v not in valid_distances:
            valid_names = [DISTANCE_NAMES[d] for d in valid_distances]
            raise ValueError(f"Please select a valid distance: {', '.join(valid_names)}")
        return v



    activity_name: str
    distance_km: float


# Strength Training Schemas
class StrengthExerciseResponse(BaseModel):
    """Strength exercise response."""
    
    id: str
    name: str
    exercise_id: str
    force: Optional[str] = None
    level: Optional[str] = None
    mechanic: Optional[str] = None
    equipment: Optional[str] = None
    primary_muscles: List[str] = []
    secondary_muscles: List[str] = []
    instructions: List[str] = []
    category: Optional[str] = None
    target_muscles: Optional[str] = None
    images: List[str] = []
    gif_url: Optional[str] = None
    is_running_related: bool = False
    is_bodyweight: bool = False
    is_dumbbell: bool = False


class ExerciseSet(BaseModel):
    """Exercise set definition."""
    
    exercise_id: str
    sets: int
    reps: str  # e.g., "12", "10-12", "30 sec"


class DailyWorkoutResponse(BaseModel):
    """Daily strength workout response."""
    
    id: str
    date: str
    title: str
    description: Optional[str] = None
    warmup_exercises: List[Dict[str, Any]] = []
    main_exercises: List[Dict[str, Any]] = []
    cooldown_exercises: List[Dict[str, Any]] = []
    warmup_duration: int = 5
    main_duration: int = 25
    cooldown_duration: int = 5
    total_duration: int = 35
    primary_focus: Optional[str] = None
    secondary_focus: Optional[str] = None
    difficulty: str = "beginner"


class UserFavoriteWorkoutResponse(BaseModel):
    """User favorite workout response."""
    
    id: str
    user_id: str
    workout_id: str
    workout: Optional[DailyWorkoutResponse] = None
    notes: Optional[str] = None
    created_at: datetime


class FavoriteRequest(BaseModel):
    """Favorite/unfavorite workout request."""
    
    workout_id: str
    notes: Optional[str] = None
