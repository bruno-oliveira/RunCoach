"""Pydantic schemas for training plan requests and validation."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
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


def compute_vdot_from_time(
    distance_km: float, time_str: str, field_name: str = "race time"
) -> tuple[float, float]:
    """Parse a finish time and return (VDOT, pace_min_per_km) for the given distance.

    Raises ValueError if the time string is unparseable. Centralised so plan and
    fitness request schemas share one VDOT-derivation path.
    """
    from app.core.training.vdot_calculator import VDOTCalculator

    seconds = VDOTCalculator.parse_time_to_seconds(time_str)
    if not seconds or seconds <= 0:
        raise ValueError(
            f"Could not parse {field_name} '{time_str}'. "
            "Use HH:MM:SS or MM:SS format (e.g. '42:15' or '1:45:30')."
        )
    vdot = VDOTCalculator.calculate_vdot(distance_km, seconds)
    pace_min_km = (seconds / 60) / distance_km
    return vdot, pace_min_km


_MILEAGE_CONFIG = {
    5.0: {
        "min": settings.min_mileage_5k,
        "max": settings.max_mileage_5k,
        "low_msg": settings.low_mileage_msg_5k,
        "high_msg": settings.high_mileage_msg_5k,
    },
    10.0: {
        "min": settings.min_mileage_10k,
        "max": settings.max_mileage_10k,
        "low_msg": settings.low_mileage_msg_10k,
        "high_msg": settings.high_mileage_msg_10k,
    },
    21.1: {
        "min": settings.min_mileage_half,
        "max": settings.max_mileage_half,
        "low_msg": settings.low_mileage_msg_half,
        "high_msg": settings.high_mileage_msg_half,
    },
    30.0: {
        "min": settings.min_mileage_30k,
        "max": settings.max_mileage_30k,
        "low_msg": settings.low_mileage_msg_30k,
        "high_msg": settings.high_mileage_msg_30k,
    },
    42.2: {
        "min": settings.min_mileage_marathon,
        "max": settings.max_mileage_marathon,
        "low_msg": settings.low_mileage_msg_marathon,
        "high_msg": settings.high_mileage_msg_marathon,
    },
}


class PlanRequestBase(BaseModel):
    """Basic fields for training plan generation."""

    current_km: float = Field(
        ..., ge=0, le=200, description="Current weekly mileage in km"
    )
    target_distance: float = Field(
        ...,
        gt=0,
        le=163.0,
        description="Target race distance in km (road preset OR custom trail/ultra 8–163 km)",
    )
    # Outer envelope — per-distance validators tighten further (road ≤ 24, ultra up to 40).
    weeks: int = Field(..., ge=4, le=40, description="Training duration in weeks")
    max_runs_per_week: int = Field(default=4, ge=2, le=6, description="Maximum runs per week")

    # Trail mode — set by the form when user picks "Trail / Ultra (custom)".
    # Auto-set in the legacy migration path when target_distance == 30.0.
    is_trail: bool = Field(
        default=False,
        description="True for parameterized trail/ultra plans (distance + elevation).",
    )
    target_elevation_gain_m: Optional[float] = Field(
        default=None,
        ge=0,
        le=10000,
        description="Total race elevation gain in m. Required when is_trail=True.",
    )

    # Deprecated: superseded by target_elevation_gain_m. Kept for backward
    # compat with the legacy form and existing DB rows; auto-migrated below.
    terrain: Optional[str] = Field(
        default=None,
        description="DEPRECATED — legacy 'hilly'/'flat' toggle, migrated to target_elevation_gain_m.",
    )

    # Body weight — used for personalised nutrition
    body_weight_kg: float = Field(
        default=70.0, ge=30.0, le=250.0, description="Body weight in kg"
    )


class RaceInfoMixin(BaseModel):
    """Optional race info for VDOT-based pace zones."""

    recent_race_distance_km: Optional[float] = Field(
        default=None, description="Recent race distance in km (for VDOT calculation)"
    )
    recent_race_time: Optional[str] = Field(
        default=None, description="Recent race finish time (HH:MM:SS or MM:SS)"
    )

    # Optional: goal finish time for the target race — drives aspirational
    # pace zones when present (goal VDOT used in place of current VDOT).
    goal_time: Optional[str] = Field(
        default=None, description="Goal finish time for the target race (HH:MM:SS or MM:SS)"
    )


class PlanRequest(PlanRequestBase, RaceInfoMixin):
    """Request schema for generating a training plan."""

    # Auto-computed — not user inputs
    vdot: Optional[float] = Field(default=None, exclude=True)
    goal_vdot: Optional[float] = Field(default=None, exclude=True)
    goal_pace_min_km: Optional[float] = Field(default=None, exclude=True)
    current_pace_min_km: Optional[float] = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _auto_migrate_legacy_trail(cls, values):
        """Auto-promote legacy form input to the new trail fields.

        Pre-existing form posts and DB rows used target_distance=30.0 and a
        ``terrain`` toggle. The new schema models trail goals as
        (is_trail=True, target_elevation_gain_m). This shim keeps both
        callsites working until the UI is updated in phase 6.
        """
        if not isinstance(values, dict):
            return values

        target = values.get("target_distance")
        try:
            target_f = float(target) if target is not None else None
        except (TypeError, ValueError):
            return values  # let downstream validation produce the real error

        is_trail_explicit = "is_trail" in values and bool(values.get("is_trail"))
        terrain = values.get("terrain")

        # Legacy form path: target=30.0 with no is_trail flag. Auto-promote to
        # trail mode and derive elevation from the deprecated terrain toggle.
        # The new form path always sends is_trail explicitly and must supply
        # target_elevation_gain_m itself — we do not silently default it here.
        if target_f == 30.0 and not is_trail_explicit:
            values["is_trail"] = True
            if values.get("target_elevation_gain_m") is None:
                values["target_elevation_gain_m"] = 200.0 if terrain == "flat" else 1000.0

        return values

    @model_validator(mode="after")
    def _validate_trail_or_road_distance(self) -> "PlanRequest":
        """Branch validation: trail accepts 8–163 km + elevation; road uses presets."""
        from app.core.training.trail_profile import (
            TRAIL_DISTANCE_MAX_KM,
            TRAIL_DISTANCE_MIN_KM,
        )

        if self.is_trail:
            if not (TRAIL_DISTANCE_MIN_KM <= self.target_distance <= TRAIL_DISTANCE_MAX_KM):
                raise ValueError(
                    f"Trail/ultra distance must be {TRAIL_DISTANCE_MIN_KM:g}–"
                    f"{TRAIL_DISTANCE_MAX_KM:g} km. For shorter races pick a road preset."
                )
            if self.target_elevation_gain_m is None:
                raise ValueError(
                    "Trail/ultra plans require an elevation gain in metres "
                    "(enter 0 for fully flat trails)."
                )
        else:
            if self.target_distance not in SUPPORTED_DISTANCES:
                road_set = [d for d in SUPPORTED_DISTANCES if d != 30.0]
                valid_names = [DISTANCE_NAMES[d] for d in road_set]
                raise ValueError(
                    f"Please select a valid distance: {', '.join(valid_names)}, "
                    "or pick Trail/Ultra for a custom trail goal."
                )

        return self

    @model_validator(mode="after")
    def validate_weeks_for_distance(self) -> "PlanRequest":
        """Validate that training duration is appropriate for target distance."""
        weeks = self.weeks

        if self.is_trail:
            from app.core.training.trail_profile import (
                classify_trail,
                trail_max_weeks,
                trail_min_weeks,
            )

            profile = classify_trail(self.target_distance, self.target_elevation_gain_m or 0.0)
            min_w = trail_min_weeks(profile)
            max_w = trail_max_weeks(profile)

            if weeks < min_w:
                raise InsufficientTimeException(
                    f"Training for a {self.target_distance:g} km trail/ultra "
                    f"requires at least {min_w} weeks",
                    f"This bracket needs {min_w}–{max_w} weeks to build "
                    "trail-specific strength, time-on-feet, and fueling habits.",
                )
            if weeks > max_w:
                raise ValueError(
                    f"Training plans for a {self.target_distance:g} km trail/ultra "
                    f"should not exceed {max_w} weeks. Consider a shorter focused cycle."
                )
            return self

        target = self.target_distance
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

    @model_validator(mode="after")
    def validate_runs_per_week(self) -> "PlanRequest":
        """Bracket-aware runs-per-week floor.

        Road: 5K/10K accept 2; Half ≥ 3; Marathon ≥ 4.
        Trail: short ≥ 3, standard ≥ 4, ultra ≥ 5, long_ultra ≥ 6.
        """
        v = self.max_runs_per_week

        if self.is_trail:
            from app.core.training.trail_profile import (
                classify_trail,
                trail_min_runs_per_week,
            )

            profile = classify_trail(self.target_distance, self.target_elevation_gain_m or 0.0)
            min_runs = trail_min_runs_per_week(profile)
            if v < min_runs:
                raise ValueError(
                    f"A {self.target_distance:g} km trail/ultra plan needs at least "
                    f"{min_runs} runs per week to absorb the volume safely. "
                    "Trail-specific stress is harder to compress into fewer sessions."
                )
            return self

        target_distance = self.target_distance
        if target_distance >= 42.2 and v < 4:
            distance_name = DISTANCE_NAMES.get(target_distance, f"{target_distance}km")
            raise ValueError(
                f"{distance_name} training typically requires at least 4 runs per week. "
                f"Consider 4-5 runs per week for {distance_name.lower()} preparation."
            )
        if target_distance >= 21.1 and v < 3:
            distance_name = DISTANCE_NAMES.get(target_distance, f"{target_distance}km")
            raise ValueError(
                f"{distance_name} training requires at least 3 runs per week. "
                f"The 2-runs option is only available for 5K and 10K plans."
            )
        return self

    @model_validator(mode="after")
    def validate_current_mileage(self) -> "PlanRequest":
        """Validate that current mileage is appropriate for target distance."""
        target = self.target_distance
        current_km = self.current_km
        weeks = self.weeks

        if current_km == 0:
            supported_distances = [5.0, 10.0]
            if self.is_trail or target not in supported_distances:
                target_display = (
                    f"a {target:g} km trail/ultra"
                    if self.is_trail
                    else DISTANCE_NAMES.get(target, f"{target}km")
                )
                raise ZeroMileageUnsupportedException(
                    f"Starting from zero for {target_display} is not recommended.",
                    f"Starting from zero mileage for {target_display} requires building a running base first. "
                    "Consider training for a 5K or 10K first to build your fitness foundation.",
                )

            if weeks < 8:
                raise InsufficientTimeException(
                    "Beginner plans require at least 8 weeks for safe progression.",
                    "Couch to 5K programs need 8+ weeks to build fitness safely. "
                    "Consider extending your training to at least 8 weeks."
                )

            return self

        if self.is_trail:
            from app.core.training.trail_profile import (
                classify_trail,
                trail_min_weekly_mileage,
            )

            profile = classify_trail(target, self.target_elevation_gain_m or 0.0)
            min_km = trail_min_weekly_mileage(profile)
            if current_km < min_km:
                raise InadequateBaseException(
                    f"Current mileage ({current_km:g} km/week) is below the recommended "
                    f"minimum ({min_km:g} km/week) for a {target:g} km trail/ultra",
                    "Build a steady base of easy running first — trail-specific volume "
                    "and elevation work compounds the load quickly.",
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
        """Calculate current and goal VDOT from optional inputs.

        - recent_race_distance_km + recent_race_time → current VDOT
        - target_distance + goal_time → goal VDOT (and goal pace)
        - Validates that the goal improvement is plausible (max ~15%).
        """
        if self.recent_race_distance_km and self.recent_race_time:
            self.vdot, self.current_pace_min_km = compute_vdot_from_time(
                self.recent_race_distance_km, self.recent_race_time, "recent_race_time"
            )

        if self.goal_time:
            self.goal_vdot, self.goal_pace_min_km = compute_vdot_from_time(
                self.target_distance, self.goal_time, "goal_time"
            )

            if self.vdot and self.goal_vdot and self.goal_vdot > self.vdot:
                improvement = (self.goal_vdot - self.vdot) / self.vdot
                if improvement > 0.15:
                    raise ValueError(
                        f"Goal time represents a >15% VDOT jump from your recent "
                        f"race ({self.vdot:.1f} → {self.goal_vdot:.1f}). "
                        "Consider a more conservative goal or extend your training."
                    )
        return self


def get_mileage_warning(
    target_distance: float,
    current_km: float,
    is_trail: bool = False,
    target_elevation_gain_m: Optional[float] = None,
) -> Optional[str]:
    """Get warning message if mileage is unusually high for target distance."""
    if is_trail:
        from app.core.training.trail_profile import (
            classify_trail,
            trail_max_weekly_mileage,
        )

        profile = classify_trail(target_distance, target_elevation_gain_m or 0.0)
        if current_km > trail_max_weekly_mileage(profile):
            return (
                "High mileage for this trail/ultra distance. "
                "Focus on time-on-feet, recovery, and consistency rather than chasing volume."
            )
        return None

    if target_distance in _MILEAGE_CONFIG:
        cfg = _MILEAGE_CONFIG[target_distance]
        if current_km > cfg["max"]:
            return cfg["high_msg"]
    return None


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

            min_requirements = {
                5.0: settings.perf_min_mileage_5k,
                10.0: settings.perf_min_mileage_10k,
                21.1: settings.perf_min_mileage_half,
                42.2: settings.perf_min_mileage_marathon,
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
