"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during
Build and Peak phases to make training plans feel coached, not generated.
"""

import re
from typing import Any, Callable, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.hr_zone_calculator import WORKOUT_ZONE_MAP
from app.core.training.key_workout_data import WORKOUTS
from app.core.training.vdot_calculator import VDOTCalculator


def _wu_cd(d: float) -> tuple:
    """Return (warmup_km, cooldown_km) matching workout_steps._wucd_m exactly.

    Uses integer-meter rounding so the description-level distances align with
    the executable steps; rounding to 0.1 km here drifted by ~100 m versus
    the steps and made displayed totals diverge from descriptions.
    """
    total_m = int(round(d * 1000))
    wu_m = min(2000, max(500, int(round(total_m * 0.25))))
    return (wu_m / 1000.0, wu_m / 1000.0)


def _mp_cutdown_reps(d: float) -> int:
    """2km-rep count for marathon_mp_cutdown, bucketed by distance.

    Each rep is 2km of work + ~0.3km recovery jog (~2.3km total).
    Combined with ~10% warmup + ~10% cooldown of d, the buckets ensure
    the structure fits inside the assigned budget.
    """
    if d < 8:
        return 2
    if d < 12:
        return 3
    if d < 16:
        return 4
    if d < 20:
        return 5
    return 6


def _vo2max_400_reps(d: float) -> int:
    """Scale 400m VO2max reps to fit distance d.

    Each rep is ~0.4km work + ~0.3km easy jog recovery (~0.7km total).
    Reps clamped to [4, 12] so the workout stays recognizable.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    reps = round(main_km / 0.7)
    return max(4, min(12, reps))


