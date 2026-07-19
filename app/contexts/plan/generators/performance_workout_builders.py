"""Workout builders for performance plans — tempo, VO2max, race pace, fartlek, long, easy."""

from typing import Dict

from app.contexts.plan.generators.workout_builder_base import (
    _cooldown_segment,
    _regenerate_description,
    _warmup_segment,
    build_fartlek_workout,
    build_tempo_workout,
    estimate_duration_min,
    generate_easy_run,
    reconcile_workout_after_cap,
)
from app.core.training.road_profile import classify_road
from app.core.training.workout_steps import _wucd_m_for_work
from app.utils import format_km
from app.utils import format_pace as _shared_format_pace

# ``reconcile_workout_after_cap`` / ``_regenerate_description`` now live in
# workout_builder_base so the fitness generator can share them; re-exported
# here for back-compat (tests and the performance generator import them from
# this module).
__all_reexport__ = (reconcile_workout_after_cap, _regenerate_description)

# Long-run distance cap (km) per road band.
_LONG_RUN_CAP_KM = {"5k": 15, "10k": 15, "half": 22, "marathon": 32}

# Performance-plan tempo/fartlek tuning (segment shape lives in workout_builder_base).
_TEMPO_PHASE_CAPS = {"base": (6, 0.20), "build": (10, 0.25), "peak": (12, 0.30)}
_TEMPO_DEFAULT_CAP_PCT = (5, 0.15)
_FARTLEK_PCT_MAP = {"base": 0.20, "build": 0.25, "peak": 0.28, "taper": 0.15}

__all__ = [
    "estimate_duration_min",
    "generate_easy_run",
    "reconcile_workout_after_cap",
    "generate_tempo_workout",
    "generate_vo2max_workout",
    "generate_race_pace_workout",
    "generate_fartlek_workout",
    "generate_long_run",
]


def generate_tempo_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a tempo workout scaled to weekly volume."""
    return build_tempo_workout(
        zones,
        weekly_km,
        phase,
        phase_caps=_TEMPO_PHASE_CAPS,
        default_cap_pct=_TEMPO_DEFAULT_CAP_PCT,
    )


def generate_vo2max_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a VO2 max interval workout scaled to weekly volume."""
    target_pace = zones["zone_4_vo2max"]["pace"]

    pct_map = {"base": 0.15, "build": 0.20, "peak": 0.18, "taper": 0.12}
    target_interval_km = weekly_km * pct_map.get(phase, 0.15)

    if target_interval_km <= 3:
        interval_m = 400
    elif target_interval_km <= 5:
        interval_m = 600
    elif target_interval_km <= 8:
        interval_m = 800
    else:
        interval_m = 1000

    interval_km = interval_m / 1000
    reps = max(3, min(8, round(target_interval_km / interval_km)))

    recovery_time = int(interval_km * 2)
    total_interval_km = interval_km * reps
    # Shared warm-up/cool-down policy, hard profile: interval work earns the
    # longer bookends (sized from the work block — see _wucd_m_for_work).
    warmup_km = _wucd_m_for_work(int(round(total_interval_km * 1000)), hard=True) / 1000
    cooldown_km = warmup_km
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Intervals",
            "distance_km": round(total_interval_km, 1),
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_4",
            "zone_label": "Zone 4",
            "type": "main",
            "intervals": {
                "reps": reps,
                "interval_m": interval_m,
                "recovery_min": recovery_time,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "vo2max",
        "intensity": "high",
        "zone": "zone_4",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{format_km(total_km)}km intervals: {format_km(warmup_km)}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_time}min recovery), {format_km(cooldown_km)}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_race_pace_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a race pace workout scaled to weekly volume."""
    target_pace = zones["zone_5_race"]["pace"]

    if phase == "base":
        race_km = min(4, weekly_km * 0.15)
    elif phase == "build":
        race_km = min(8, weekly_km * 0.20)
    elif phase == "peak":
        race_km = min(12, weekly_km * 0.25)
    else:
        race_km = min(3, weekly_km * 0.10)
    # Round once so the segment, the description, and the total all use the
    # identical one-decimal value (format_km truncates; round() does not).
    race_km = round(race_km, 1)

    warmup_km = _wucd_m_for_work(int(round(race_km * 1000)), hard=True) / 1000
    cooldown_km = warmup_km
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Race Pace",
            "distance_km": race_km,
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_5",
            "zone_label": "Zone 5",
            "type": "main",
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "race_pace",
        "intensity": "high",
        "zone": "zone_5",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{format_km(total_km)}km race pace: {format_km(warmup_km)}km warmup, {format_km(race_km)}km at {_shared_format_pace(target_pace)}, {format_km(cooldown_km)}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_fartlek_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a fartlek (speed play) workout scaled to weekly volume."""
    return build_fartlek_workout(
        zones,
        weekly_km,
        phase,
        pct_map=_FARTLEK_PCT_MAP,
        total_max_km=14,
        surge_multiplier=1.5,
        surge_max=10,
    )


def generate_long_run(
    zones: Dict, weekly_km: float, week: int, phase: str, distance_km: float
) -> Dict:
    """Generate a long run with optional race pace finish."""
    easy_pace = zones["zone_1_recovery"]["pace"]
    race_pace = zones["zone_5_race"]["pace"]

    long_run_km = weekly_km * 0.30
    long_run_km = min(long_run_km, _LONG_RUN_CAP_KM[classify_road(distance_km)])
    # Round once, up front: the segment distance, the description header, and
    # the stored ``distance`` must all derive from the SAME one-decimal value.
    # Formatting the raw float separately let format_km (which truncates) and
    # round() disagree by 0.1 (e.g. 7.65 -> header "7.5km" but distance 7.6).
    long_run_km = round(long_run_km, 1)

    if phase in ["build", "peak"] and long_run_km >= 12:
        race_pace_km = round(min(4, distance_km * 0.3), 1)
        easy_km = round(long_run_km - race_pace_km, 1)
        segments = [
            {
                "name": "Easy",
                "distance_km": easy_km,
                "pace_formatted": _shared_format_pace(easy_pace),
                "pace_raw": easy_pace,
                "zone": "zone_1",
                "zone_label": "Zone 1",
                "type": "main",
            },
            {
                "name": "Race Pace Finish",
                "distance_km": race_pace_km,
                "pace_formatted": _shared_format_pace(race_pace),
                "pace_raw": race_pace,
                "zone": "zone_5",
                "zone_label": "Zone 5",
                "type": "main",
            },
        ]
        long_run_km = round(sum(s["distance_km"] for s in segments), 1)
        description = f"{format_km(long_run_km)}km long run: {format_km(segments[0]['distance_km'])}km easy at {_shared_format_pace(easy_pace)}, last {format_km(segments[1]['distance_km'])}km at {_shared_format_pace(race_pace)}"
    else:
        description = (
            f"{format_km(long_run_km)}km long run at {_shared_format_pace(easy_pace)}"
        )
        segments = [
            {
                "name": "Easy Long Run",
                "distance_km": long_run_km,
                "pace_formatted": _shared_format_pace(easy_pace),
                "pace_raw": easy_pace,
                "zone": "zone_1",
                "zone_label": "Zone 1",
                "type": "main",
            },
        ]

    return {
        "type": "long",
        "intensity": "medium",
        "zone": "zone_1",
        "target_pace": easy_pace,
        "target_pace_formatted": _shared_format_pace(easy_pace),
        "description": description,
        "distance": round(long_run_km, 1),
        "quality": False,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }
