"""PlanRequest schema with validators for the main road/trail plan flow."""

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from app.core.training.environment import EnvironmentalConditions

from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
from app.core.training.backyard_profile import (
    BACKYARD_LOOP_KM,
    BACKYARD_LOOP_MAX_ELEVATION_M,
    BACKYARD_LOOP_MAX_KM,
    BACKYARD_LOOP_MIN_KM,
    MAX_TARGET_LOOPS,
    MIN_TARGET_LOOPS,
    BackyardProfile,
    backyard_max_weeks,
    backyard_min_runs_per_week,
    backyard_min_weekly_km,
    backyard_min_weeks,
    classify_backyard,
)
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

    # Backyard Ultra mode — set by the form when the user picks "Backyard
    # Ultra". A backyard goal is stated in hourly loops, not in
    # kilometres, so ``target_distance`` / ``target_elevation_gain_m`` are
    # *derived* below rather than supplied: the engine periodises against the
    # ultra a backyard goal projects onto, while everything the runner sees is
    # denominated in loops.
    is_backyard: bool = Field(
        default=False,
        description="True for backyard ultra plans (goal stated in hourly loops).",
    )
    backyard_target_loops: Optional[int] = Field(
        default=None,
        ge=MIN_TARGET_LOOPS,
        le=MAX_TARGET_LOOPS,
        description=(
            "Hourly loops the runner is training to complete. "
            "Required when is_backyard=True."
        ),
    )
    backyard_loop_km: float = Field(
        default=BACKYARD_LOOP_KM,
        ge=BACKYARD_LOOP_MIN_KM,
        le=BACKYARD_LOOP_MAX_KM,
        description="Loop length in km. Defaults to the standard 6.706 km.",
    )
    backyard_loop_elevation_gain_m: float = Field(
        default=0.0,
        ge=0,
        le=BACKYARD_LOOP_MAX_ELEVATION_M,
        description="Elevation gain per loop in m (0 for a flat loop).",
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
    def _derive_backyard_target(cls, values):
        """Project a backyard goal onto the distance the engine periodises against.

        A backyard runner states a goal in loops; the plan engine, the
        duplicate check, the nutrition engine and the stored row all speak
        kilometres. Deriving the projection here — once, at the edge — means
        every one of them keeps working unchanged, and nothing downstream has
        to know that ``target_distance`` came from a loop count.
        """
        if not isinstance(values, dict) or not values.get("is_backyard"):
            return values

        loops = values.get("backyard_target_loops")
        if loops is None:
            raise ValueError(
                "Backyard plans need a target — how many hourly loops are you "
                "training to complete?"
            )
        try:
            loops_i = int(loops)
        except (TypeError, ValueError):
            raise ValueError("Target must be a whole number of loops.")
        if not MIN_TARGET_LOOPS <= loops_i <= MAX_TARGET_LOOPS:
            raise ValueError(
                f"Target must be between {MIN_TARGET_LOOPS} and "
                f"{MAX_TARGET_LOOPS} loops."
            )

        loop_km = values.get("backyard_loop_km")
        loop_km_f = BACKYARD_LOOP_KM if loop_km in (None, "") else float(loop_km)
        elev = values.get("backyard_loop_elevation_gain_m")
        elev_f = 0.0 if elev in (None, "") else float(elev)
        if not BACKYARD_LOOP_MIN_KM <= loop_km_f <= BACKYARD_LOOP_MAX_KM:
            raise ValueError(
                f"Loop length must be {BACKYARD_LOOP_MIN_KM:g}–"
                f"{BACKYARD_LOOP_MAX_KM:g} km. An hourly lap outside that range "
                "is a different event, not a backyard."
            )
        if not 0 <= elev_f <= BACKYARD_LOOP_MAX_ELEVATION_M:
            raise ValueError(
                f"Loop elevation gain must be 0–{BACKYARD_LOOP_MAX_ELEVATION_M:g} m."
            )

        profile = classify_backyard(loops_i, loop_km_f, elev_f)
        values["backyard_target_loops"] = loops_i
        values["backyard_loop_km"] = loop_km_f
        values["backyard_loop_elevation_gain_m"] = elev_f
        # A backyard periodises as the ultra it projects onto, so it travels
        # through the rest of the system as a trail plan.
        values["is_trail"] = True
        values["target_distance"] = profile.equivalent_distance_km
        values["target_elevation_gain_m"] = profile.equivalent_elevation_gain_m
        return values

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

        if self.is_backyard:
            # The target distance is derived, not entered — the loop count was
            # already range-checked when it was projected.
            return self

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

    def backyard_profile(self) -> Optional[BackyardProfile]:
        """The runner's backyard goal, or ``None`` for every other plan kind."""
        if not self.is_backyard or self.backyard_target_loops is None:
            return None
        return classify_backyard(
            self.backyard_target_loops,
            self.backyard_loop_km,
            self.backyard_loop_elevation_gain_m,
        )

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

        backyard = self.backyard_profile()
        if backyard is not None:
            min_w = backyard_min_weeks(backyard)
            max_w = backyard_max_weeks(backyard)
            if weeks < min_w:
                raise InsufficientTimeException(
                    f"Training for {backyard.target_loops} loops requires at "
                    f"least {min_w} weeks",
                    f"This goal needs {min_w}–{max_w} weeks to build the "
                    "aerobic base, the loop-pace habit, and enough simulations "
                    "to rehearse the format.",
                )
            if weeks > max_w:
                raise ValueError(
                    f"A {backyard.target_loops}-loop plan should not exceed "
                    f"{max_w} weeks. Consider a shorter, sharper block."
                )
            return self

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

        backyard = self.backyard_profile()
        if backyard is not None:
            min_runs = backyard_min_runs_per_week(backyard)
            if v < min_runs:
                raise ValueError(
                    f"A {backyard.target_loops}-loop backyard plan needs at "
                    f"least {min_runs} runs per week. Backyard volume arrives "
                    "as many medium sessions, not a few big ones — compressing "
                    "it into fewer days trains the wrong thing."
                )
            return self

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
                if self.is_backyard:
                    target_display = f"a {self.backyard_target_loops}-loop backyard"
                elif self.is_trail:
                    target_display = f"a {target:g} km trail/ultra"
                else:
                    target_display = DISTANCE_NAMES.get(target, f"{target}km")
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

        backyard = self.backyard_profile()
        if backyard is not None:
            min_km = backyard_min_weekly_km(backyard)
            if current_km < min_km:
                raise InadequateBaseException(
                    f"Current mileage ({current_km:g} km/week) is below the "
                    f"recommended minimum ({min_km:g} km/week) for a "
                    f"{backyard.target_loops}-loop goal",
                    "Build a steady base of easy running first — a backyard "
                    "asks you to repeat a loop you're already comfortable "
                    "with, not to discover one.",
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

        # A backyard has no goal time: the goal is a loop count, and its pace is
        # the rest budget the profile computes. Feeding a 160 km projection to
        # the VDOT model would produce a number nothing should act on.
        if self.goal_time and not self.is_backyard:
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
