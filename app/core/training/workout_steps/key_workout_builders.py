"""Structured builders for the curated key-workout families.

km-rep cruise/segments, easy-start/faster-finish splits, fartlek/over-under,
progression blocks, continuous runs, fixed-metre reps, and time-based reps.
Each derives steps directly from the assigned distance (no prose parsing).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import (
    _cooldown,
    _pace_str,
    _step,
    _warmup,
    _wucd_m,
)


def build_meter_rep_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    reps: int,
    rep_m: int,
    work_zone: str = "I",
    recovery_label: str = "easy jog recovery",
) -> List[Dict[str, Any]]:
    """Warm-up + N × <rep_m> work reps with jog recovery + cool-down.

    The rep distance is honoured *literally* (e.g. 400 m): the leftover of the
    work budget after the reps becomes the recovery-jog distance, so the
    session totals the prescribed distance AND each rep matches the
    prescription. (The prose parser instead inflated the rep distance to fill
    the budget — a 400 m rep came out as ~650 m, contradicting the
    description.)
    """
    if distance_km <= 0 or reps <= 0 or rep_m <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    cd_m = wu_m
    work_budget = max(0, total_m - wu_m - cd_m)
    work_total = min(work_budget, reps * rep_m)
    rec_total = max(0, work_budget - work_total)
    rec_m = int(round(rec_total / reps))
    steps = [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{reps} × {rep_m} m",
            distance_m=rep_m,
            repeat=reps,
            pace_zone=work_zone,
            pace_str=_pace_str(work_zone, pace_zones),
            effort="hard",
        ),
    ]
    if rec_m > 0:
        steps.append(
            _step(
                "recovery",
                recovery_label,
                distance_m=rec_m,
                repeat=reps,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="easy jog",
            )
        )
    steps.append(_cooldown(pace_zones, cd_m))
    return steps


def build_km_rep_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    reps: int,
    work_zone: str,
    recovery_s: Optional[int] = None,
    work_effort: str = "comfortably hard",
) -> List[Dict[str, Any]]:
    """Warm-up + N × <X km> work reps (+ optional jog recovery) + cool-down.

    The rep distance is scaled to fill the warm-up/cool-down-adjusted budget
    (a 200 m floor, snapped to 100 m at/above 1 km and 50 m below) so the reps
    total the prescribed distance. The recovery step, when present, is
    duration-based with no pace zone so it adds no distance — matching the
    cruise/segment family the prose rewrites describe.
    """
    if distance_km <= 0 or reps <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    cd_m = wu_m
    work_m = max(0, total_m - 2 * wu_m)
    if work_m <= 0:
        return []
    rep_m = max(200, int(round(work_m / reps)))
    if rep_m >= 1000:
        rep_m = int(round(rep_m / 100.0)) * 100
    else:
        rep_m = int(round(rep_m / 50.0)) * 50
    rep_label = (
        f"{reps} × {rep_m / 1000:.1f} km" if rep_m >= 1000 else f"{reps} × {rep_m} m"
    )
    steps = [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            rep_label,
            distance_m=rep_m,
            repeat=reps,
            pace_zone=work_zone,
            pace_str=_pace_str(work_zone, pace_zones),
            effort="hard" if work_zone in ("I", "R") else work_effort,
        ),
    ]
    if recovery_s:
        steps.append(
            _step(
                "recovery",
                f"{recovery_s} s jog between reps",
                duration_s=recovery_s,
                repeat=reps - 1,
                effort="jog",
            )
        )
    steps.append(_cooldown(pace_zones, cd_m))
    return steps


def build_fartlek_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    reps: int,
    on_s: int,
    off_s: int,
    on_zone: str,
    work_effort: str = "hard",
) -> List[Dict[str, Any]]:
    """Warm-up + N × duration-based on-reps + cool-down (fartlek / over-under).

    The off-jogs are explicit recovery steps (the same pattern as
    ``build_meter_rep_steps``): the runner covers that ground, so it counts
    toward the session distance, and structured exports get the real
    on/off alternation instead of back-to-back work reps.
    """
    if distance_km <= 0 or reps <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    on_label = f"{on_s // 60} min" if on_s >= 60 else f"{on_s} s"
    off_label = f"{off_s // 60} min" if off_s >= 60 else f"{off_s} s"
    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{reps} × {on_label} on / {off_label} off",
            duration_s=on_s,
            repeat=reps,
            pace_zone=on_zone,
            pace_str=_pace_str(on_zone, pace_zones),
            effort=work_effort,
        ),
        _step(
            "recovery",
            f"{off_label} easy jog between reps",
            duration_s=off_s,
            repeat=reps,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="easy jog",
        ),
        _cooldown(pace_zones, wu_m),
    ]


def build_progression_block_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    block_zone: str,
    label: str = "Tempo progression",
    effort: str = "build to tempo",
) -> List[Dict[str, Any]]:
    """Warm-up + single progressive run block + cool-down."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    block_m = max(0, total_m - 2 * wu_m)
    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            label,
            distance_m=block_m,
            pace_zone=block_zone,
            pace_str=_pace_str(block_zone, pace_zones),
            effort=effort,
        ),
        _cooldown(pace_zones, wu_m),
    ]


