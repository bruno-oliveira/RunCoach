"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.
"""

from typing import Dict, List, Optional

from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.vdot_calculator import VDOTCalculator

# Backward-compatible alias: tests and internal code import _WORKOUTS.
_WORKOUTS = WORKOUTS


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
