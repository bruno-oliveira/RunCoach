"""Workout builders for fitness plans — VO2max, tempo, cruise intervals, ladders, fartlek, time trials, long, easy."""

from typing import Dict, Optional

from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_pace as _shared_format_pace


def estimate_duration_min(segments: list) -> int:
    """Estimate total workout duration from segments."""
    total = 0
    for seg in segments:
        total += seg["distance_km"] * seg.get("pace_raw", 6.0)
    return round(total)


def _warmup_segment(warmup_km: float, pace: float) -> dict:
    return {
        "name": "Warm-up",
        "distance_km": warmup_km,
        "pace_formatted": _shared_format_pace(pace),
        "pace_raw": pace,
        "zone": "zone_1",
        "zone_label": "Zone 1",
        "type": "warmup",
    }


def _cooldown_segment(cooldown_km: float, pace: float) -> dict:
    return {
        "name": "Cool-down",
        "distance_km": cooldown_km,
        "pace_formatted": _shared_format_pace(pace),
        "pace_raw": pace,
        "zone": "zone_1",
        "zone_label": "Zone 1",
        "type": "cooldown",
    }


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
    target_pace = zones["zone_3_tempo"]["pace"]

    if phase == "base":
        tempo_km = min(5, weekly_km * 0.18)
    elif phase == "build":
        tempo_km = min(8, weekly_km * 0.22)
    elif phase == "peak":
        tempo_km = min(10, weekly_km * 0.25)
    else:
        tempo_km = min(4, weekly_km * 0.12)

    warmup_km = 2
    cooldown_km = 2
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Tempo",
            "distance_km": round(tempo_km, 1),
            "pace_formatted": _shared_format_pace(target_pace),
            "pace_raw": target_pace,
            "zone": "zone_3",
            "zone_label": "Zone 3",
            "type": "main",
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "tempo",
        "intensity": "medium",
        "zone": "zone_3",
        "target_pace": target_pace,
        "target_pace_formatted": _shared_format_pace(target_pace),
        "description": f"{total_km:.0f}km tempo: {warmup_km}km warmup, {round(tempo_km, 1):.1f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_fartlek_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a fartlek (speed play) workout."""
    tempo_pace = zones["zone_3_tempo"]["pace"]
    hard_pace = zones["zone_4_vo2max"]["pace"]

    pct_map = {"base": 0.18, "build": 0.22, "peak": 0.25, "taper": 0.12}
    total_km = round(weekly_km * pct_map.get(phase, 0.20), 1)
    total_km = max(5, min(12, total_km))

    surges = max(4, min(8, round((total_km - 4) * 1.2)))
    warmup_km = 2
    cooldown_km = 2
    main_km = max(1, total_km - warmup_km - cooldown_km)
    warmup_pace = zones["zone_1_recovery"]["pace"]
    fartlek_avg_pace = (tempo_pace + hard_pace) / 2

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Fartlek",
            "distance_km": round(main_km, 1),
            "pace_formatted": f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
            "pace_raw": fartlek_avg_pace,
            "zone": "mixed",
            "zone_label": "Mixed Zones",
            "type": "main",
            "intervals": {
                "reps": surges,
                "interval_m": "1-3min surges",
                "recovery_min": None,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    total_km = round(sum(s["distance_km"] for s in segments), 1)

    return {
        "type": "fartlek",
        "intensity": "medium",
        "zone": "mixed",
        "target_pace": tempo_pace,
        "target_pace_formatted": f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
        "description": f"{total_km}km fartlek: {surges} surges of 1-3min at {_shared_format_pace(hard_pace)}, easy running between",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


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


def generate_easy_run(zones: Dict, distance_km: float) -> Dict:
    """Generate an easy recovery run."""
    easy_pace = zones["zone_1_recovery"]["pace"]
    rounded_km = round(distance_km, 1)

    segments = [
        {
            "name": "Easy Run",
            "distance_km": rounded_km,
            "pace_formatted": _shared_format_pace(easy_pace),
            "pace_raw": easy_pace,
            "zone": "zone_1",
            "zone_label": "Zone 1",
            "type": "main",
        },
    ]

    return {
        "type": "easy",
        "intensity": "low",
        "zone": "zone_1",
        "target_pace": easy_pace,
        "target_pace_formatted": _shared_format_pace(easy_pace),
        "description": f"{rounded_km:.1f}km easy at {_shared_format_pace(easy_pace)}",
        "distance": rounded_km,
        "quality": False,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def generate_long_run(zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
    """Generate a long aerobic run (capped at 25% of weekly mileage, max ~18km)."""
    easy_pace = zones["zone_1_recovery"]["pace"]
    long_run_km = round(distance_km, 1)

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

    return {
        "type": "long",
        "intensity": "medium",
        "zone": "zone_1",
        "target_pace": easy_pace,
        "target_pace_formatted": _shared_format_pace(easy_pace),
        "description": f"{long_run_km:.0f}km long run at {_shared_format_pace(easy_pace)}",
        "distance": long_run_km,
        "quality": False,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }
