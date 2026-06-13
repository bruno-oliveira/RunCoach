"""Key-workout step builders and the per-workout builder registry.

``build_key_workout_steps`` is the single entry point that turns a key workout
into executable steps (structured-first: explicit steps -> steps_builder ->
running-fraction -> per-workout builder -> defensive easy default).
"""

from typing import Any, Callable, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.key_workout_library.rewrites import (
    _fartlek_reps,
    _mp_cutdown_reps,
    _over_under_reps,
    _pyramid_pattern,
    _vo2max_400_reps,
    _vo2max_km_reps,
    _yasso_800_reps,
    reconcile_key_workout_text,
)

# Key workouts whose on-foot running distance is only a fraction of the
# allocated budget — the remainder is spent on non-running drills (agility
# circuits, deliberate technical foot-placement work). The fraction is applied
# once to the distance in ``overlay_key_workout`` so the card distance, the
# executable steps, and the description (which now cites the distance directly)
# all agree. Without this the description cited ``d * fraction`` while the card
# showed the full budget, so the two numbers never matched.
_RUNNING_DISTANCE_FRACTION: Dict[str, float] = {
    "trail_flat_proprioception": 0.80,
    "trail_technical_terrain": 0.80,
}

# Structured-first step builders, keyed by workout id. Where present, steps are
# generated directly from the distance (mirroring the description rewrite)
# instead of being reverse-engineered from prose. Currently covers the
# fixed-distance rep sessions (e.g. N × 400 m), where the prose parser produced
# rep distances that contradicted the prescription. Other key workouts still
# fall through to the hardened parser inside build_key_workout_steps.
_KEY_WORKOUT_STEP_BUILDERS: Dict[
    str, Callable[[float, Optional[Dict]], List[Dict[str, Any]]]
] = {
    "5k_vo2max_400s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_vo2max_400_reps(d),
        rep_m=400,
        work_zone="I",
        recovery_label="90s easy jog recovery",
    ),
    "marathon_yasso_800s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_yasso_800_reps(d),
        rep_m=800,
        work_zone="I",
        recovery_label="equal-time jog recovery",
    ),
    # -- km-rep cruise / segment / cutdown sessions --
    "5k_cruise_intervals": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=4, work_zone="T"
    ),
    "10k_cruise_intervals": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=4, work_zone="T"
    ),
    "half_threshold_cruise": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=3, work_zone="T"
    ),
    "10k_goal_pace_segments": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=2, work_zone="10K"
    ),
    # -- VO2max km-rep interval variants (proportional reps) --
    "5k_vo2max_1000s": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=_vo2max_km_reps(d, default=5), work_zone="I", recovery_s=150
    ),
    "10k_vo2max_1000s": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=_vo2max_km_reps(d, default=5), work_zone="I", recovery_s=120
    ),
    "half_km_intervals": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=_vo2max_km_reps(d, default=5), work_zone="10K", recovery_s=90
    ),
    "marathon_km_intervals": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=_vo2max_km_reps(d, default=6), work_zone="10K", recovery_s=90
    ),
    "5k_race_pace_3km": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=2, work_zone="T", recovery_s=180
    ),
    "half_race_pace_segments": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=3, work_zone="M", recovery_s=120
    ),
    "marathon_tempo_cutdown": lambda d, pz: _steps_mod.build_km_rep_steps(
        d, pz, reps=2, work_zone="T", recovery_s=180
    ),
    # -- easy-start / faster-finish split long runs --
    "marathon_mp_long": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=0.60, finish_mult=0.40
    ),
    "marathon_progressive_long": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=0.67, finish_mult=0.33
    ),
    "marathon_peak_progressive": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=0.57, finish_mult=0.43
    ),
    "half_progressive_long": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=0.65, finish_mult=0.35
    ),
    "half_cutdown_long": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=1.0 / 3.0, finish_mult=2.0 / 3.0
    ),
    # -- fartlek / over-under (duration on-reps) --
    "10k_fartlek": lambda d, pz: _steps_mod.build_fartlek_steps(
        d,
        pz,
        reps=_fartlek_reps(d, default=6, lo=2, hi=8),
        on_s=180,
        off_s=120,
        on_zone="10K",
    ),
    "trail_flat_surge_fartlek": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=_fartlek_reps(d), on_s=180, off_s=120, on_zone="T"
    ),
    "trail_flat_over_under_intervals": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=6, on_s=180, off_s=120, on_zone="T"
    ),
    # -- base-phase light quality: strides, relaxed fartlek, relaxed cruise --
    "base_strides": lambda d, pz: _steps_mod.build_strides_steps(
        d, pz, reps=6, stride_s=20, recovery_s=60
    ),
    "base_hill_strides": lambda d, pz: _steps_mod.build_strides_steps(
        d,
        pz,
        reps=6,
        stride_s=15,
        recovery_s=60,
        work_zone="R",
        label="6 × 15s hill strides",
        effort="strong uphill",
        cue="hill",
    ),
    "base_light_fartlek": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=6, on_s=60, off_s=120, on_zone="10K", work_effort="relaxed-quick"
    ),
    "base_relaxed_cruise": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=2, on_s=360, off_s=120, on_zone="M", work_effort="steady"
    ),
    # -- true over-unders: alternating over/under threshold, no easy recovery --
    "10k_over_unders": lambda d, pz: _steps_mod.build_over_under_steps(
        d, pz, reps=_over_under_reps(d, default=5), over_s=60, under_s=120
    ),
    "half_over_unders": lambda d, pz: _steps_mod.build_over_under_steps(
        d, pz, reps=_over_under_reps(d, default=6), over_s=90, under_s=150
    ),
    "marathon_over_unders": lambda d, pz: _steps_mod.build_over_under_steps(
        d, pz, reps=_over_under_reps(d, default=6), over_s=120, under_s=180
    ),
    # -- single progressive block --
    "10k_tempo_progression": lambda d, pz: _steps_mod.build_progression_block_steps(
        d, pz, block_zone="10K"
    ),
    # -- continuous at a single zone --
    "5k_threshold_run": lambda d, pz: _steps_mod.build_continuous_quality_steps(
        d, pz, zone="T"
    ),
    "marathon_easy_long_fueling": lambda d, pz: (
        _steps_mod.build_continuous_quality_steps(d, pz, zone="E")
    ),
    "trail_flat_soft_surface": lambda d, pz: _steps_mod.build_continuous_quality_steps(
        d, pz, zone="E"
    ),
    # -- time-based hill / technique / hike sessions --
    "trail_elevation_repeats": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d, pz, reps=6, work_s=180, work_zone="I", cue="hard"
    ),
    "5k_hill_sprints": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d, pz, reps=8, work_s=60, work_zone="R", cue="hill"
    ),
    "trail_power_hike": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=5,
        work_s=300,
        work_zone="E",
        work_kind="walk",
        label="5 × 5 min power-hike",
        work_effort="power hike",
        recovery_s=180,
        recovery_kind="run",
        recovery_effort="run",
        recovery_label="Run flats and descents",
        recovery_zone="E",
    ),
    "trail_flat_power_walk": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=6,
        work_s=300,
        work_zone="E",
        work_kind="walk",
        label="6 × 5 min power-walk",
        work_effort="power walk",
        recovery_s=300,
        recovery_kind="run",
        recovery_effort="easy run",
        recovery_label="5 min easy run",
        recovery_zone="E",
    ),
    # -- distance-based downhill / cutdown reps --
    "trail_downhill_technique": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=6,
        rep_m=500,
        work_zone="E",
        recovery_label="hike back up for recovery",
    ),
    "marathon_mp_cutdown": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_mp_cutdown_reps(d),
        rep_m=2000,
        work_zone="M",
        recovery_label="90s jog recovery",
    ),
    # -- pyramid at race pace --
    "5k_pyramid": lambda d, pz: _steps_mod.build_pyramid_steps(
        d,
        pz,
        pattern=[int(x.strip().rstrip("m")) for x in _pyramid_pattern(d).split(",")],
        pace_zone="I",
    ),
    # -- easy continuous trail runs --
    "trail_time_on_feet": lambda d, pz: _steps_mod.build_easy_steps(d, pz),
    "trail_night_run": lambda d, pz: _steps_mod.build_easy_steps(d, pz),
}

