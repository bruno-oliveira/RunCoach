"""Shared workout-builder primitives for fitness and performance plans.

Both plan families assemble workouts from the same warm-up / main / cool-down
segment shapes and the same duration estimate. The fitness and performance
builder modules import these helpers and supply their own phase tuning for the
parameterized tempo / fartlek builders, so the segment-construction logic lives
in exactly one place.
"""

from typing import Any, Dict, Mapping, Tuple

from app.core.training.workout_steps import _wucd_m, _wucd_m_for_work
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

    # Bookends come from the shared warm-up/cool-down policy (sized from the
    # work block, since the session total isn't known yet) so performance
    # plans and road plans prescribe identical warm-ups for identical work.
    warmup_km = _wucd_m_for_work(int(round(tempo_km * 1000)), hard=False) / 1000
    cooldown_km = warmup_km
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

    warmup_km = _wucd_m(int(round(total_km * 1000)), hard=False) / 1000
    cooldown_km = warmup_km
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


def reconcile_workout_after_cap(workout: Dict[str, Any]) -> None:
    """Sync segments and description after enforce_week_caps reduced distance.

    Shared by the performance and fitness generators: both build segment-based
    workouts of the same shape (warm-up / main / cool-down), so the same
    reconciliation keeps ``distance``, segments, and the description citing one
    consistent one-decimal figure after a cap shaves the workout down.
    """
    segments = workout.get("segments")
    if not segments:
        return

    seg_total = round(sum(s["distance_km"] for s in segments), 1)
    target = workout["distance"]

    # Reconcile on any drift beyond the one-decimal grid. A looser tolerance
    # (the old 0.15) let a sub-0.15 cap silently leave the header/segments at
    # the pre-cap value while ``distance`` moved — so the card showed e.g.
    # "6.6km race pace" with distance 6.5. Distance, segments, and description
    # must always cite the identical one-decimal figure.
    if abs(seg_total - target) < 0.05:
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
            f"{format_km(total_km)}km tempo: {format_km(wu_km)}km warmup, "
            f"{format_km(main['distance_km'])}km at {main['pace_formatted']}, "
            f"{format_km(cd_km)}km cooldown"
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
                f"{format_km(total_km)}km intervals: {format_km(wu_km)}km warmup, "
                f"{ivl['reps']}x{ivl['interval_m']}m at {main['pace_formatted']}{rec}, "
                f"{format_km(cd_km)}km cooldown"
            )
        else:
            workout["description"] = (
                f"{format_km(total_km)}km intervals: {format_km(wu_km)}km warmup, "
                f"{format_km(main['distance_km'])}km at {main['pace_formatted']}, "
                f"{format_km(cd_km)}km cooldown"
            )
    elif wtype == "race_pace":
        workout["description"] = (
            f"{format_km(total_km)}km race pace: {format_km(wu_km)}km warmup, "
            f"{format_km(main['distance_km'])}km at {main['pace_formatted']}, "
            f"{format_km(cd_km)}km cooldown"
        )
    elif wtype == "fartlek":
        ivl = main.get("intervals", {})
        pace_parts = main["pace_formatted"].split(" - ")
        hard_pace = pace_parts[-1] if len(pace_parts) > 1 else main["pace_formatted"]
        reps = ivl.get("reps", 0) if ivl else 0
        workout["description"] = (
            f"{format_km(total_km)}km fartlek: {reps} surges of 1-3min at {hard_pace}, "
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
                f"{format_km(total_km)}km {wtype}: {format_km(wu_km)}km warmup, "
                f"{ivl['reps']}x{ivl['interval_m']}m at {main['pace_formatted']}{rec}, "
                f"{format_km(cd_km)}km cooldown"
            )
        else:
            workout["description"] = (
                f"{format_km(total_km)}km {wtype}: {format_km(wu_km)}km warmup, "
                f"{format_km(main['distance_km'])}km at {main['pace_formatted']}, "
                f"{format_km(cd_km)}km cooldown"
            )
