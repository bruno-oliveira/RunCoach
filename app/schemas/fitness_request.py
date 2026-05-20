"""FitnessPlanRequest schema."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
from app.schemas.plan_config import compute_vdot_from_time


class FitnessPlanRequest(BaseModel):
    """Request schema for generating a fitness (VO2Max/physiological) training plan."""

    current_km: float = Field(
        ..., ge=10.0, le=200, description="Current weekly mileage in km (min 10)"
    )
    weeks: int = Field(
        ..., ge=6, le=12, description="Training duration in weeks (6-12)"
    )
    runs_per_week: int = Field(
        ..., ge=3, le=6, description="Number of runs per week (3-6)"
    )
    focus_area: str = Field(
        default="vo2max",
        description="Training focus: 'vo2max', 'threshold', or 'balanced'",
    )
    focus_distance: Optional[float] = Field(
        default=None,
        description="Optional focus distance for pacing context (from SUPPORTED_DISTANCES)",
    )
    body_weight_kg: float = Field(
        default=70.0, ge=30.0, le=250.0, description="Body weight in kg"
    )
    max_heart_rate: Optional[int] = Field(
        None, ge=120, le=220, description="Maximum heart rate in BPM"
    )

    recent_race_distance_km: Optional[float] = Field(
        default=None, description="Recent race distance in km (for VDOT calculation)"
    )
    recent_race_time: Optional[str] = Field(
        default=None, description="Recent race finish time (HH:MM:SS or MM:SS)"
    )

    vdot: Optional[float] = Field(default=None, exclude=True)
    current_pace_min_km: Optional[float] = Field(default=None, exclude=True)

    @field_validator("focus_area")
    @classmethod
    def validate_focus_area(cls, v: str) -> str:
        valid = ("vo2max", "threshold", "balanced")
        if v not in valid:
            raise ValueError(f"Focus area must be one of: {', '.join(valid)}")
        return v

    @field_validator("focus_distance")
    @classmethod
    def validate_focus_distance(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v not in SUPPORTED_DISTANCES:
            valid_names = [DISTANCE_NAMES[d] for d in SUPPORTED_DISTANCES]
            raise ValueError(f"Focus distance must be one of: {', '.join(valid_names)}")
        return v

    @model_validator(mode="after")
    def compute_vdot(self) -> "FitnessPlanRequest":
        if self.recent_race_distance_km and self.recent_race_time:
            self.vdot, self.current_pace_min_km = compute_vdot_from_time(
                self.recent_race_distance_km, self.recent_race_time, "recent_race_time"
            )
        return self
