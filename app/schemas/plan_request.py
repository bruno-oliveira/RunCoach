"""PlanRequest schema with validators for the main road/trail plan flow."""

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from app.core.training.environment import EnvironmentalConditions

from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
from app.core.training.trail_profile import TRAIL_SENTINEL_KM
from app.core.training.training_config import get_constraints
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ZeroMileageUnsupportedException,
)
from app.schemas.plan_config import _MILEAGE_CONFIG, compute_vdot_from_time


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
    max_runs_per_week: int = Field(
        default=4, ge=2, le=6, description="Maximum runs per week"
    )

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
    training_terrain: Optional[str] = Field(
        default=None,
        description=(
            "Terrain available for day-to-day training: flat, rolling, hilly, or "
            "mountainous. Optional; when omitted we infer from race elevation."
        ),
    )

    # Deprecated: superseded by target_elevation_gain_m. Kept for backward
    # compat with the legacy form and existing DB rows; auto-migrated below.
    terrain: Optional[str] = Field(
        default=None,
        description="DEPRECATED — legacy 'hilly'/'flat' toggle, migrated to target_elevation_gain_m.",
    )

    # Trail Intensive Training Weekend — opt-in, eligible trail plans only.
    # The engine no-ops it for road/short-bracket plans, so it's safe to pass
    # through unconditionally; the form only surfaces it for trail goals.
    intensive_weekend_enabled: bool = Field(
        default=False,
        description=(
            "Opt a trail/ultra plan into an Intensive Training Weekend block "
            "(Saturday trail-quality + Sunday long on fatigued legs) on the "
            "final peak week. Ignored for road and short-bracket plans."
        ),
    )

    # Body weight — used for personalised nutrition
    body_weight_kg: float = Field(
        default=70.0, ge=30.0, le=250.0, description="Body weight in kg"
    )

    # Optional race-day conditions — feed heat/altitude-aware predictions.
    # All optional; when omitted predictions behave exactly as before.
    race_temp_c: Optional[float] = Field(
        default=None,
        ge=-30.0,
        le=55.0,
        description="Expected race-day air temperature in °C (for heat-adjusted pacing).",
    )
    race_humidity_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Expected race-day relative humidity (%) (combined with temp via dew point).",
    )
    race_altitude_m: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=6000.0,
        description="Race elevation above sea level in m (for altitude-adjusted VDOT).",
    )

    def race_conditions(self) -> Optional["EnvironmentalConditions"]:
        """Build :class:`EnvironmentalConditions` from the optional race inputs.

        Returns ``None`` when nothing actionable was supplied so callers can
        treat "no conditions" uniformly.
        """
        from app.core.training.environment import EnvironmentalConditions

        return EnvironmentalConditions.from_inputs(
            temp_c=self.race_temp_c,
            humidity_pct=self.race_humidity_pct,
            altitude_m=self.race_altitude_m,
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
        default=None,
        description="Goal finish time for the target race (HH:MM:SS or MM:SS)",
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
        if target_f == TRAIL_SENTINEL_KM and not is_trail_explicit:
            values["is_trail"] = True
            if values.get("target_elevation_gain_m") is None:
                values["target_elevation_gain_m"] = (
                    200.0 if terrain == "flat" else 1000.0
                )

        return values

    @model_validator(mode="after")
    def validate_training_terrain(self) -> "PlanRequest":
        """Validate optional training terrain selection."""
        if self.training_terrain is None:
            return self
        allowed = {"flat", "rolling", "hilly", "mountainous"}
        terrain = self.training_terrain.strip().lower()
        if terrain not in allowed:
            raise ValueError(
                "Training terrain must be one of: flat, rolling, hilly, mountainous."
            )
        self.training_terrain = terrain
        return self

    @model_validator(mode="after")
    def _validate_trail_or_road_distance(self) -> "PlanRequest":
        """Branch validation: trail accepts 8–163 km + elevation; road uses presets."""
        from app.core.training.trail_profile import (
            TRAIL_DISTANCE_MAX_KM,
            TRAIL_DISTANCE_MIN_KM,
        )

        if self.is_trail:
            if not (
                TRAIL_DISTANCE_MIN_KM <= self.target_distance <= TRAIL_DISTANCE_MAX_KM
            ):
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

    def resolved_training_terrain(self) -> Optional[str]:
        """Return the terrain to use for workout selection.

        Priority:
        1) explicit ``training_terrain``
        2) legacy ``terrain`` toggle (flat vs non-flat)
        3) inferred from race elevation profile for trail plans
        """
        if not self.is_trail:
            return None

        if self.training_terrain:
            return self.training_terrain

        if self.terrain:
            return "flat" if self.terrain == "flat" else "hilly"

        from app.core.training.trail_profile import classify_trail

        profile = classify_trail(
            self.target_distance, self.target_elevation_gain_m or 0.0
        )
        return profile.elevation_class

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

            profile = classify_trail(
                self.target_distance, self.target_elevation_gain_m or 0.0
            )
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
        constraints = get_constraints(target)

        if constraints is not None and target != 30.0:
            # 30k (trail) has bracket-specific handling above and skips week-window enforcement.
            if weeks < constraints.min_weeks:
                target_display = DISTANCE_NAMES.get(target, f"{target}km")
                raise InsufficientTimeException(
                    f"Training for {target_display} requires at least {constraints.min_weeks} weeks",
                    f"Consider extending your training to {constraints.min_weeks} weeks. "
                    f"{constraints.insufficient_time_reason}",
                )
            if weeks > constraints.max_weeks:
                raise ValueError(
                    f"{constraints.excessive_time_reason}. Consider a shorter training period."
                )

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

            profile = classify_trail(
                self.target_distance, self.target_elevation_gain_m or 0.0
            )
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
                    "Consider extending your training to at least 8 weeks.",
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
