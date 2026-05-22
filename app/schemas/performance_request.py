"""PerformancePlanRequest schema for VDOT/time-goal performance plans."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
from app.core.training.training_config import get_constraints
from app.exceptions import InadequateBaseException
from app.utils import format_pace_bare


class PerformancePlanRequest(BaseModel):
    """Request schema for generating a performance training plan."""

    target_distance: float = Field(
        ..., gt=0, le=42.2, description="Target race distance in km"
    )
    current_pace: Optional[float] = Field(
        None,
        ge=2.5,
        le=10.0,
        description="Current pace in min/km (auto-calculated if not provided)",
    )
    goal_pace: float = Field(
        ..., ge=2.5, le=10.0, description="Goal race pace in min/km"
    )
    current_time: Optional[str] = Field(
        None, description="Current finish time (HH:MM:SS or MM:SS)"
    )
    goal_time: str = Field(..., description="Goal finish time (HH:MM:SS or MM:SS)")
    weeks: int = Field(
        ..., ge=6, le=16, description="Training duration in weeks (6-16)"
    )
    current_weekly_km: Optional[float] = Field(
        None,
        ge=0,
        le=200,
        description="Current weekly mileage in km (auto-calculated if not provided)",
    )
    auto_calculate: bool = Field(
        default=True, description="Auto-calculate fitness from run logs"
    )
    runs_per_week: int = Field(
        default=5, ge=3, le=6, description="Number of runs per week"
    )
    max_heart_rate: Optional[int] = Field(
        None,
        ge=120,
        le=220,
        description="Maximum heart rate in BPM (optional, auto-calculated if not provided)",
    )

    @field_validator("target_distance")
    @classmethod
    def validate_target_distance(cls, v: float) -> float:
        """Validate that target distance is a supported race distance."""
        valid_distances = [d for d in SUPPORTED_DISTANCES if d != 30.0]
        if v not in valid_distances:
            valid_names = [DISTANCE_NAMES.get(d, f"{d}km") for d in valid_distances]
            raise ValueError(
                f"Please select a valid distance: {', '.join(valid_names)}"
            )
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

            constraints = get_constraints(target)
            min_required = constraints.perf_min_mileage if constraints else None

            if min_required is not None:
                if current_km < min_required:
                    target_display = DISTANCE_NAMES.get(target, f"{target}km")
                    raise InadequateBaseException(
                        f"Performance training for {target_display} requires at least {min_required}km/week base. "
                        f"You're currently at {current_km}km/week.",
                        f"Build your weekly mileage to {min_required}km for 3-4 weeks before starting performance training. "
                        "Performance plans focus on speed/quality, so a solid mileage base is essential.",
                    )

        return self