# Sessions installed only by the intensive-weekend post-pass (via ``force_id``).
# They presuppose the weekend context (e.g. "fatigued from yesterday"), so they
# are excluded from the normal ``week_in_phase`` rotation to avoid appearing as


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
    if builder_key == "pyramid_trail":
        return _steps_mod.build_pyramid_steps(distance_km, pace_zones, pace_zone="T")
    if builder_key == "ladder_trail":
        return _steps_mod.build_ladder_steps(distance_km, pace_zones, pace_zone="T")
    if builder_key == "hike_run":
        return _steps_mod.build_hike_run_steps(distance_km, pace_zones)
    if builder_key == "back_to_back":
        return _steps_mod.build_back_to_back_steps(distance_km, pace_zones)
    if builder_key == "b2b_day2":
        steps = _steps_mod.build_long_steps(distance_km, pace_zones, variant="easy")
        for s in steps:
            if s.get("kind") == "run":
                s["note"] = "On fatigued legs from yesterday — hold easy effort"
                break
        return steps
    return _steps_mod.build_long_steps(distance_km, pace_zones, variant="easy")


def _inject_pace_into_steps(
    steps: List[Dict[str, Any]], pace_zones: Optional[Dict]
) -> List[Dict[str, Any]]:
    """Clone steps and fill in pace_str from pace_zones when missing."""
    if not pace_zones:
        return [dict(s) for s in steps]
    out = []
    for s in steps:
        new = dict(s)
        zone = new.get("pace_zone")
        if zone and not new.get("pace_str") and zone in pace_zones:
            new["pace_str"] = pace_zones[zone].get("pace_str")
        out.append(new)
    return out


