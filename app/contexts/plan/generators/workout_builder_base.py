"""Shared workout-builder primitives for fitness and performance plans.

Both plan families assemble workouts from the same warm-up / main / cool-down
segment shapes and the same duration estimate. The fitness and performance
builder modules import these helpers and supply their own phase tuning for the
parameterized tempo / fartlek builders, so the segment-construction logic lives
in exactly one place.
"""

from typing import Dict, Mapping, Tuple

from app.utils import format_km
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
        "description": f"{format_km(rounded_km)}km easy at {_shared_format_pace(easy_pace)}",
        "distance": rounded_km,
        "quality": False,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def build_tempo_workout(
    zones: Dict,
    weekly_km: float,
    phase: str,
    *,
    phase_caps: Mapping[str, Tuple[float, float]],
    default_cap_pct: Tuple[float, float],
) -> Dict:
    """Tempo run at threshold pace, scaled to weekly volume.

    Args:
        phase_caps: Maps phase -> ``(cap_km, pct)``; tempo distance is
            ``min(cap_km, weekly_km * pct)``.
        default_cap_pct: ``(cap_km, pct)`` for taper / unknown phases.
    """
    target_pace = zones["zone_3_tempo"]["pace"]

    cap_km, pct = phase_caps.get(phase, default_cap_pct)
    tempo_km = round(min(cap_km, weekly_km * pct), 1)

    warmup_km = 2
    cooldown_km = 2
    warmup_pace = zones["zone_1_recovery"]["pace"]

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            "name": "Tempo",
            "distance_km": tempo_km,
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
        "description": f"{format_km(total_km)}km tempo: {format_km(warmup_km)}km warmup, {format_km(tempo_km)}km at {_shared_format_pace(target_pace)}, {format_km(cooldown_km)}km cooldown",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }


def build_fartlek_workout(
    zones: Dict,
    weekly_km: float,
    phase: str,
    *,
    pct_map: Mapping[str, float],
    total_max_km: float,
    surge_multiplier: float,
    surge_max: int,
    default_pct: float = 0.20,
    total_min_km: float = 5,
    surge_min: int = 4,
) -> Dict:
    """Fartlek (speed play) workout scaled to weekly volume.

    ``pct_map`` and ``surge_*`` differ between plan families; segment shape and
    description do not.
    """
    tempo_pace = zones["zone_3_tempo"]["pace"]
    hard_pace = zones["zone_4_vo2max"]["pace"]

    total_km = round(weekly_km * pct_map.get(phase, default_pct), 1)
    total_km = max(total_min_km, min(total_max_km, total_km))

    surges = max(surge_min, min(surge_max, round((total_km - 4) * surge_multiplier)))

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
        "description": f"{format_km(total_km)}km fartlek: {surges} surges of 1-3min at {_shared_format_pace(hard_pace)}, easy running between",
        "distance": total_km,
        "quality": True,
        "segments": segments,
        "total_duration_est_min": estimate_duration_min(segments),
    }
