"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.
"""

import re
from typing import Any, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.vdot_calculator import VDOTCalculator


# Key workouts with hardcoded distances that need rewriting when the
# assigned distance differs from the description's implied distance.
# Each entry maps a workout id to (total_pattern, splits_pattern).
# total_pattern replaces "Run Xkm" / "Run X-Ykm" with the actual distance.
# splits_pattern is a callable(actual_distance) -> str for proportional splits.
_DISTANCE_REWRITES: Dict[str, tuple] = {
    "marathon_mp_long": (
        r"Run 25km total",
        lambda d: f"First {round(d * 0.60, 0):.0f}km at easy pace, then shift to marathon goal pace for the final {round(d * 0.40, 0):.0f}km",
    ),
    "marathon_progressive_long": (
        r"Run 28-30km\. First 20km",
        lambda d: f"Run {round(d, 0):.0f}km. First {round(d * 0.67, 0):.0f}km",
    ),
    "marathon_peak_progressive": (
        r"Run 28km total\. First 16km",
        lambda d: f"Run {round(d, 0):.0f}km total. First {round(d * 0.57, 0):.0f}km",
    ),
    "marathon_easy_long_fueling": (
        r"Run 30-32km",
        lambda d: f"Run {round(d, 0):.0f}km",
    ),
    "marathon_tempo_cutdown": (
        None,
        lambda d: f"Warm up {round(d * 0.10, 0):.0f}km easy. Run 2 x {round(d * 0.35, 0):.0f}km at threshold pace with 3 min easy jog recovery. Cool down {round(d * 0.10, 0):.0f}km easy.",
    ),
    "marathon_mp_cutdown": (
        None,
        lambda d: f"Warm up {round(d * 0.10, 0):.0f}km easy. Run 5 x 2km alternating between marathon pace and threshold pace, with 90s jog recovery between each. Cool down {round(d * 0.10, 0):.0f}km easy.",
    ),
    "half_progressive_long": (
        r"Run 14-16km total\. Start at easy pace for 10km",
        lambda d: f"Run {round(d, 0):.0f}km total. Start at easy pace for {round(d * 0.65, 0):.0f}km",
    ),
    "half_cutdown_long": (
        r"Run 15km in three 5km segments",
        lambda d: f"Run {round(d, 0):.0f}km in three equal segments",
    ),
    "half_race_pace_segments": (
        None,
        lambda d: f"Warm up 2km easy. Run 3 x {round(d * 0.25, 0):.0f}km at half marathon goal pace with 2 min easy jog recovery. Cool down 2km easy.",
    ),
    "half_threshold_cruise": (
        None,
        lambda d: f"Warm up 2km easy. Run 3 x {round(d * 0.20, 0):.0f}km at threshold pace with 90 seconds easy jog recovery. Cool down 2km easy.",
    ),
    "trail_flat_surge_fartlek": (
        r"Run 8 x 3 min",
        lambda d: f"Run 8 x 3 min",
    ),
    "trail_flat_soft_surface": (
        r"Run 2\.5-3 hours",
        lambda d: f"Run your long-run duration",
    ),
    "trail_time_on_feet": (
        r"Run 2\.5-3 hours",
        lambda d: f"Run your long-run duration",
    ),
    "trail_back_to_back": (
        r"Saturday: 20-22km.*?Sunday: 15-18km",
        lambda d: f"Saturday: {round(d * 0.57, 0):.0f}km trail run at easy effort on hilly terrain. Sunday: {round(d * 0.43, 0):.0f}km trail run at easy effort on fatigued legs",
    ),
    "trail_technical_terrain": (
        r"Run 8km",
        lambda d: f"Run {round(d * 0.80, 0):.0f}km",
    ),
    "10k_goal_pace_segments": (
        None,
        lambda d: f"Warm up 2km easy. Run 2 x {round(d * 0.25, 0):.0f}km at 10K goal pace with 3 min standing recovery. Cool down 2km easy.",
    ),
    "10k_tempo_progression": (
        None,
        lambda d: f"Warm up 2km easy. Run {round(d * 0.50, 0):.0f}km as a progression: first km at easy pace, each subsequent km 10-15 sec/km faster, finishing last km at 10K goal pace. Cool down 2km easy.",
    ),
    "10k_fartlek": (
        None,
        lambda d: f"Warm up 2km easy. Within a continuous run, alternate 6 x (3 min at 10K pace / 2 min easy jog). Cool down 2km easy.",
    ),
}


def _rewrite_key_workout_description(description: str, workout_id: str,
                                      actual_distance: float) -> str:
    """Rewrite hardcoded distances in a key workout description.

    Uses a lookup table of known patterns to replace specific distance
    references with values proportional to the actual assigned distance.
    Falls back to the original description if no rewrite rule matches.
    """
    rewrite = _DISTANCE_REWRITES.get(workout_id)
    if not rewrite:
        return description

    total_pattern, splits_fn = rewrite

    if total_pattern:
        description = re.sub(total_pattern, f"Run {round(actual_distance, 0):.0f}km", description)

    if splits_fn:
        splits_text = splits_fn(actual_distance)
        description = re.sub(
            r"(First \d+km.*?(?:final \d+km|last \d+km|descending pace|marathon pace))",
            splits_text,
            description,
            flags=re.DOTALL,
        )
        description = re.sub(
            r"(Warm up \d+km.*?Cool down \d+km.*?)(?:\.)?",
            splits_text + ".",
            description,
            flags=re.DOTALL,
        )
        if "Run 2 x" in splits_text or "Run 3 x" in splits_text or "Run 5 x" in splits_text:
            description = re.sub(
                r"Run \d+ x \d+km.*?(?:\.|$)",
                splits_text + ".",
                description,
                flags=re.DOTALL,
            )
        if "Within a continuous run" in splits_text:
            description = re.sub(
                r"Within a continuous run.*?(?:\.|$)",
                splits_text + ".",
                description,
                flags=re.DOTALL,
            )
        if "Saturday:" in splits_text:
            description = re.sub(
                r"Saturday:.*?(?:fatigued legs)\.",
                splits_text + ".",
                description,
                flags=re.DOTALL,
            )
        if "Run your long-run duration" in splits_text:
            description = re.sub(
                r"Run \d+(?:\.\d+)?-\d+(?:\.\d+)? hours",
                "your long-run duration",
                description,
            )

    return description

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