def build_key_workout_steps(
    key_wk: Dict[str, Any],
    structure: str,
    distance_km: float,
    workout_type: str,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Build executable steps for a key workout from a single distance source.

    Dispatch order (structured-first): explicit ``steps`` → ``steps_builder``
    → single continuous block for fractional/prose runs → per-workout builder
    in ``_KEY_WORKOUT_STEP_BUILDERS`` → defensive easy-run default. Used by both
    ``overlay_key_workout`` (initial generation) and ``rebuild_key_workout``
    (adaptation / repair) so steps are always derived the same way.
    """
    if key_wk.get("steps"):
        return _inject_pace_into_steps(key_wk["steps"], pace_zones)
    if key_wk.get("steps_builder"):
        return _resolve_long_steps_builder(
            key_wk["steps_builder"], distance_km, pace_zones
        )
    if key_wk["id"] in _RUNNING_DISTANCE_FRACTION and distance_km > 0:
        return _steps_mod.build_easy_steps(distance_km, pace_zones)
    builder = _KEY_WORKOUT_STEP_BUILDERS.get(key_wk["id"])
    if builder is not None and distance_km > 0:
        return builder(distance_km, pace_zones)
    # Every key workout is covered by an explicit builder, a steps_builder, or
    # the running-fraction path above. This defensive default only guards a
    # future workout id added without a builder — it degrades to an easy run
    # rather than crashing.
    return _steps_mod.build_easy_steps(distance_km, pace_zones)


def rebuild_key_workout(
    workout: Dict[str, Any], pace_zones: Optional[Dict] = None
) -> bool:
    """Regenerate a key workout's prose, structure, steps and distance from a
    single source: the current ``workout['distance']``.

    Reconciles the description + structure, rebuilds the steps the same way
    generation does, then snaps ``distance`` to the executable steps total so
    the card, the steps and the description always agree. Distance-based
    sessions track the new distance; duration-defined ones (time-based reps)
    naturally settle back to their time-defined total. Returns True if the
    workout had a key overlay.
    """
    kid = workout.get("key_workout_id")
    if not kid:
        return False
    d = workout.get("distance", 0) or 0
    if d <= 0:
        return False
    # Local import breaks the builders <-> selection cycle (selection imports
    # build_key_workout_steps at module load; only this path needs the library).
    from app.core.training.key_workout_library.selection import KeyWorkoutLibrary

    key_wk = KeyWorkoutLibrary.get_by_id(kid)
    if not key_wk:
        return False
    reconcile_key_workout_text(workout, pace_zones)
    structure = workout.get("structure") or key_wk.get("structure", "")
    workout_type = workout.get("type") or key_wk.get("type", "interval")
    steps = build_key_workout_steps(key_wk, structure, d, workout_type, pace_zones)
    workout["steps"] = steps
    steps_total = _steps_mod._compute_distance_from_steps(steps)
    if steps_total > 0:
        workout["distance"] = round(steps_total, 1)
    return True