def build_continuous_quality_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    zone: str,
    effort: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Continuous run at a single zone.

    Easy-zone runs are self-contained (the run is its own warm-up) and cover
    the full distance; tempo/threshold runs add a warm-up + cool-down around a
    continuous block.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    if zone == "E":
        return [
            _step(
                "run",
                f"{total_m / 1000:.1f} km continuous",
                distance_m=total_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort=effort or "conversational",
            )
        ]
    wu_m = _wucd_m(total_m)
    block_m = max(0, total_m - 2 * wu_m)
    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{block_m / 1000:.1f} km continuous",
            distance_m=block_m,
            pace_zone=zone,
            pace_str=_pace_str(zone, pace_zones),
            effort=effort or "comfortably hard",
        ),
        _cooldown(pace_zones, wu_m),
    ]


def build_duration_rep_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    reps: int,
    work_s: int,
    work_zone: str,
    work_kind: str = "run",
    cue: str = "",
    work_effort: str = "hard",
    label: Optional[str] = None,
    recovery_s: Optional[int] = None,
    recovery_kind: str = "recovery",
    recovery_effort: str = "jog",
    recovery_label: Optional[str] = None,
    recovery_zone: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Warm-up + N × time-based work reps (+ optional recovery) + cool-down.

    Distance for the work reps is derived from duration × pace at
    ``work_zone``; an optional recovery block (jog/walk) can follow each rep.
    Pass ``recovery_zone`` when the recovery is real covered ground (an easy
    run between power-hike blocks) so it prices into the session distance;
    leave it None for standing/walk-down recoveries that shouldn't count.
    Used by hill/elevation/technique sessions whose work is defined by time.
    """
    if distance_km <= 0 or reps <= 0 or work_s <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    work_label = label or (
        f"{reps} × {work_s} s {cue}".rstrip() if cue else f"{reps} × {work_s} s"
    )
    steps = [
        _warmup(pace_zones, wu_m),
        _step(
            work_kind,
            work_label,
            duration_s=work_s,
            repeat=reps,
            pace_zone=work_zone,
            pace_str=_pace_str(work_zone, pace_zones),
            effort=work_effort,
        ),
    ]
    if recovery_s:
        steps.append(
            _step(
                recovery_kind,
                recovery_label or f"{recovery_s} s recovery",
                duration_s=recovery_s,
                repeat=reps,
                pace_zone=recovery_zone,
                pace_str=_pace_str(recovery_zone, pace_zones)
                if recovery_zone
                else None,
                effort=recovery_effort,
            )
        )
    steps.append(_cooldown(pace_zones, wu_m))
    return steps