def _pyramid_pattern(d: float) -> str:
    """Pick a pyramid pattern that fits within distance d.

    Equal-distance recovery jogs roughly double the work-km cost, so a
    full 3.2km of reps needs ~6.4km of main-set room.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    if main_km >= 6.0:
        return "200m, 400m, 600m, 800m, 600m, 400m, 200m"
    if main_km >= 3.4:
        return "200m, 400m, 600m, 400m, 200m"
    return "200m, 400m, 400m, 200m"


def _fartlek_reps(d: float, on_min: int = 3, off_min: int = 2,
                  pace_min_per_km: float = 6.0,
                  default: int = 8, lo: int = 3, hi: int = 10) -> int:
    """Scale fartlek rep count to fit distance d.

    A "set" of (on_min hard / off_min easy) covers roughly
    ``(on_min + off_min) / pace_min_per_km`` km. Reps are capped to a sane
    range so structures stay recognizable across distances.
    """
    wu, cd = _wu_cd(d)
    main_km = max(0.0, d - wu - cd)
    set_km = (on_min + off_min) / pace_min_per_km
    if set_km <= 0:
        return default
    reps = round(main_km / set_km)
    return max(lo, min(hi, reps))


# Each entry generates a complete description from the actual distance.
_DISTANCE_REWRITES: Dict[str, Callable[[float], str]] = {
    "5k_vo2max_400s": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run {_vo2max_400_reps(d)} x 400m at 5K pace "
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
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run pyramid: {_pyramid_pattern(d)} "
        f"— all at 5K pace with equal-distance recovery jogs. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "marathon_mp_long": lambda d: (
        f"Run {d:.1f}km: first {d * 0.60:.1f}km easy, "
        f"last {d * 0.40:.1f}km at marathon pace. "
        f"Take a gel at {d * 0.32:.1f}km and {d * 0.64:.1f}km to practice race fueling."
    ),
    "marathon_progressive_long": lambda d: (
        f"Run {d:.1f}km: first {d * 0.67:.1f}km easy, "
        f"last {d * 0.33:.1f}km at marathon pace. "
        f"Run the finish as 2km segments, each 5-10s/km faster than the last. "
        f"Practice fueling every 5km."
    ),
    "marathon_peak_progressive": lambda d: (
        f"Run {d:.1f}km: first {d * 0.57:.1f}km easy, "
        f"last {d * 0.43:.1f}km at marathon pace. "
        f"Run the finish as 3km segments, each 5-10s/km faster than the last."
    ),
    "marathon_easy_long_fueling": lambda d: (
        f"Run {d:.1f}km continuous at easy conversational pace. "
        f"Take a gel or fuel every 5km starting at km 10. Practice your exact race-day nutrition strategy. "
        f"Walk 1 min after each fuel stop if needed."
    ),
    "marathon_tempo_cutdown": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run 2 x {round(max(1.0, (d - 2 * _wu_cd(d)[0]) / 2), 1):g}km at threshold pace with 3 min easy jog recovery. "
        f"Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "marathon_mp_cutdown": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run {_mp_cutdown_reps(d)} x 2km "
        f"alternating between marathon pace and threshold pace "
        f"with 90s jog recovery between each. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "half_progressive_long": lambda d: (
        f"Run {d:.1f}km: first {d * 0.65:.1f}km easy, "
        f"last {d * 0.35:.1f}km at marathon pace. "
        f"No warm-up needed — the easy start IS the warm-up."
    ),
    "half_cutdown_long": lambda d: (
        f"Run {d:.1f}km: first {d / 3:.1f}km easy, "
        f"last {d * 2 / 3:.1f}km at marathon pace. "
        f"Run as 3 segments, each 15s/km faster than the last."
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
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run {_fartlek_reps(d)} x (3 min at hill-repeat effort / 2 min easy jog) on varied terrain "
        f"(grass, dirt path, or trail). Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "trail_flat_soft_surface": lambda d: (
        f"Run {d:.1f}km continuous at easy effort on soft surface "
        f"(grass, dirt trails, beach, or gravel paths). "
        f"The soft surface increases energy cost 10-15% vs pavement. "
        f"Walk 2 min every 45 min. Practice race fueling."
    ),
    "trail_time_on_feet": lambda d: (
        f"Run {d:.1f}km on trails at easy conversational effort. "
        f"Walk steep uphills (>15% grade) to conserve energy. Practice race fueling every 30 min."
    ),
    "trail_back_to_back": lambda d: (
        f"Saturday: {d * 0.57:.1f}km trail run at easy effort on hilly terrain. "
        f"Sunday: {d * 0.43:.1f}km trail run at easy effort on fatigued legs. "
        f"Practice race fueling on both days."
    ),
    "trail_technical_terrain": lambda d: (
        f"Find a technical trail with rocks, roots, and uneven surface. "
        f"Run {d * 0.80:.1f}km at moderate effort, focusing on foot placement, "
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
    "10k_cruise_intervals": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Run 4 x {round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 4, 1):g}km "
        f"at threshold pace with 60 seconds easy jog between reps. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "10k_fartlek": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Within a continuous run, "
        f"alternate {_fartlek_reps(d, default=6, lo=3, hi=8)} x (3 min at 10K pace / 2 min easy jog). "
        f"Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "5k_hill_sprints": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. Find a moderate hill (4-6% grade). "
        f"Run 8-10 x 60 seconds hard uphill with easy jog back down. "
        f"Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "marathon_yasso_800s": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy. "
        f"Run {max(6, min(10, round((d - _wu_cd(d)[0] - _wu_cd(d)[1]) / 1.6))):g} x 800m "
        f"at VO2max pace with equal-time recovery jog. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "trail_elevation_repeats": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km easy on flat. Find a trail hill (6-10% grade). "
        f"Run 6-8 x 3 min hard uphill, driving arms and shortening stride. "
        f"Jog back down for recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "trail_power_hike": lambda d: (
        f"On a hilly trail loop: power-hike steep uphills for 5 min "
        f"(arms pumping, long strides), then run the flats and downhills. "
        f"Repeat 5 times. Plan for ~60-75 min total."
    ),
    "trail_downhill_technique": lambda d: (
        f"Warm up {_wu_cd(d)[0]:g}km on flat. "
        f"Find a trail descent (5-8% grade, 400-600m). Run 6-8 downhill repeats "
        f"focusing on quick cadence, slight forward lean, and soft landings. "
        f"Hike back up for recovery. Cool down {_wu_cd(d)[1]:g}km easy."
    ),
    "trail_flat_power_walk": lambda d: (
        f"Alternate 5 min maximum-effort power walking with 5 min easy running "
        f"x 6 sets. Plan for ~60 min total. Max-effort power walking at "
        f"9-10 min/km builds the specific muscular endurance for race-day hiking."
    ),
    "trail_flat_proprioception": lambda d: (
        f"Run {d * 0.80:.1f}km alternating surfaces every 1-2km: pavement, "
        f"grass, gravel, dirt. Every 2km, stop for a 2-min agility circuit: "
        f"10 single-leg hops each side, 20m lateral shuffles, 20m backward running."
    ),

    # -- Long-run variants (Half Marathon) --
    "half_long_alternating_mp": lambda d: (
        f"Run {d:.1f}km alternating 2 km easy and 2 km at "
        f"marathon pace. No rest between blocks. The switching rehearses "
        f"race-pace discipline on fatigued legs."
    ),
    "half_long_fast_finish": lambda d: (
        f"Run {d:.1f}km with the first portion at easy pace, "
        f"then accelerate into the final 3 km at threshold pace. "
        f"Build effort into the last kilometer."
    ),
    "half_long_rolling_hills": lambda d: (
        f"Run {d:.1f}km on a rolling hills route. "
        f"Keep effort even — push on the climbs, float on the descents. "
        f"Do NOT chase pace on the flats."
    ),

    # -- Long-run variants (Marathon) --
    "marathon_long_alternating_mp": lambda d: (
        f"Run {d:.1f}km alternating 3 km easy and 3 km at "
        f"marathon pace. No stops. The back-to-back pace changes simulate "
        f"late-race moments where you must hold form."
    ),
    "marathon_long_fast_finish": lambda d: (
        f"Run {d:.1f}km easy, then finish with the last 4 km "
        f"at threshold pace. Build effort kilometer by kilometer — the "
        f"last km should be your fastest."
    ),
    "marathon_long_depletion": lambda d: (
        f"Run {d:.1f}km fasted (pre-breakfast). Water only "
        f"during the run — no carbs. Keep effort conservative; run slower "
        f"than your normal long-run pace."
    ),
    "marathon_long_rolling_hills": lambda d: (
        f"Run {d:.1f}km on a rolling hills route. Hold even "
        f"effort throughout — the hills become natural fartlek intervals "
        f"without breaking rhythm."
    ),

    # -- Long-run variants (10K) --
    "10k_long_fast_finish": lambda d: (
        f"Run {d:.1f}km easy, then finish with the last 2 km "
        f"at threshold pace. A miniature version of the classic "
        f"marathon fast-finish long run."
    ),

    # -- Long-run variants (Trail 30K — hilly) --
    "trail_long_fast_finish": lambda d: (
        f"Run {d:.1f}km on trails at easy effort. In the "
        f"final 3 km, pick up to tempo effort — push the climbs, float "
        f"the descents. Finish with purpose, not a sprint."
    ),
    "trail_long_rolling_hills": lambda d: (
        f"Run {d:.1f}km on the hilliest trail you can find. "
        f"Keep effort even throughout — push the climbs at threshold effort, "
        f"recover on the descents. Walk uphills steeper than 15% grade."
    ),
    "trail_long_race_simulation": lambda d: (
        f"Run {d:.1f}km on trails that approximate race "
        f"terrain. Run at planned race effort — walk uphills you plan to "
        f"walk on race day. Practice your exact fueling strategy: take "
        f"nutrition every 30 min. Treat this as a dress rehearsal."
    ),

    # -- Long-run variants (Trail 30K — flat) --
    "trail_flat_long_fast_finish": lambda d: (
        f"Run {d:.1f}km on the softest surface available "
        f"(grass, dirt, gravel). In the final 3 km, pick up to tempo "
        f"effort. The soft surface adds 10-15% metabolic cost, partially "
        f"compensating for lack of hills."
    ),
    "trail_flat_long_fueling": lambda d: (
        f"Run {d:.1f}km at easy conversational pace. Take "
        f"your planned race nutrition every 30 min starting at minute 30. "
        f"Test exactly what you'll eat and drink on race day. Walk 1 min "
        f"after each fuel stop if needed."
    ),
    "trail_flat_long_race_sim": lambda d: (
        f"Run {d:.1f}km alternating surfaces (grass, dirt, "
        f"gravel, pavement) every 2-3 km. Run at planned race effort. "
        f"Practice your exact fueling strategy. Treat this as a dress "
        f"rehearsal for race day."
    ),
}


_STRUCTURE_REWRITES: Dict[str, Callable[[float], str]] = {
    # Half Marathon long runs
    "half_long_alternating_mp": lambda d: f"{d:.1f}km alternating 2km easy / 2km marathon pace",
    "half_long_fast_finish": lambda d: f"{d:.1f}km with last 3km at threshold pace",
    "half_long_rolling_hills": lambda d: f"{d:.1f}km on rolling hills at even effort",

    # Marathon long runs
    "marathon_long_alternating_mp": lambda d: f"{d:.1f}km alternating 3km easy / 3km marathon pace",
    "marathon_long_fast_finish": lambda d: f"{d:.1f}km easy with last 4km at threshold pace",
    "marathon_long_depletion": lambda d: f"{d:.1f}km fasted long run — water only",
    "marathon_long_rolling_hills": lambda d: f"{d:.1f}km on rolling hills at steady effort",

    # 10K long run
    "10k_long_fast_finish": lambda d: f"{d:.1f}km easy with last 2km at threshold pace",

    # Trail hilly long runs
    "trail_long_fast_finish": lambda d: f"{d:.1f}km trail with last 3km at tempo effort",
    "trail_long_rolling_hills": lambda d: f"{d:.1f}km on hilly trail at even effort",
    "trail_long_race_simulation": lambda d: f"{d:.1f}km trail at race effort with fueling every 30min",

    # Trail flat long runs
    "trail_flat_long_fast_finish": lambda d: f"{d:.1f}km soft-surface with last 3km at tempo",
    "trail_flat_long_fueling": lambda d: f"{d:.1f}km easy with nutrition practice every 30min",
    "trail_flat_long_race_sim": lambda d: f"{d:.1f}km varied-surface at race effort with fueling",

    # Trail flat tempo (soft surface)
    "trail_flat_soft_surface": lambda d: f"{d:.1f}km continuous at easy effort on soft surface",
}


def _rewrite_key_workout_description(description: str, workout_id: str,
                                      actual_distance: float) -> str:
    """Generate a distance-appropriate description for a key workout."""
    rewrite_fn = _DISTANCE_REWRITES.get(workout_id)
    if not rewrite_fn:
        return description
    return rewrite_fn(actual_distance)


def _derive_structure(description: str) -> str:
    """Strip warm-up/cool-down sentences to get a structure one-liner."""
    s = re.sub(r"Warm up [\d.]+km easy[^.]*\.\s*", "", description)
    s = re.sub(r"\s*Cool down [\d.]+km easy[^.]*\.", "", s)
    s = re.sub(r"^Run\s+", "", s.strip())
    s = re.sub(r"^Find a[^.]*\.\s*", "", s.strip())
    return s.strip()


def reconcile_key_workout_text(workout: Dict[str, Any]) -> bool:
    """Re-render description+structure from current ``workout['distance']``.

    Returns True if the workout had a key-workout overlay and was rewritten,
    False otherwise. Callers use this after any operation that mutates a
    key workout's distance (scaling, capping, transfer) so that the
    description, structure and distance stay in lockstep.
    """
    kid = workout.get('key_workout_id')
    if not kid:
        return False
    d = workout.get('distance', 0) or 0
    if d <= 0:
        return False
    if kid in _DISTANCE_REWRITES:
        workout['description'] = _DISTANCE_REWRITES[kid](d)
        if kid in _STRUCTURE_REWRITES:
            workout['structure'] = _STRUCTURE_REWRITES[kid](d)
        else:
            workout['structure'] = _derive_structure(workout['description'])
    elif kid in _STRUCTURE_REWRITES:
        workout['structure'] = _STRUCTURE_REWRITES[kid](d)
    return True

# Long-ultra-only template: a short headlamp run during the peak phase to
# rehearse darkness pacing and gear. Bracketed via ``brackets`` so it never
# fires for short/standard plans (or road).
_LONG_ULTRA_NIGHT_RUN: Dict[str, Any] = {
    "id": "trail_night_run",
    "distances": [30.0],   # trail-tagged; trail_profile widens this to any bracket
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


# --- Trail bracket gating ---------------------------------------------------
# A workout's optional ``brackets`` field restricts it to specific trail
# bracket(s). Without the field the workout is allowed for any trail
# bracket (and any non-trail distance, when applicable).
#
# Existing trail workouts that should NOT fire for short trail plans
# (15 km / 8-week prep is the wrong place for a 50 km race simulation):

# Minimum workout distance for key workouts whose structure (time-based reps,
# technical-terrain blocks) doesn't fit the small budget allocated by the
# phase distribution. Without these floors a 6 × 3-min hill session ends up
# with a 0.65 km warm-up and a sub-3 km displayed total, even though the
# actual work covers ~3 km on its own. Apply by bumping ``actual_distance``
# in :func:`overlay_key_workout` before description / step generation.
_KEY_WORKOUT_MIN_DISTANCE_KM: Dict[str, float] = {
    "trail_elevation_repeats": 5.0,
    "trail_technical_terrain": 4.5,
    "trail_power_hike":         6.0,
    "trail_downhill_technique": 5.0,
    "5k_hill_sprints":          4.0,
}


_BRACKET_RESTRICTIONS: Dict[str, list] = {
    "trail_back_to_back":            ["ultra", "long_ultra"],
    "trail_long_race_simulation":    ["ultra", "long_ultra"],
    "trail_flat_long_race_sim":      ["ultra", "long_ultra"],
    "trail_flat_long_fueling":       ["standard", "ultra", "long_ultra"],
    "trail_power_hike":              ["standard", "ultra", "long_ultra"],
    "trail_time_on_feet":            ["standard", "ultra", "long_ultra"],
}


def _bracket_allowed(workout: Dict[str, Any], bracket: str) -> bool:
    explicit = workout.get("brackets")
    if explicit is not None:
        return bracket in explicit
    restriction = _BRACKET_RESTRICTIONS.get(workout.get("id"))
    if restriction is not None:
        return bracket in restriction
    return True


def _trail_aware_distance_filter(
    target_distance: float, trail_profile,
) -> List[Dict[str, Any]]:
    """Return workouts whose ``distances`` list matches the goal.

    For trail/ultra plans, every workout tagged with the legacy 30.0 sentinel
    is considered eligible (subject to bracket gating below). This unlocks
    the existing 15+ trail workout templates for 50/80/163 km plans without
    requiring a per-distance fan-out in every workout entry.
    """
    if trail_profile is not None:
        return [w for w in _WORKOUTS if 30.0 in w["distances"] or target_distance in w["distances"]]
    return [w for w in _WORKOUTS if target_distance in w["distances"]]


def _filter_candidates(
    workout_type: str,
    target_distance: float,
    phase: str,
    terrain: Optional[str],
    trail_profile,
) -> List[Dict[str, Any]]:
    candidates = [
        w for w in _trail_aware_distance_filter(target_distance, trail_profile)
        if phase in w["phases"] and w["type"] == workout_type
    ]

    # Terrain filter — flat-only or hilly/any otherwise.
    if terrain == "flat" or (trail_profile and trail_profile.elevation_class == "flat"):
        candidates = [w for w in candidates if "flat" in w.get("terrain", ["any"])]
    elif trail_profile is not None or terrain is not None:
        candidates = [
            w for w in candidates
            if "any" in w.get("terrain", ["any"])
            or "hilly" in w.get("terrain", ["any"])
        ]

    # Bracket gating — ultra-specific workouts (e.g. back-to-back) only fire
    # for ultra/long_ultra plans.
    if trail_profile is not None:
        candidates = [w for w in candidates if _bracket_allowed(w, trail_profile.bracket)]

    return candidates


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


def _inject_pace_into_steps(steps: List[Dict[str, Any]],
                            pace_zones: Optional[Dict]) -> List[Dict[str, Any]]:
    """Clone steps and fill in pace_str from pace_zones when missing."""
    if not pace_zones:
        return [dict(s) for s in steps]
    out = []
    for s in steps:
        new = dict(s)
        zone = new.get('pace_zone')
        if zone and not new.get('pace_str') and zone in pace_zones:
            new['pace_str'] = pace_zones[zone].get('pace_str')
        out.append(new)
    return out


def overlay_key_workout(
    workout: Dict[str, Any],
    workout_type: str,
    phase: str,
    target_distance: float,
    week_in_phase: int,
    terrain: Optional[str] = None,
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
) -> None:
    """Attach key workout metadata, description, and steps for quality sessions.

    Replaces any existing ``segments`` with parsed ``steps`` so the template
    always renders session blocks that match the ``structure`` one-liner.
    """
    if workout_type not in ('interval', 'tempo', 'hill', 'long'):
        return
    if phase not in ('build', 'peak'):
        return
    if workout.get('duration_min'):
        return

    key_wk = KeyWorkoutLibrary.get_for_phase(
        target_distance, phase, week_in_phase, workout_type,
        terrain=terrain, trail_profile=trail_profile,
    )
    if not key_wk:
        return
    if pace_zones:
        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)

    actual_distance = workout.get('distance', 0)
    floor = _KEY_WORKOUT_MIN_DISTANCE_KM.get(key_wk['id'], 0)
    if floor > 0:
        actual_distance = max(actual_distance, floor)
        workout['distance'] = actual_distance
    description = key_wk['description']
    if actual_distance > 0:
        description = _rewrite_key_workout_description(
            description, key_wk['id'], actual_distance,
        )

    rewritten = actual_distance > 0 and key_wk['id'] in _DISTANCE_REWRITES

    workout['description'] = description
    workout['key_workout_id'] = key_wk['id']
    workout['key_workout_name'] = key_wk['name']
    if key_wk['id'] in _STRUCTURE_REWRITES:
        workout['structure'] = _STRUCTURE_REWRITES[key_wk['id']](actual_distance)
    elif rewritten:
        workout['structure'] = _derive_structure(description)
    else:
        workout['structure'] = key_wk['structure']
    workout['key_workout_rationale'] = key_wk['rationale']

    if key_wk.get('steps'):
        workout['steps'] = _inject_pace_into_steps(key_wk['steps'], pace_zones)
    elif key_wk.get('steps_builder'):
        workout['steps'] = _resolve_long_steps_builder(
            key_wk['steps_builder'], workout.get('distance', 0), pace_zones,
        )
    else:
        workout['steps'] = _steps_mod.parse_key_workout_steps(
            workout['structure'], pace_zones, workout_type,
            default_zone=key_wk.get('pace_zone'),
            total_distance_km=actual_distance,
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
    steps_total_km = _steps_mod._compute_distance_from_steps(workout['steps'])
    if steps_total_km > 0:
        workout['distance'] = round(steps_total_km, 1)

    workout.pop('segments', None)


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
        # Key workouts only during build and peak
        if phase not in ("build", "peak"):
            return None

        candidates = _filter_candidates(
            workout_type, target_distance, phase, terrain, trail_profile,
        )
        if not candidates:
            return None

        # Rotate through candidates using week_in_phase
        return candidates[week_in_phase % len(candidates)]

    @classmethod
    def get_all_for_distance(cls, target_distance: float, terrain: Optional[str] = None,
                             trail_profile=None) -> List[Dict]:
        """Return all key workouts for a race distance."""
        workouts = _trail_aware_distance_filter(target_distance, trail_profile)
        if terrain == "flat" or (trail_profile and trail_profile.elevation_class == "flat"):
            workouts = [w for w in workouts if "flat" in w.get("terrain", ["any"])]
        elif terrain is not None or trail_profile is not None:
            workouts = [
                w for w in workouts
                if "any" in w.get("terrain", ["any"])
                or "hilly" in w.get("terrain", ["any"])
            ]
        if trail_profile is not None:
            workouts = [w for w in workouts if _bracket_allowed(w, trail_profile.bracket)]
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
