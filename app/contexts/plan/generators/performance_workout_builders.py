"""Workout builders for performance plans — tempo, VO2max, race pace, fartlek, long, easy."""

from typing import Any, Dict

from app.contexts.plan.generators.workout_builder_base import (
    _cooldown_segment,
    _warmup_segment,
    build_fartlek_workout,
    build_tempo_workout,
    estimate_duration_min,
    generate_easy_run,
)
from app.core.training.road_profile import classify_road
from app.utils import format_pace as _shared_format_pace

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


def reconcile_workout_after_cap(workout: Dict[str, Any]) -> None:
    """Sync segments and description after enforce_week_caps reduced distance."""
    segments = workout.get("segments")
    if not segments:
        return

    seg_total = round(sum(s["distance_km"] for s in segments), 1)
    target = workout["distance"]

    if abs(seg_total - target) < 0.15:
        return

    main_segs = [s for s in segments if s["type"] == "main"]
    non_main_km = sum(s["distance_km"] for s in segments if s["type"] != "main")

    if not main_segs:
        return

    remaining = max(0.5, target - non_main_km)

    if len(main_segs) == 1:
        main_segs[0]["distance_km"] = round(remaining, 1)
        intervals = main_segs[0].get("intervals")
        if intervals and isinstance(intervals.get("interval_m"), int):
            interval_km = intervals["interval_m"] / 1000
            new_reps = max(2, round(remaining / interval_km))
            intervals["reps"] = new_reps
            main_segs[0]["distance_km"] = round(interval_km * new_reps, 1)
            workout["distance"] = round(non_main_km + main_segs[0]["distance_km"], 1)
    else:
        orig_total = sum(s["distance_km"] for s in main_segs) or 1
        for seg in main_segs:
            seg["distance_km"] = round(seg["distance_km"] / orig_total * remaining, 1)

    workout["total_duration_est_min"] = estimate_duration_min(segments)
    _regenerate_description(workout)


def _regenerate_description(workout: Dict[str, Any]) -> None:
    """Rebuild the description string from current segment values."""
    if workout.get("key_workout_id"):
        return
    segments = workout.get("segments", [])
    total_km = workout["distance"]
    wtype = workout["type"]

    warmups = [s for s in segments if s["type"] == "warmup"]
    mains = [s for s in segments if s["type"] == "main"]
    cooldowns = [s for s in segments if s["type"] == "cooldown"]
    wu_km = warmups[0]["distance_km"] if warmups else 0
    cd_km = cooldowns[0]["distance_km"] if cooldowns else 0

    if not mains:
        return

    main = mains[0]

    if wtype == "tempo":
        workout["description"] = (
            f"{total_km:.0f}km tempo: {wu_km:.0f}km warmup, "
            f"{main['distance_km']:.1f}km at {main['pace_formatted']}, "
            f"{cd_km:.0f}km cooldown"
        )
    elif wtype == "vo2max":
        ivl = main.get("intervals", {})
        if ivl and isinstance(ivl.get("interval_m"), int):
            rec = (
                f" ({ivl['recovery_min']}min recovery)"
                if ivl.get("recovery_min")
                else ""
            )
            workout["description"] = (
                f"{total_km:.0f}km intervals: {wu_km:.0f}km warmup, "
                f"{ivl['reps']}x{ivl['interval_m']}m at {main['pace_formatted']}{rec}, "
                f"{cd_km:.0f}km cooldown"
            )
        else:
            workout["description"] = (
                f"{total_km:.0f}km intervals: {wu_km:.0f}km warmup, "
                f"{main['distance_km']:.1f}km at {main['pace_formatted']}, "
                f"{cd_km:.0f}km cooldown"
            )
    elif wtype == "race_pace":
        workout["description"] = (
            f"{total_km:.0f}km race pace: {wu_km:.0f}km warmup, "
            f"{main['distance_km']:.1f}km at {main['pace_formatted']}, "
            f"{cd_km:.0f}km cooldown"
        )
    elif wtype == "fartlek":
        ivl = main.get("intervals", {})
        pace_parts = main["pace_formatted"].split(" - ")
        hard_pace = pace_parts[-1] if len(pace_parts) > 1 else main["pace_formatted"]
        reps = ivl.get("reps", 0) if ivl else 0
        workout["description"] = (
            f"{total_km}km fartlek: {reps} surges of 1-3min at {hard_pace}, "
            f"easy running between"
        )
    elif wtype in ("interval", "hill"):
        ivl = main.get("intervals", {})
        if ivl and isinstance(ivl.get("interval_m"), int):
            rec = (
                f" ({ivl['recovery_min']}min recovery)"
                if ivl.get("recovery_min")
                else ""
            )
            workout["description"] = (
                f"{total_km:.0f}km {wtype}: {wu_km:.0f}km warmup, "
                f"{ivl['reps']}x{ivl['interval_m']}m at {main['pace_formatted']}{rec}, "
                f"{cd_km:.0f}km cooldown"
            )
        else:
            workout["description"] = (
                f"{total_km:.0f}km {wtype}: {wu_km:.0f}km warmup, "
                f"{main['distance_km']:.1f}km at {main['pace_formatted']}, "
                f"{cd_km:.0f}km cooldown"
            )


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
    warmup_km = 2
    cooldown_km = 2
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
        "description": f"{total_km:.0f}km intervals: {warmup_km}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_time}min recovery), {cooldown_km}km cooldown",
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

    warmup_km = 2
    cooldown_km = 2
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Race Pace",
            "distance_km": round(race_km, 1),
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
        "description": f"{total_km:.0f}km race pace: {warmup_km}km warmup, {round(race_km, 1):.1f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
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

    if phase in ["build", "peak"] and long_run_km >= 12:
        race_pace_km = min(4, distance_km * 0.3)
        easy_km = long_run_km - race_pace_km
        segments = [
            {
                "name": "Easy",
                "distance_km": round(easy_km, 1),
                "pace_formatted": _shared_format_pace(easy_pace),
                "pace_raw": easy_pace,
                "zone": "zone_1",
                "zone_label": "Zone 1",
                "type": "main",
            },
            {
                "name": "Race Pace Finish",
                "distance_km": round(race_pace_km, 1),
                "pace_formatted": _shared_format_pace(race_pace),
                "pace_raw": race_pace,
                "zone": "zone_5",
                "zone_label": "Zone 5",
                "type": "main",
            },
        ]
        long_run_km = round(sum(s["distance_km"] for s in segments), 1)
        description = f"{long_run_km:.0f}km long run: {segments[0]['distance_km']:.1f}km easy at {_shared_format_pace(easy_pace)}, last {segments[1]['distance_km']:.1f}km at {_shared_format_pace(race_pace)}"
    else:
        description = (
            f"{long_run_km:.0f}km long run at {_shared_format_pace(easy_pace)}"
        )
        segments = [
            {
                "name": "Easy Long Run",
                "distance_km": round(long_run_km, 1),
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
