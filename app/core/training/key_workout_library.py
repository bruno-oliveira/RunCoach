"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.
"""

from typing import Any, Callable, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.vdot_calculator import VDOTCalculator


def _wu_cd(d: float) -> tuple:
    """Return (warmup_km, cooldown_km) that fit within total distance d."""
    wu = min(2.0, max(0.5, round(d * 0.25, 1)))
    return (wu, wu)


# Each entry generates a complete description from the actual distance.
_DISTANCE_REWRITES: Dict[str, Callable[[float], str]] = {
    "5k_vo2max_400s": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run 10-12 x 400m at 5K pace "
        f"with 90s easy jog recovery between reps. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "5k_race_pace_3km": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run 2 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 2, 1):g}km "
        f"at 5K goal pace with 3 min easy jog recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "5k_cruise_intervals": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run 4 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 4, 1):g}km "
        f"at threshold pace with 60 seconds easy jog between reps. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "5k_threshold_run": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run {round(d - _wu_cd(d)[0] - _wu_cd(d)[1], 1):g}km continuous at threshold pace "
        f"— comfortably hard, you can speak a few words at a time. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "5k_pyramid": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run pyramid: 200m, 400m, 600m, 800m, 600m, 400m, 200m "
        f"— all at 5K pace with equal-distance recovery jogs. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "marathon_mp_long": lambda d: (
        f"Run {round(d):g}km total. First {round(d * 0.60):g}km at easy pace, "
        f"then shift to marathon goal pace for the final {round(d * 0.40):g}km. "
        f"Take a gel at {round(d * 0.32):g}km and {round(d * 0.64):g}km to practice race fueling."
    ),
    "marathon_progressive_long": lambda d: (
        f"Run {round(d):g}km. First {round(d * 0.67):g}km at easy pace. "
        f"Then run each subsequent 2km segment 5-10s/km faster, finishing the last 2km at marathon pace. "
        f"Practice fueling every 5km."
    ),
    "marathon_peak_progressive": lambda d: (
        f"Run {round(d):g}km total. First {round(d * 0.57):g}km at easy pace. "
        f"Then run each subsequent 3km segment 5-10s/km faster, finishing the last 3km at marathon pace."
    ),
    "marathon_easy_long_fueling": lambda d: (
        f"Run {round(d):g}km at easy conversational pace. "
        f"Take a gel or fuel every 5km starting at km 10. Practice your exact race-day nutrition strategy. "
        f"Walk 1 min after each fuel stop if needed."
    ),
    "marathon_tempo_cutdown": lambda d: (
        f"Warm up {round(max(1, d * 0.10)):g}km easy. "
        f"Run 2 x {round(max(1, d * 0.35)):g}km at threshold pace with 3 min easy jog recovery. "
        f"Cool down {round(max(1, d * 0.10)):g}km easy."
    ),
    "marathon_mp_cutdown": lambda d: (
        f"Warm up {round(max(1, d * 0.10)):g}km easy. "
        f"Run 5 x 2km alternating between marathon pace and threshold pace, "
        f"with 90s jog recovery between each. Cool down {round(max(1, d * 0.10)):g}km easy."
    ),
    "half_progressive_long": lambda d: (
        f"Run {round(d):g}km total. Start at easy pace for {round(d * 0.65):g}km, "
        f"then increase to marathon pace for the final {round(d * 0.35):g}km. "
        f"No warm-up needed — the easy start IS the warm-up."
    ),
    "half_cutdown_long": lambda d: (
        f"Run {round(d):g}km in three {round(d / 3, 1):g}km segments. "
        f"Segment 1 at easy pace, segment 2 at 15s/km faster, segment 3 at marathon pace."
    ),
    "half_race_pace_segments": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run 3 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 3, 1):g}km "
        f"at half marathon goal pace with 2 min easy jog recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "half_threshold_cruise": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run 3 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 3, 1):g}km "
        f"at threshold pace with 90 seconds easy jog recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "trail_flat_surge_fartlek": lambda d: (
        f"On varied terrain (grass, dirt path, or trail). Run 8 x 3 min at hill-repeat effort "
        f"(Zone 4-5) with 2 min easy jog recovery. {_wu_cd(d)[0]:g}km warm-up, {_wu_cd(d)[1]:g}km cool-down."
    ),
    "trail_flat_soft_surface": lambda d: (
        f"Find the softest running surface available: grass fields, dirt trails, beach, gravel paths. "
        f"Run {round(d):g}km at easy effort. The soft surface increases energy cost 10-15% vs pavement. "
        f"Walk 2 min every 45 min. Practice race fueling."
    ),
    "trail_time_on_feet": lambda d: (
        f"Run {round(d):g}km on trails at easy conversational effort. "
        f"Walk steep uphills (>15% grade) to conserve energy. Practice race fueling every 30 min."
    ),
    "trail_back_to_back": lambda d: (
        f"Saturday: {round(d * 0.57):g}km trail run at easy effort on hilly terrain. "
        f"Sunday: {round(d * 0.43):g}km trail run at easy effort on fatigued legs. "
        f"Practice race fueling on both days."
    ),
    "trail_technical_terrain": lambda d: (
        f"Find a technical trail with rocks, roots, and uneven surface. "
        f"Run {round(d * 0.80):g}km at moderate effort, focusing on foot placement, "
        f"quick cadence, and staying light on your feet."
    ),
    "10k_goal_pace_segments": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run 2 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 2, 1):g}km "
        f"at 10K goal pace with 3 min standing recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "10k_tempo_progression": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run {round(d - _wu_cd(d)[0] - _wu_cd(d)[1], 1):g}km as a progression: "
        f"first km at easy pace, each subsequent km 10-15 sec/km faster, "
        f"finishing last km at 10K goal pace. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "10k_fartlek": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Within a continuous run, "
        f"alternate 6 x (3 min at 10K pace / 2 min easy jog). Cool down {_wu_cd(d)[1]:g}km easy."
    ),
}


def _rewrite_key_workout_description(description: str, workout_id: str,
                                      actual_distance: float) -> str:
    """Generate a distance-appropriate description for a key workout."""
    rewrite_fn = _DISTANCE_REWRITES.get(workout_id)
    if not rewrite_fn:
        return description
    return rewrite_fn(actual_distance)

# Backward-compatible alias: tests and internal code import _WORKOUTS.
_WORKOUTS = WORKOUTS


def _resolve_long_steps_builder(
    builder_key: str,
    distance_km: float,
    pace_zones: Optional[Dict],
) -> List[Dict[str, Any]]:
    """Dispatch a long-run steps_builder string to its builder function."""
    if builder_key == "alternating_mp":
        return _steps_mod.build_alternating_mp_long_steps(
            distance_km, pace_zones, block_km=2.0
        )
    if builder_key == "alternating_mp_3k":
        return _steps_mod.build_alternating_mp_long_steps(
            distance_km, pace_zones, block_km=3.0
        )
    if builder_key == "fast_finish":
        return _steps_mod.build_fast_finish_long_steps(
            distance_km, pace_zones, finish_km=3.0
        )
    if builder_key == "fast_finish_2k":
        return _steps_mod.build_fast_finish_long_steps(
            distance_km, pace_zones, finish_km=2.0
        )
    if builder_key == "fast_finish_4k":
        return _steps_mod.build_fast_finish_long_steps(
            distance_km, pace_zones, finish_km=4.0
        )
    if builder_key == "rolling_hills":
        return _steps_mod.build_rolling_hills_long_steps(distance_km, pace_zones)
    if builder_key == "depletion":
        return _steps_mod.build_depletion_long_steps(distance_km, pace_zones)
    return _steps_mod.build_long_steps(distance_km, pace_zones, variant="easy")


class KeyWorkoutLibrary:
    """Provides race-specific key workout selection for plan generation."""

    @classmethod
    def get_for_phase(
        cls,
        target_distance: float,
        phase: str,
        week_in_phase: int,
        workout_type: str = "interval",
        terrain: Optional[str] = None,
    ) -> Optional[Dict]:
        """Select a key workout for the given distance, phase, and week.

        Args:
            target_distance: Race distance in km.
            phase:           Training phase (base, build, peak, taper).
            week_in_phase:   Zero-indexed week within the current phase.
            workout_type:    Requested workout type (interval, tempo, hill).
            terrain:         Terrain access ('flat' or None/hilly). Only
                             affects trail (30km) workout selection.

        Returns:
            A workout dict or None if no key workout applies.
        """
        # Key workouts only during build and peak
        if phase not in ("build", "peak"):
            return None

        candidates = [
            w for w in _WORKOUTS
            if target_distance in w["distances"]
            and phase in w["phases"]
            and w["type"] == workout_type
        ]

        # Filter by terrain for trail workouts
        if terrain == "flat":
            candidates = [w for w in candidates if "flat" in w.get("terrain", ["any"])]
        else:
            candidates = [
                w for w in candidates
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]

        if not candidates:
            return None

        # Rotate through candidates using week_in_phase
        return candidates[week_in_phase % len(candidates)]

    @classmethod
    def get_all_for_distance(cls, target_distance: float, terrain: Optional[str] = None) -> List[Dict]:
        """Return all key workouts for a race distance."""
        workouts = [w for w in _WORKOUTS if target_distance in w["distances"]]
        if terrain == "flat":
            workouts = [w for w in workouts if "flat" in w.get("terrain", ["any"])]
        elif terrain is not None:
            workouts = [
                w for w in workouts
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]
        return workouts

    @classmethod
    def inject_vdot_paces(cls, workout: Dict, vdot_zones: Optional[Dict]) -> Dict:
        """Enrich a workout description with specific VDOT-based paces.

        Args:
            workout:    Workout dict (not mutated -- returns a copy).
            vdot_zones: Output of ``VDOTCalculator.get_pace_zones()``.

        Returns:
            Copy of workout with pace-enriched description.
        """
        if not vdot_zones:
            return workout

        enriched = dict(workout)
        enriched["description"] = VDOTCalculator.inject_paces_into_description(
            enriched["description"], vdot_zones, enriched["type"]
        )
        enriched["structure"] = VDOTCalculator.inject_paces_into_description(
            enriched["structure"], vdot_zones, enriched["type"]
        )
        return enriched
