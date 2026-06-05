"""Workout builders for fitness plans — VO2max, tempo, cruise intervals, ladders, fartlek, time trials, long, easy."""

from typing import Dict, Optional

from app.contexts.plan.generators.workout_builder_base import (
    _cooldown_segment,
    _warmup_segment,
    build_fartlek_workout,
    build_tempo_workout,
    estimate_duration_min,
    generate_easy_run,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_pace as _shared_format_pace

# Fitness-plan tempo/fartlek tuning (segment shape lives in workout_builder_base).
_TEMPO_PHASE_CAPS = {"base": (5, 0.18), "build": (8, 0.22), "peak": (10, 0.25)}
_TEMPO_DEFAULT_CAP_PCT = (4, 0.12)
_FARTLEK_PCT_MAP = {"base": 0.18, "build": 0.22, "peak": 0.25, "taper": 0.12}

__all__ = [
    "estimate_duration_min",
    "generate_easy_run",
    "generate_vo2max_workout",
    "generate_vo2max_ladder",
    "generate_cruise_interval_workout",
    "generate_tempo_workout",
    "generate_fartlek_workout",
    "generate_race_pace_workout",
    "generate_time_trial_workout",
    "generate_long_run",
]


def _race_pace_min_km(
    zones: Dict, focus_distance: Optional[float], vdot: Optional[float]
) -> float:
    """Goal race pace (min/km) for the fitness focus distance.

    Derived from VDOT for the chosen race distance so a 5K focus and a Half
    focus prescribe genuinely different paces (audit G9). Falls back to the
    threshold band when VDOT is unavailable.
    """
    if vdot and focus_distance and focus_distance > 0:
        secs = VDOTCalculator.predict_time_for_distance(vdot, focus_distance)
        if secs:
            return secs / focus_distance / 60.0
    return zones["zone_3_tempo"]["pace"]


def generate_vo2max_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate VO2max intervals (800m/1km repeats)."""
    target_pace = zones["zone_4_vo2max"]["pace"]

    pct_map = {"base": 0.12, "build": 0.18, "peak": 0.20, "taper": 0.10}
    target_interval_km = weekly_km * pct_map.get(phase, 0.15)

    if target_interval_km <= 3:
        interval_m, recovery_min = 800, 2
    elif target_interval_km <= 5:
        interval_m, recovery_min = 800, 2
    elif target_interval_km <= 8:
        interval_m, recovery_min = 1000, 3
    else:
        interval_m, recovery_min = 1000, 3

    interval_km = interval_m / 1000
    reps = max(3, min(8, round(target_interval_km / interval_km)))

    total_interval_km = interval_km * reps
    warmup_km = 2
    cooldown_km = 2
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "VO2max Intervals",
            "distance_km": round(total_interval_km, 1),
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_4",
            "zone_label": "Zone 4",
            "type": "main",
            "intervals": {
                "reps": reps,
                "interval_m": interval_m,
                "recovery_min": recovery_min,
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
        "description": f"{total_km:.0f}km VO2max: {warmup_km}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_min}min jog recovery), {cooldown_km}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_vo2max_ladder(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate VO2max ladder (e.g., 400-600-800-1000-800-600-400)."""
    target_pace = zones["zone_4_vo2max"]["pace"]
    warmup_pace = zones["zone_1_recovery"]["pace"]

    if phase == "base":
        ladder_rungs = [600, 800, 1000, 800, 600]
    elif phase == "build":
        ladder_rungs = [400, 600, 800, 1000, 1200, 1000, 800]
    else:
        ladder_rungs = [400, 600, 800, 1000, 1200, 1000, 800, 600, 400]

    recovery_min = 2
    total_interval_km = sum(r / 1000 for r in ladder_rungs)
    warmup_km = 2
    cooldown_km = 2

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "VO2max Ladder",
            "distance_km": round(total_interval_km, 1),
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_4",
            "zone_label": "Zone 4",
            "type": "main",
            "intervals": {
                "reps": len(ladder_rungs),
                "ladder_m": ladder_rungs,
                "recovery_min": recovery_min,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)
    ladder_str = "-".join(f"{r}m" for r in ladder_rungs)

    return {
        "type": "vo2max_ladder",
        "intensity": "high",
        "zone": "zone_4",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{total_km:.0f}km ladder: {warmup_km}km warmup, {ladder_str} at {_shared_format_pace(target_pace)} ({recovery_min}min between), {cooldown_km}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_cruise_interval_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate cruise intervals at threshold pace with short recovery."""
    target_pace = zones["zone_3_tempo"]["pace"]
    warmup_pace = zones["zone_1_recovery"]["pace"]

    pct_map = {"base": 0.15, "build": 0.22, "peak": 0.25, "taper": 0.12}
    target_interval_km = weekly_km * pct_map.get(phase, 0.20)

    interval_m = 1000
    interval_km = interval_m / 1000
    reps = max(3, min(7, round(target_interval_km / interval_km)))
    recovery_min = 1

    total_interval_km = interval_km * reps
    warmup_km = 2
    cooldown_km = 2

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Cruise Intervals",
            "distance_km": round(total_interval_km, 1),
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_3",
            "zone_label": "Zone 3",
            "type": "main",
            "intervals": {
                "reps": reps,
                "interval_m": interval_m,
                "recovery_min": recovery_min,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "cruise_interval",
        "intensity": "medium",
        "zone": "zone_3",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{total_km:.0f}km cruise: {warmup_km}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_min}min jog), {cooldown_km}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_tempo_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a tempo run at threshold pace."""
    return build_tempo_workout(
        zones,
        weekly_km,
        phase,
        phase_caps=_TEMPO_PHASE_CAPS,
        default_cap_pct=_TEMPO_DEFAULT_CAP_PCT,
    )


def generate_fartlek_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a fartlek (speed play) workout."""
    return build_fartlek_workout(
        zones,
        weekly_km,
        phase,
        pct_map=_FARTLEK_PCT_MAP,
        total_max_km=12,
        surge_multiplier=1.2,
        surge_max=8,
    )


def generate_time_trial_workout(
    zones: Dict, distance_km: float, week: int, vdot: Optional[float] = None
) -> Dict:
    """Generate a time trial benchmark workout.

    All-out effort over a set distance for VDOT tracking.
    """
    warmup_km = 2
    cooldown_km = 2
    warmup_pace = zones["zone_1_recovery"]["pace"]

    if vdot:
        vdot_zones = VDOTCalculator.get_pace_zones(vdot)
        target_pace = vdot_zones["I"]["pace_min_km"]
    else:
        target_pace = zones["zone_4_vo2max"]["pace"]

    rounded_km = round(distance_km, 1)

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Time Trial",
            "distance_km": rounded_km,
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_5",
            "zone_label": "Zone 5",
            "type": "main",
            "intervals": {
                "reps": 1,
                "distance_km": rounded_km,
                "effort": "all-out",
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "time_trial",
        "intensity": "high",
        "zone": "zone_5",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{total_km:.0f}km: {warmup_km}km warmup, {rounded_km}km TIME TRIAL (all-out), {cooldown_km}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
        "is_benchmark": True,
    }


def generate_race_pace_workout(
    zones: Dict,
    weekly_km: float,
    week: int,
    phase: str,
    focus_distance: Optional[float] = None,
    vdot: Optional[float] = None,
) -> Dict:
    """Race-specific session at goal pace for the focus distance (audit G9).

    Short races (≤12 km focus) get 1 km reps; longer races get continuous
    2 km blocks, mirroring how race specificity sharpens toward the goal.
    """
    warmup_pace = zones["zone_1_recovery"]["pace"]
    race_pace = _race_pace_min_km(zones, focus_distance, vdot)

    pct_map = {"base": 0.15, "build": 0.20, "peak": 0.25, "taper": 0.12}
    target_rp_km = max(2.0, weekly_km * pct_map.get(phase, 0.18))

    short_race = (focus_distance or 10.0) <= 12.0
    interval_m = 1000 if short_race else 2000
    recovery_min = 2
    interval_km = interval_m / 1000
    reps = max(2, min(6, round(target_rp_km / interval_km)))

    total_interval_km = round(interval_km * reps, 1)
    warmup_km = 2
    cooldown_km = 2

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Race-Pace Reps",
            "distance_km": total_interval_km,
            "pace_formatted": _shared_format_pace(race_pace),
            "pace_raw": race_pace,
            "zone": "zone_3",
            "zone_label": "Zone 3",
            "type": "main",
            "intervals": {
                "reps": reps,
                "interval_m": interval_m,
                "recovery_min": recovery_min,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)
    dist_label = (
        f"{focus_distance:g}km" if focus_distance and focus_distance > 0 else "race"
    )

    return {
        "type": "race_pace",
        "intensity": "high",
        "zone": "zone_3",
        "target_pace": race_pace,
        "target_pace_formatted": _shared_format_pace(race_pace),
        "description": (
            f"{total_km:.0f}km race-pace: {warmup_km}km warmup, "
            f"{reps}x{interval_m}m at {_shared_format_pace(race_pace)} "
            f"({dist_label} goal pace, {recovery_min}min jog), {cooldown_km}km cooldown"
        ),
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_long_run(
    zones: Dict,
    distance_km: float,
    week: int,
    phase: str,
    race_pace: Optional[float] = None,
) -> Dict:
    """Generate a long aerobic run (capped at 25% of weekly mileage, max ~18km).

    In peak weeks, when a goal ``race_pace`` is known, the final ~25% is run
    at race pace so the long run rehearses race specificity (audit G9).
    """
    easy_pace = zones["zone_1_recovery"]["pace"]
    long_run_km = round(distance_km, 1)

    if race_pace and phase == "peak" and long_run_km >= 8.0:
        finish_km = round(long_run_km * 0.25, 1)
        easy_km = round(long_run_km - finish_km, 1)
        segments = [
            {
                "name": "Long Run",
                "distance_km": easy_km,
                "pace_formatted": _shared_format_pace(easy_pace),
                "pace_raw": easy_pace,
                "zone": "zone_1",
                "zone_label": "Zone 1",
                "type": "main",
            },
            {
                "name": "Goal-Pace Finish",
                "distance_km": finish_km,
                "pace_formatted": _shared_format_pace(race_pace),
                "pace_raw": race_pace,
                "zone": "zone_3",
                "zone_label": "Zone 3",
                "type": "main",
            },
        ]
        description = (
            f"{long_run_km:.0f}km long run: {easy_km:.0f}km easy at "
            f"{_shared_format_pace(easy_pace)}, final {finish_km:.0f}km at "
            f"{_shared_format_pace(race_pace)} (goal race pace)"
        )
    else:
        segments = [
            {
                "name": "Long Run",
                "distance_km": long_run_km,
                "pace_formatted": _shared_format_pace(easy_pace),
                "pace_raw": easy_pace,
                "zone": "zone_1",
                "zone_label": "Zone 1",
                "type": "main",
            },
        ]
        description = (
            f"{long_run_km:.0f}km long run at {_shared_format_pace(easy_pace)}"
        )

    return {
        "type": "long",
        "intensity": "medium",
        "zone": "zone_1",
        "target_pace": easy_pace,
        "target_pace_formatted": _shared_format_pace(easy_pace),
        "description": description,
        "distance": long_run_km,
        "quality": False,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }
