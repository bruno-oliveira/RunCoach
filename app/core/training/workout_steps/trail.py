"""Trail intensive-weekend builders: pyramid, ladder, hike-run, back-to-back."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import (
    _cooldown,
    _pace_str,
    _step,
    _warmup,
    _wucd_m,
)


def _build_rung_steps(
    rungs: List[int],
    pace_zones: Optional[Dict],
    pace_zone: str,
    wu_m: int,
    cd_m: int,
) -> List[Dict[str, Any]]:
    """Warm-up → (rep + equal-distance jog recovery) per rung → cool-down.

    Shared by :func:`build_pyramid_steps` and :func:`build_ladder_steps`.
    Each rep is followed by an equal-distance recovery jog, except the last.
    """
    steps: List[Dict[str, Any]] = [_warmup(pace_zones, wu_m)]
    last = len(rungs) - 1
    for i, rung_m in enumerate(rungs):
        steps.append(
            _step(
                "run",
                f"{rung_m} m",
                distance_m=rung_m,
                pace_zone=pace_zone,
                pace_str=_pace_str(pace_zone, pace_zones),
                effort="hard",
            )
        )
        if i < last:
            steps.append(
                _step(
                    "recovery",
                    f"{rung_m} m jog recovery",
                    distance_m=rung_m,
                    pace_zone="E",
                    pace_str=_pace_str("E", pace_zones),
                    effort="jog",
                )
            )
    steps.append(_cooldown(pace_zones, cd_m))
    return steps


def build_pyramid_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    pattern: Optional[List[int]] = None,
    pace_zone: str = "T",
) -> List[Dict[str, Any]]:
    """Symmetric pyramid (e.g. 400-800-1200-800-400) at trail/threshold pace.

    Recovery jogs are equal-distance to the rep just run. Defaults to a
    trail-pace pyramid suited to a Saturday intensive-weekend quality session.
    """
    if distance_km <= 0:
        return []
    if pattern is None:
        pattern = [400, 800, 1200, 800, 400]
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    return _build_rung_steps(pattern, pace_zones, pace_zone, wu_m, wu_m)


def build_ladder_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    rungs: Optional[List[int]] = None,
    pace_zone: str = "T",
) -> List[Dict[str, Any]]:
    """Ascending ladder (e.g. 400-800-1200-1600) at trail/threshold pace.

    A pyramid is a symmetric ladder; both share :func:`_build_rung_steps`.
    """
    if distance_km <= 0:
        return []
    if rungs is None:
        rungs = [400, 800, 1200, 1600]
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    return _build_rung_steps(rungs, pace_zones, pace_zone, wu_m, wu_m)


def build_hike_run_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    run_min: int = 9,
    hike_min: int = 1,
    sets: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Alternating run / power-hike long session for ultra-distance trail.

    Each set is a run block plus a power-hike block. Block distances are
    explicit (apportioned from a run≈6:00/km, hike≈12:00/km split) so the
    recomputed total is deterministic and not dependent on pace estimates.
    Follows the codebase convention (cf. ``build_alternating_mp_long_steps``)
    of one repeated step per block type rather than literal alternation.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    run_pace, hike_pace = 6.0, 12.0  # min/km
    run_block_m = int(round((run_min / run_pace) * 1000))
    hike_block_m = int(round((hike_min / hike_pace) * 1000))
    set_m = run_block_m + hike_block_m
    if set_m <= 0:
        return []
    if sets is None:
        sets = max(1, round(total_m / set_m))
    # Absorb the set-rounding remainder into the run block so the recomputed
    # total equals the prescribed distance (blocks stay "~9 min" / "~1 min",
    # as the description states). Without this, the integer set count dropped
    # ~0.5 km and the card diverged from the "Run {d}km" description.
    leftover = total_m - sets * set_m
    run_block_m = max(0, run_block_m + round(leftover / sets))
    return [
        _step(
            "run",
            f"{run_min} min run",
            distance_m=run_block_m,
            repeat=sets,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Settle into an easy rhythm",
        ),
        _step(
            "walk",
            f"{hike_min} min power hike",
            distance_m=hike_block_m,
            repeat=sets,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="power hike",
            note="Drive the hips, hands on thighs — rehearse race-day climbing",
        ),
    ]


def build_back_to_back_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    day1_fraction: float = 0.57,
) -> List[Dict[str, Any]]:
    """Two-day back-to-back weekend modelled as two run blocks.

    The card distance is the weekend total; the two blocks (Saturday on fresh
    legs, Sunday on fatigued legs) carry the split the description cites, so
    the executable steps sum to the total and the description's per-day numbers
    resolve to a step.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    day1_m = int(round(total_m * day1_fraction))
    day2_m = total_m - day1_m
    return [
        _step(
            "run",
            "Saturday — hilly trail",
            distance_m=day1_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Easy effort on hilly terrain",
        ),
        _step(
            "run",
            "Sunday — fatigued legs",
            distance_m=day2_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="On legs fatigued from yesterday — hold easy effort",
        ),
    ]
