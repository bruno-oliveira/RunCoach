"""Key-workout selection: candidate filtering, bracket gating, and overlay.

``KeyWorkoutLibrary`` picks a workout for a (distance, phase, week);
``overlay_key_workout`` installs the chosen workout's description, structure,
and steps onto a generated workout slot.
"""

from typing import Any, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library.builders import (
    _RUNNING_DISTANCE_FRACTION,
    build_key_workout_steps,
)
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _STRUCTURE_REWRITES,
    _derive_structure,
    _rewrite_key_workout_description,
)
from app.core.training.vdot_calculator import VDOTCalculator

# Long-ultra-only template: a short headlamp run during the peak phase to
# rehearse darkness pacing and gear. Bracketed via ``brackets`` so it never
# fires for short/standard plans (or road).
_LONG_ULTRA_NIGHT_RUN: Dict[str, Any] = {
    "id": "trail_night_run",
    "distances": [30.0],  # trail-tagged; trail_profile widens this to any bracket
    "brackets": ["long_ultra"],
    "phases": ["peak"],
    "type": "tempo",
    "terrain": ["any"],
    "name": "Headlamp Night Run",
    "structure": "45-60 min easy night run on trails with headlamp and hand torch",
    "description": (
        "After dark: 45-60 min easy effort on a familiar trail loop with a "
        "headlamp (and a backup hand torch). Practice the gear, the depth "
        "perception, and eating/drinking by feel. Run conservatively — a "
        "trip in the dark is the goal to avoid, not to recover from."
    ),
    "intensity": "low",
    "target_zone": 2,
    "pace_zone": "E",
    "rationale": (
        "100-mile races run through the night. Rehearsing in the dark "
        "lets you debug gear, fueling, and pacing while the stakes are low — "
        "not at 2am during the race."
    ),
}

# Backward-compatible alias: tests and internal code import _WORKOUTS.
_WORKOUTS = list(WORKOUTS) + [_LONG_ULTRA_NIGHT_RUN]


# Minimum workout distance for key workouts whose structure (time-based reps,
# technical-terrain blocks) doesn't fit the small budget allocated by the
# phase distribution. Without these floors a 6 × 3-min hill session ends up
# with a 0.65 km warm-up and a sub-3 km displayed total, even though the
# actual work covers ~3 km on its own. Apply by bumping ``actual_distance``
# in :func:`overlay_key_workout` before description / step generation.
_KEY_WORKOUT_MIN_DISTANCE_KM: Dict[str, float] = {
    "trail_elevation_repeats": 5.0,
    "trail_technical_terrain": 4.5,
    "trail_power_hike": 6.0,
    "trail_downhill_technique": 5.0,
    "5k_hill_sprints": 4.0,
    "trail_pyramid_intervals": 5.0,
    "trail_ladder_intervals": 5.0,
}


# Sessions installed only by the intensive-weekend post-pass (via ``force_id``).
# They presuppose the weekend context (e.g. "fatigued from yesterday"), so they
# are excluded from the normal ``week_in_phase`` rotation to avoid appearing as
# standalone sessions and to keep existing rotation expectations stable.
_ITW_ONLY_IDS = frozenset({"trail_hike_run_long", "trail_b2b_day2"})


_BRACKET_RESTRICTIONS: Dict[str, list] = {
    "trail_back_to_back": ["ultra", "long_ultra"],
    "trail_long_race_simulation": ["ultra", "long_ultra"],
    "trail_flat_long_race_sim": ["ultra", "long_ultra"],
    "trail_flat_long_fueling": ["standard", "ultra", "long_ultra"],
    "trail_power_hike": ["standard", "ultra", "long_ultra"],
    "trail_time_on_feet": ["standard", "ultra", "long_ultra"],
}


def _bracket_allowed(workout: Dict[str, Any], bracket: str) -> bool:
    explicit = workout.get("brackets")
    if explicit is not None:
        return bracket in explicit
    restriction = _BRACKET_RESTRICTIONS.get(workout.get("id", ""))
    if restriction is not None:
        return bracket in restriction
    return True


def _trail_aware_distance_filter(
    target_distance: float,
    trail_profile,
) -> List[Dict[str, Any]]:
    """Return workouts whose ``distances`` list matches the goal.

    For trail/ultra plans, every workout tagged with the legacy 30.0 sentinel
    is considered eligible (subject to bracket gating below). This unlocks
    the existing 15+ trail workout templates for 50/80/163 km plans without
    requiring a per-distance fan-out in every workout entry.
    """
    if trail_profile is not None:
        return [
            w
            for w in _WORKOUTS
            if 30.0 in w["distances"] or target_distance in w["distances"]
        ]
    return [w for w in _WORKOUTS if target_distance in w["distances"]]


