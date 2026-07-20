"""Key-workout step builders and the per-workout builder registry.

``build_key_workout_steps`` is the single entry point that turns a key workout
into executable steps (structured-first: explicit steps -> steps_builder ->
running-fraction -> per-workout builder -> defensive easy default).
"""

from typing import Any, Callable, Dict, List, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.key_workout_library.rewrites import (
    _FLAT_PYRAMID_PATTERNS,
    _HILL_PYRAMID_PATTERNS,
    _compound_400_200_reps,
    _compound_800_400_reps,
    _duration_pyramid_min,
    _fartlek_reps,
    _mile_rep_reps,
    _mp_cutdown_reps,
    _on_off_k_reps,
    _over_under_reps,
    _pyramid_pattern,
    _road_pyramid_pattern_m,
    _rolling_400_reps,
    _thirty_thirty_reps,
    _vo2max_400_reps,
    _vo2max_km_reps,
    _yasso_800_reps,
    canonical_plan,
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


def _canonical_meter_reps(
    wid: str,
    work_zone: str,
    recovery_label: str = "easy jog recovery",
) -> Callable[[float, Optional[Dict]], List[Dict[str, Any]]]:
    """Step builder for canonical-rep sessions.

    ``canonical_plan`` (shared with the prose rewrites) picks a round-number
    rep distance and a count that fills the budget; the leftover becomes the
    recovery jogs, so the session prices to its assigned distance while each
    rep stays canonical ("4 × 1 km", never "4 × 1.7 km").
    """

    def _build(d: float, pz: Optional[Dict]) -> List[Dict[str, Any]]:
        rep_m, count = canonical_plan(wid, d)
        return _steps_mod.build_meter_rep_steps(
            d,
            pz,
            reps=count,
            rep_m=rep_m,
            work_zone=work_zone,
            recovery_label=recovery_label,
        )

    return _build


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
    # -- km-rep cruise / segment / cutdown sessions (canonical reps) --
    "5k_cruise_intervals": _canonical_meter_reps("5k_cruise_intervals", "T"),
    "10k_cruise_intervals": _canonical_meter_reps("10k_cruise_intervals", "T"),
    "half_threshold_cruise": _canonical_meter_reps("half_threshold_cruise", "T"),
    "10k_goal_pace_segments": _canonical_meter_reps("10k_goal_pace_segments", "10K"),
    # -- VO2max km-rep interval variants (canonical 1000 m reps) --
    "5k_vo2max_1000s": _canonical_meter_reps("5k_vo2max_1000s", "I"),
    "10k_vo2max_1000s": _canonical_meter_reps("10k_vo2max_1000s", "I"),
    "half_km_intervals": _canonical_meter_reps("half_km_intervals", "10K"),
    "marathon_km_intervals": _canonical_meter_reps("marathon_km_intervals", "10K"),
    "5k_race_pace_3km": _canonical_meter_reps("5k_race_pace_3km", "T"),
    "half_race_pace_segments": _canonical_meter_reps("half_race_pace_segments", "M"),
    "marathon_tempo_cutdown": _canonical_meter_reps("marathon_tempo_cutdown", "T"),
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
    # -- 30/30 VO2max intervals (short on/off couplets) --
    "5k_thirty_thirties": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=_thirty_thirty_reps(d), on_s=30, off_s=30, on_zone="I"
    ),
    "10k_thirty_thirties": lambda d, pz: _steps_mod.build_fartlek_steps(
        d, pz, reps=_thirty_thirty_reps(d), on_s=30, off_s=30, on_zone="I"
    ),
    # -- mile (1600 m) repeats --
    "10k_mile_repeats": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_mile_rep_reps(d),
        rep_m=1600,
        work_zone="T",
        recovery_label="90s easy jog recovery",
    ),
    "half_mile_repeats": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_mile_rep_reps(d),
        rep_m=1600,
        work_zone="10K",
        recovery_label="90s easy jog recovery",
    ),
    # -- marathon-pace blocks (canonical 2-5 km blocks) --
    "marathon_mp_blocks": _canonical_meter_reps(
        "marathon_mp_blocks", "M", recovery_label="easy jog between blocks"
    ),
    # -- Runna-inspired build/peak sessions --
    "half_on_off_ks": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_on_off_k_reps(d),
        rep_m=1000,
        work_zone="T",
        recovery_label="~1 km easy float between",
    ),
    "rolling_400s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_rolling_400_reps(d),
        rep_m=400,
        work_zone="10K",
        recovery_label="steady float between surges",
    ),
    "tempo_2_1_1": lambda d, pz: _steps_mod.build_distance_ladder_steps(
        d, pz, pattern_m=(2000, 1000, 1000), work_zone="T", float_m=500
    ),
    "intervals_400s_into_200s": lambda d, pz: _steps_mod.build_compound_rep_steps(
        d,
        pz,
        blocks=[
            (_compound_400_200_reps(d)[0], 400, "I", "hard"),
            (_compound_400_200_reps(d)[1], 200, "R", "fast and relaxed"),
        ],
    ),
    "intervals_800s_into_400s": lambda d, pz: _steps_mod.build_compound_rep_steps(
        d,
        pz,
        blocks=[
            (_compound_800_400_reps(d)[0], 800, "I", "hard"),
            (_compound_800_400_reps(d)[1], 400, "I", "quicker — shift gears"),
        ],
    ),
    "time_trial_5k": lambda d, pz: _steps_mod.build_time_trial_steps(d, pz, tt_m=5000),
    "race_practice_long": lambda d, pz: _steps_mod.build_split_long_steps(
        d, pz, easy_mult=0.60, finish_mult=0.40
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
    "trail_flat_over_under_intervals": lambda d, pz: _steps_mod.build_over_under_steps(
        d,
        pz,
        reps=_fartlek_reps(
            d, on_min=3, off_min=2, pace_min_per_km=6.0, default=6, lo=4, hi=8
        ),
        over_s=180,
        under_s=120,
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
    # -- taper sharpeners: easy bulk + race-effort touches (+ strides) --
    "taper_5k10k_sharpener": lambda d, pz: _steps_mod.build_sharpener_steps(
        d, pz, touches=4, touch_s=60, touch_zone="10K", strides=4
    ),
    "taper_half_sharpener": lambda d, pz: _steps_mod.build_sharpener_steps(
        d,
        pz,
        touches=2,
        touch_s=300,
        touch_zone="T",
        touch_effort="half-marathon effort",
    ),
    "taper_marathon_sharpener": lambda d, pz: _steps_mod.build_sharpener_steps(
        d,
        pz,
        touches=2,
        touch_s=360,
        touch_zone="M",
        touch_effort="marathon effort",
        strides=4,
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
    # -----------------------------------------------------------------------
    # Workouts that previously fell through to the easy-run defensive default.
    # Each builder matches the workout's declared type (interval/tempo/hill)
    # so the step effort, pace zone, and run label are internally consistent
    # with what the detail page shows as the session header.
    # -----------------------------------------------------------------------
    # -- 10K road interval variants --
    "10k_rolling_500s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=8,
        rep_m=500,
        work_zone="10K",
        recovery_label="200m easy jog",
    ),
    "10k_broken_miles": _canonical_meter_reps(
        "10k_broken_miles", "I", recovery_label="easy jog between miles"
    ),
    "10k_200m_repeats": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_vo2max_400_reps(d),
        rep_m=200,
        work_zone="R",
        recovery_label="200m jog recovery",
    ),
    "10k_pyramid_intervals": lambda d, pz: _steps_mod.build_pyramid_steps(
        d,
        pz,
        pattern=_road_pyramid_pattern_m(d),
        pace_zone="I",
        recovery_frac=0.5,
    ),
    # -- 10K road tempo variant --
    "10k_mile_up_overs": lambda d, pz: _steps_mod.build_over_under_steps(
        d,
        pz,
        reps=_over_under_reps(d, over_min=2.0, under_min=2.0, default=4, lo=3, hi=5),
        over_s=120,
        under_s=120,
    ),
    # -- Trail hilly interval / hill variants --
    "trail_technical_terrain": lambda d, pz: _steps_mod.build_continuous_quality_steps(
        d,
        pz,
        zone="T",
        effort="moderate, deliberate foot placement",
    ),
    "trail_broken_climbs": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=_fartlek_reps(
            d, on_min=1.5, off_min=1.0, pace_min_per_km=6.5, default=6, lo=4, hi=8
        ),
        work_s=90,
        work_zone="I",
        cue="hill",
        work_effort="hard uphill",
        recovery_s=60,
        recovery_label="60s easy jog",
        recovery_zone="E",
    ),
    "trail_rolling_500s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=8,
        rep_m=500,
        work_zone="T",
        recovery_label="200m easy jog",
    ),
    "trail_downhill_broken_miles": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=_vo2max_km_reps(d, rep_km=0.5, recovery_km=0.3, default=4, lo=3, hi=5),
        rep_m=500,
        work_zone="I",
        recovery_label="hike back up to reset",
    ),
    "trail_hill_pyramid": lambda d, pz: _steps_mod.build_duration_pyramid_steps(
        d,
        pz,
        pattern_s=[m * 60 for m in _duration_pyramid_min(d, _HILL_PYRAMID_PATTERNS)],
        work_zone="I",
        work_effort="hard uphill",
        cue="hill",
        recovery_label="jog down recovery",
    ),
    "trail_base_hike_run": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=_fartlek_reps(d, on_min=4, off_min=4, default=6, lo=4, hi=8),
        work_s=240,
        work_zone="E",
        work_kind="walk",
        label="power-hike uphills",
        work_effort="power hike",
        recovery_s=240,
        recovery_kind="run",
        recovery_effort="easy run",
        recovery_label="run flats and descents",
        recovery_zone="E",
    ),
    # -- Trail interval / base surge variants --
    "trail_base_surges": lambda d, pz: _steps_mod.build_strides_steps(
        d,
        pz,
        reps=6,
        stride_s=30,
        recovery_s=90,
        work_zone="I",
        label="6 × 30s uphill surges",
        effort="uphill surge",
        cue="hill",
    ),
    # -- Trail flat interval variants --
    "trail_flat_rolling_500s": lambda d, pz: _steps_mod.build_meter_rep_steps(
        d,
        pz,
        reps=8,
        rep_m=500,
        work_zone="T",
        recovery_label="200m easy jog",
    ),
    "trail_flat_broken_miles": _canonical_meter_reps(
        "trail_flat_broken_miles", "I", recovery_label="easy jog between miles"
    ),
    "trail_flat_pyramid": lambda d, pz: _steps_mod.build_duration_pyramid_steps(
        d,
        pz,
        pattern_s=[m * 60 for m in _duration_pyramid_min(d, _FLAT_PYRAMID_PATTERNS)],
        work_zone="I",
        work_effort="trail race effort",
        recovery_label="equal-duration easy jog",
    ),
    "trail_flat_vo2max_intervals": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=_fartlek_reps(d, on_min=3, off_min=2, default=5, lo=4, hi=7),
        work_s=180,
        work_zone="I",
        cue="hard",
        work_effort="hard",
        recovery_s=120,
        recovery_label="2min easy jog",
        recovery_zone="E",
    ),
    "trail_flat_proprioception": lambda d, pz: (
        _steps_mod.build_continuous_quality_steps(
            d,
            pz,
            zone="T",
            effort="moderate, varied-surface foot placement",
        )
    ),
    # -- Trail flat tempo variants --
    "trail_flat_base_strides": lambda d, pz: _steps_mod.build_strides_steps(
        d,
        pz,
        reps=6,
        stride_s=20,
        recovery_s=60,
        work_zone="R",
        label="6 × 20s fast strides on grass/dirt",
        effort="relaxed-fast",
        cue="stride",
    ),
    "trail_flat_base_fartlek": lambda d, pz: _steps_mod.build_fartlek_steps(
        d,
        pz,
        reps=6,
        on_s=120,
        off_s=180,
        on_zone="T",
        work_effort="comfortably hard",
    ),
    "trail_flat_threshold_blocks": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=_over_under_reps(d, over_min=8, under_min=3, default=3, lo=2, hi=4),
        work_s=480,
        work_zone="T",
        cue="hard",
        work_effort="threshold",
        recovery_s=180,
        recovery_label="3min easy jog",
        recovery_zone="E",
    ),
    "trail_flat_progressive_tempo": lambda d, pz: (
        _steps_mod.build_progression_block_steps(
            d,
            pz,
            block_zone="T",
        )
    ),
    "trail_flat_over_unders": lambda d, pz: _steps_mod.build_over_under_steps(
        d,
        pz,
        reps=_over_under_reps(d, over_min=2, under_min=3, default=5, lo=4, hi=7),
        over_s=120,
        under_s=180,
    ),
    "trail_flat_steady_state": lambda d, pz: _steps_mod.build_continuous_quality_steps(
        d,
        pz,
        zone="T",
    ),
    # -- Trail tempo variants --
    "trail_stacked_efforts": lambda d, pz: _steps_mod.build_duration_rep_steps(
        d,
        pz,
        reps=_over_under_reps(d, over_min=10, under_min=3, default=3, lo=2, hi=4),
        work_s=600,
        work_zone="T",
        cue="hard",
        work_effort="trail race effort",
        recovery_s=180,
        recovery_label="3min easy jog",
        recovery_zone="E",
    ),
    "trail_climb_surge_fartlek": lambda d, pz: _steps_mod.build_fartlek_steps(
        d,
        pz,
        reps=_fartlek_reps(d, on_min=2, off_min=2, default=8, lo=5, hi=12),
        on_s=120,
        off_s=120,
        on_zone="I",
        work_effort="surge uphill",
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
    → per-workout builder in ``_KEY_WORKOUT_STEP_BUILDERS`` → single continuous
    easy block for fractional/prose runs (``_RUNNING_DISTANCE_FRACTION``) →
    defensive easy-run default. Explicit builders are checked before the
    running-fraction fallback so workouts with a registered builder always
    produce type-consistent steps rather than a generic easy run.
    Used by both ``overlay_key_workout`` (initial generation) and
    ``rebuild_key_workout`` (adaptation / repair) so steps are always derived
    the same way.
    """
    if key_wk.get("steps"):
        return _inject_pace_into_steps(key_wk["steps"], pace_zones)
    # Scope the warm-up/cool-down profile to the session's type so the step
    # builders (and the rep-count helpers they call) size bookends with the
    # same hard/tempo profile the prose rewrites use.
    with _steps_mod.wucd_profile(key_wk.get("type") or workout_type):
        if key_wk.get("steps_builder"):
            return _resolve_long_steps_builder(
                key_wk["steps_builder"], distance_km, pace_zones
            )
        # Explicit per-workout builder takes priority over the running-fraction
        # easy-run path so interval/tempo/hill workouts always get
        # type-consistent steps rather than a generic easy run.
        builder = _KEY_WORKOUT_STEP_BUILDERS.get(key_wk["id"])
        if builder is not None and distance_km > 0:
            return builder(distance_km, pace_zones)
        if key_wk["id"] in _RUNNING_DISTANCE_FRACTION and distance_km > 0:
            return _steps_mod.build_easy_steps(distance_km, pace_zones)
        # Every key workout is covered by an explicit builder, a steps_builder,
        # or the running-fraction path above. This defensive default only
        # guards a future workout id added without a builder — it degrades to
        # an easy run rather than crashing.
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
