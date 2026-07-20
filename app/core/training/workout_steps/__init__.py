"""Structured workout steps.

Turns a workout into a sequence of concrete, executable blocks. Each step
is a dict with:

    kind       : 'warmup' | 'run' | 'recovery' | 'cooldown' | 'strides' |
                 'walk' | 'rest'
    label      : short human-readable label ("Warm up", "5 × 400 m")
    distance_m : target distance per rep in meters (None if duration-based)
    duration_s : target duration per rep in seconds (None if distance-based)
    repeat     : how many times to perform this block (default 1)
    pace_zone  : 'E' | 'M' | 'T' | 'I' | 'R' | None
    pace_str   : injected pace string ("4:22/km"), or None
    effort     : short effort cue ("conversational", "hard", "jog", "walk")
    note       : optional tip

Watches, UI, PDF, and adaptation can all operate on this structure rather
than parsing prose descriptions. Builders here are pure functions — they
accept numbers and pace-zones, and return a list of step dicts.

This package splits the builders by concern:
    primitives — step factory + warm-up/cool-down helpers
    aerobic    — easy / long / long-run variants
    quality    — tempo / interval / hill + key-workout builders
    trail      — pyramid / ladder / hike-run / back-to-back
    metrics    — distance computation, pace parsing, scaling

The names below are re-exported so callers keep importing from
``app.core.training.workout_steps`` unchanged.
"""

from __future__ import annotations

from app.core.training.workout_steps.aerobic import (
    build_alternating_mp_long_steps,
    build_depletion_long_steps,
    build_easy_steps,
    build_fast_finish_long_steps,
    build_long_steps,
    build_rolling_hills_long_steps,
    build_split_long_steps,
)
from app.core.training.workout_steps.key_workout_builders import (
    build_compound_rep_steps,
    build_continuous_quality_steps,
    build_distance_ladder_steps,
    build_duration_pyramid_steps,
    build_duration_rep_steps,
    build_fartlek_steps,
    build_km_rep_steps,
    build_meter_rep_steps,
    build_over_under_steps,
    build_progression_block_steps,
    build_sharpener_steps,
    build_strides_steps,
    build_time_trial_steps,
)
from app.core.training.workout_steps.metrics import (
    _DEFAULT_PACES,
    _compute_distance_from_steps,
    _parse_pace_str_to_min_per_km,
    compute_distance_from_steps_checked,
    exempt_work_km,
    fit_steps_to_distance,
    fit_steps_to_intensity_caps,
    scale_steps,
    total_distance_m,
    work_km_by_group,
)
from app.core.training.workout_steps.primitives import (
    _COOLDOWN_M,
    _WARMUP_M,
    HARD_SESSION_TYPES,
    STEP_KINDS,
    _cooldown,
    _pace_str,
    _step,
    _warmup,
    _wucd_m,
    _wucd_m_for_work,
    wucd_profile,
)
from app.core.training.workout_steps.quality import (
    _build_interval_steps_high_base,
    _build_interval_steps_low_base,
    build_hill_steps,
    build_interval_steps,
    build_tempo_steps,
    cruise_recovery_m,
    interval_rep_plan,
    interval_session_plan,
    tempo_cruise_plan,
)
from app.core.training.workout_steps.trail import (
    _build_rung_steps,
    build_back_to_back_steps,
    build_hike_run_steps,
    build_ladder_steps,
    build_pyramid_steps,
)

__all__ = [
    "STEP_KINDS",
    "build_easy_steps",
    "build_long_steps",
    "build_alternating_mp_long_steps",
    "build_fast_finish_long_steps",
    "build_rolling_hills_long_steps",
    "build_depletion_long_steps",
    "build_split_long_steps",
    "build_tempo_steps",
    "cruise_recovery_m",
    "interval_rep_plan",
    "interval_session_plan",
    "tempo_cruise_plan",
    "build_interval_steps",
    "build_hill_steps",
    "build_meter_rep_steps",
    "build_km_rep_steps",
    "build_fartlek_steps",
    "build_sharpener_steps",
    "build_over_under_steps",
    "build_strides_steps",
    "build_progression_block_steps",
    "build_compound_rep_steps",
    "build_continuous_quality_steps",
    "build_distance_ladder_steps",
    "build_time_trial_steps",
    "build_duration_rep_steps",
    "build_duration_pyramid_steps",
    "build_pyramid_steps",
    "build_ladder_steps",
    "build_hike_run_steps",
    "build_back_to_back_steps",
    "scale_steps",
    "total_distance_m",
    "fit_steps_to_distance",
    "fit_steps_to_intensity_caps",
    "work_km_by_group",
    "exempt_work_km",
    "wucd_profile",
    "HARD_SESSION_TYPES",
    # Internal helpers re-exported for cross-module and test use.
    "_step",
    "_pace_str",
    "_warmup",
    "_cooldown",
    "_wucd_m",
    "_wucd_m_for_work",
    "_WARMUP_M",
    "_COOLDOWN_M",
    "_build_interval_steps_high_base",
    "_build_interval_steps_low_base",
    "_build_rung_steps",
    "_DEFAULT_PACES",
    "_compute_distance_from_steps",
    "compute_distance_from_steps_checked",
    "_parse_pace_str_to_min_per_km",
]