def _filter_candidates(
    workout_type: str,
    target_distance: float,
    phase: str,
    terrain: Optional[str],
    trail_profile,
) -> List[Dict[str, Any]]:
    candidates = [
        w
        for w in _trail_aware_distance_filter(target_distance, trail_profile)
        if phase in w["phases"]
        and w["type"] == workout_type
        and w["id"] not in _ITW_ONLY_IDS
    ]

    # Terrain filter — flat-only or hilly/any otherwise.
    if terrain == "flat" or (
        terrain is None and trail_profile and trail_profile.elevation_class == "flat"
    ):
        candidates = [w for w in candidates if "flat" in w.get("terrain", ["any"])]
    elif trail_profile is not None or terrain is not None:
        candidates = [
            w
            for w in candidates
            if "any" in w.get("terrain", ["any"])
            or "hilly" in w.get("terrain", ["any"])
        ]

    # Bracket gating — ultra-specific workouts (e.g. back-to-back) only fire
    # for ultra/long_ultra plans.
    if trail_profile is not None:
        candidates = [
            w for w in candidates if _bracket_allowed(w, trail_profile.bracket)
        ]

    return candidates


def overlay_key_workout(
    workout: Dict[str, Any],
    workout_type: str,
    phase: str,
    target_distance: float,
    week_in_phase: int,
    terrain: Optional[str] = None,
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
    force_id: Optional[str] = None,
    max_distance: Optional[float] = None,
) -> None:
    """Attach key workout metadata, description, and steps for quality sessions.

    Replaces any existing ``segments`` with parsed ``steps`` so the template
    always renders session blocks that match the ``structure`` one-liner.

    When ``force_id`` is given, that specific key workout is installed
    (bypassing the ``week_in_phase`` rotation and the candidate filters) — used
    by the intensive-weekend post-pass to pin a chosen session.

    ``max_distance`` is the physiological ceiling (km) the resulting session may
    occupy — typically ``MAX_KEY_WORKOUT_VS_LONG_RUN * long_run``. A fixed
    library prescription whose steps would exceed it is trimmed (reps dropped,
    not rewritten short) so quality work never reaches the long run; sessions
    already within the ceiling keep their full prescribed length.
    """
    if workout_type not in ("interval", "tempo", "hill", "long"):
        return
    if phase not in ("base", "build", "peak"):
        return
    if workout.get("duration_min"):
        return

    if force_id is not None:
        key_wk = KeyWorkoutLibrary.get_by_id(force_id)
    else:
        key_wk = KeyWorkoutLibrary.get_for_phase(
            target_distance,
            phase,
            week_in_phase,
            workout_type,
            terrain=terrain,
            trail_profile=trail_profile,
        )
    if not key_wk:
        return
    if pace_zones:
        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)

    actual_distance = workout.get("distance", 0)
    floor = _KEY_WORKOUT_MIN_DISTANCE_KM.get(key_wk["id"], 0)
    if floor > 0:
        actual_distance = max(actual_distance, floor)
    frac = _RUNNING_DISTANCE_FRACTION.get(key_wk["id"])
    if frac is not None and actual_distance > 0:
        actual_distance = round(actual_distance * frac, 1)
    workout["distance"] = actual_distance
    description = key_wk["description"]
    if actual_distance > 0:
        description = _rewrite_key_workout_description(
            description,
            key_wk["id"],
            actual_distance,
        )

    rewritten = actual_distance > 0 and key_wk["id"] in _DISTANCE_REWRITES

    workout["description"] = description
    workout["key_workout_id"] = key_wk["id"]
    workout["key_workout_name"] = key_wk["name"]
    if key_wk["id"] in _STRUCTURE_REWRITES:
        workout["structure"] = _STRUCTURE_REWRITES[key_wk["id"]](actual_distance)
    elif rewritten:
        workout["structure"] = _derive_structure(description)
    else:
        workout["structure"] = key_wk["structure"]
    workout["key_workout_rationale"] = key_wk["rationale"]

    # Propagate the key workout's own intensity so the card classification
    # matches the session — without this the registry default (e.g. "high" for
    # interval/hill, "medium" for tempo) is kept even when the key workout is
    # intentionally lighter (base-phase strides have intensity="low" but were
    # shown as "high" because the overlay never overwrote the builder default).
    if "intensity" in key_wk:
        workout["intensity"] = key_wk["intensity"]

    # Structured-first step generation, shared with rebuild_key_workout. The
    # fractional/prose runs become a single block; only genuinely unparseable
    # prose reaches the hardened parser fallback.
    workout["steps"] = build_key_workout_steps(
        key_wk,
        workout["structure"],
        actual_distance,
        workout_type,
        pace_zones,
    )

    # Physiological ceiling: a fixed prescription (e.g. 8 × 500 m, or a
    # time-defined hike-run) can run longer than the runner's long run on a
    # low-mileage plan. Trim it to ``max_distance`` by dropping reps so the
    # quality day never reaches the long run, while leaving sessions that
    # already fit at their full prescribed length.
    if max_distance and max_distance > 0:
        workout["steps"] = _steps_mod.fit_steps_to_distance(
            workout["steps"], max_distance
        )

    # Reconcile displayed total with what the runner will actually cover —
    # duration-based reps (e.g. 6 × 3 min hard) contributed nothing to the
    # phase-allocated budget, so the pre-overlay ``distance`` undercounts
    # quality work. Recompute from the executable steps (pace × time fills
    # in for time-based reps) so weekly mileage and the workout card match.
    # ``workout['distance']`` is what the runner will actually cover;
    # ``actual_distance`` is the budget the description and steps were
    # rendered/parsed against. They differ when duration-based reps add
    # mileage on top of the budgeted warm-up + cool-down (e.g. 6 × 3-min
    # hill repeats). The description and step list stay rendered against
    # ``actual_distance`` — that's the value baked into the formulas
    # (warm-up size, main_km splits) and the parser (implicit wu/cd) — so
    # the cited numbers match the steps. The displayed total reflects
    # actual coverage so weekly mileage adds up.
    steps_total_km, fully_priced = _steps_mod.compute_distance_from_steps_checked(
        workout["steps"]
    )
    if steps_total_km > 0:
        if fully_priced:
            workout["distance"] = round(steps_total_km, 1)
        else:
            # Some duration reps couldn't be priced, so the steps total is a
            # lower bound. Never shrink the session below its budget on
            # incomplete math (this halved fartleks to warm-up + cool-down).
            workout["distance"] = round(max(actual_distance, steps_total_km), 1)

    workout.pop("segments", None)


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
        trail_profile=None,
    ) -> Optional[Dict]:
        """Select a key workout for the given distance, phase, and week.

        Args:
            target_distance: Race distance in km.
            phase:           Training phase (base, build, peak, taper).
            week_in_phase:   Zero-indexed week within the current phase.
            workout_type:    Requested workout type (interval, tempo, hill).
            terrain:         Terrain access string ('flat' or rolling/hilly/
                             mountainous). Only affects trail selection.
            trail_profile:   Preferred input for trail/ultra plans. When
                             present, trail-tagged workouts (those listing
                             30.0 in their ``distances``) become eligible
                             for any trail bracket and are further filtered
                             by the workout's optional ``brackets`` field.

        Returns:
            A workout dict or None if no key workout applies.
        """
        # Key workouts fire in base (light strides/fartlek only — the catalog
        # gates which sessions are base-eligible via their ``phases`` list),
        # build, and peak. Taper stays sharpener-only via the distribution.
        if phase not in ("base", "build", "peak"):
            return None

        candidates = _filter_candidates(
            workout_type,
            target_distance,
            phase,
            terrain,
            trail_profile,
        )
        if not candidates:
            return None

        # Rotate through candidates using week_in_phase
        return candidates[week_in_phase % len(candidates)]

    @classmethod
    def get_by_id(cls, workout_id: str) -> Optional[Dict]:
        """Return the key workout with the given id, or None.

        Bypasses phase/terrain/bracket filtering and rotation — the caller
        (intensive-weekend post-pass) has already chosen the session.
        """
        for w in _WORKOUTS:
            if w.get("id") == workout_id:
                return w
        return None

    @classmethod
    def get_all_for_distance(
        cls, target_distance: float, terrain: Optional[str] = None, trail_profile=None
    ) -> List[Dict]:
        """Return all key workouts for a race distance."""
        workouts = [
            w
            for w in _trail_aware_distance_filter(target_distance, trail_profile)
            if w["id"] not in _ITW_ONLY_IDS
        ]
        if terrain == "flat" or (
            terrain is None
            and trail_profile
            and trail_profile.elevation_class == "flat"
        ):
            workouts = [w for w in workouts if "flat" in w.get("terrain", ["any"])]
        elif terrain is not None or trail_profile is not None:
            workouts = [
                w
                for w in workouts
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]
        if trail_profile is not None:
            workouts = [
                w for w in workouts if _bracket_allowed(w, trail_profile.bracket)
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
