"""Workout builders for performance plans — tempo, VO2max, race pace, fartlek, long, easy."""

from typing import Any, Dict

from app.utils import format_pace as _shared_format_pace


def estimate_duration_min(segments: list) -> int:
    """Estimate total workout duration from segments."""
    total = 0
    for seg in segments:
        total += seg["distance_km"] * seg.get("pace_raw", 6.0)
    return round(total)


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


def generate_tempo_workout(
    zones: Dict, weekly_km: float, week: int, phase: str
) -> Dict:
    """Generate a tempo workout scaled to weekly volume."""
    target_pace = zones["zone_3_tempo"]["pace"]

    if phase == "base":
        tempo_km = min(6, weekly_km * 0.20)
    elif phase == "build":
        tempo_km = min(10, weekly_km * 0.25)
    elif phase == "peak":
        tempo_km = min(12, weekly_km * 0.30)
    else:
        tempo_km = min(5, weekly_km * 0.15)

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
    tempo_pace = zones["zone_3_tempo"]["pace"]
    hard_pace = zones["zone_4_vo2max"]["pace"]

    pct_map = {"base": 0.20, "build": 0.25, "peak": 0.28, "taper": 0.15}
    total_km = round(weekly_km * pct_map.get(phase, 0.20), 1)
    total_km = max(5, min(14, total_km))

    surges_per_km = 1.5
    surges = max(4, min(10, round((total_km - 4) * surges_per_km)))

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


def generate_long_run(
    zones: Dict, weekly_km: float, week: int, phase: str, distance_km: float
) -> Dict:
    """Generate a long run with optional race pace finish."""
    easy_pace = zones["zone_1_recovery"]["pace"]
    race_pace = zones["zone_5_race"]["pace"]

    long_run_km = weekly_km * 0.30

    if distance_km <= 10:
        long_run_km = min(long_run_km, 15)
    elif distance_km <= 21.1:
        long_run_km = min(long_run_km, 22)
    else:
        long_run_km = min(long_run_km, 32)

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
