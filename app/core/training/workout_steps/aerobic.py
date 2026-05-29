"""Aerobic builders: easy runs, long runs, and long-run variants."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import _pace_str, _step


def build_easy_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    with_strides: bool = False,
) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    steps = [
        _step(
            "run",
            "Easy run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
        )
    ]
    if with_strides:
        steps.append(
            _step(
                "strides",
                "6 × 100 m strides",
                distance_m=100,
                repeat=6,
                pace_zone="R",
                pace_str=_pace_str("R", pace_zones),
                effort="fast, controlled",
                note="Walk/jog back full recovery",
            )
        )
    return steps


def build_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    variant: str = "easy",
) -> List[Dict[str, Any]]:
    """Long run steps.

    variant: 'easy' (steady E), 'mp_finish' (80% E + 20% M), 'progression'
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    if variant == "mp_finish":
        easy_m = int(round(total_m * 0.8))
        mp_m = total_m - easy_m
        return [
            _step(
                "run",
                "Easy aerobic",
                distance_m=easy_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="conversational",
                note="Fuel every 45 min",
            ),
            _step(
                "run",
                "Marathon-pace finish",
                distance_m=mp_m,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="comfortably hard",
            ),
        ]
    if variant == "progression":
        thirds = total_m // 3
        return [
            _step(
                "run",
                "Easy start",
                distance_m=thirds,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="conversational",
            ),
            _step(
                "run",
                "Steady middle",
                distance_m=thirds,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="moderate",
                note="15 s/km faster than start",
            ),
            _step(
                "run",
                "Marathon-pace finish",
                distance_m=total_m - 2 * thirds,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="strong finish",
            ),
        ]
    if variant == "alternating_mp":
        return build_alternating_mp_long_steps(distance_km, pace_zones)
    if variant == "fast_finish":
        return build_fast_finish_long_steps(distance_km, pace_zones)
    if variant == "rolling_hills":
        return build_rolling_hills_long_steps(distance_km, pace_zones)
    if variant == "depletion":
        return build_depletion_long_steps(distance_km, pace_zones)
    return [
        _step(
            "run",
            "Long run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Fuel every 45-60 min",
        )
    ]


def build_alternating_mp_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    block_km: float = 2.0,
) -> List[Dict[str, Any]]:
    """Long run alternating easy and marathon-pace blocks.

    Example: 16 km → 4 × (2 km easy / 2 km MP).
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    block_m = int(round(block_km * 1000))
    pair_m = block_m * 2
    full_pairs = total_m // pair_m
    if full_pairs < 1:
        full_pairs = 1
        block_m = total_m // 2
    steps: List[Dict[str, Any]] = [
        _step(
            "run",
            f"Easy {block_m // 1000} km",
            distance_m=block_m,
            repeat=full_pairs,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
        ),
        _step(
            "run",
            f"Marathon-pace {block_m // 1000} km",
            distance_m=block_m,
            repeat=full_pairs,
            pace_zone="M",
            pace_str=_pace_str("M", pace_zones),
            effort="comfortably hard",
            note="Alternate easy → MP blocks. No rest.",
        ),
    ]
    remainder_m = total_m - (full_pairs * pair_m)
    if remainder_m >= 500:
        steps.append(
            _step(
                "run",
                "Easy cool",
                distance_m=remainder_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="easy",
            )
        )
    return steps


def build_fast_finish_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    finish_km: float = 3.0,
) -> List[Dict[str, Any]]:
    """Long run with a hard (T-pace) final segment."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    finish_m = min(int(round(finish_km * 1000)), max(1000, total_m // 4))
    easy_m = total_m - finish_m
    return [
        _step(
            "run",
            "Easy aerobic base",
            distance_m=easy_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
            note="Relax, save legs for the finish",
        ),
        _step(
            "run",
            f"{finish_m / 1000:.0f} km fast finish",
            distance_m=finish_m,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="comfortably hard → hard",
            note="Build effort through the last km",
        ),
    ]


def build_rolling_hills_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Long run on a rolling hills route at steady easy effort."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    return [
        _step(
            "run",
            "Rolling hills — steady",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="by effort, not pace",
            note="Keep effort even — push up, float down.",
        )
    ]


def build_depletion_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Fasted / low-carb long run for mitochondrial adaptation (marathon)."""
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    return [
        _step(
            "run",
            "Fasted long run",
            distance_m=total_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="easy, conservative",
            note="No carbs pre-run. Water only during. Drives fat-adaptation.",
        )
    ]


def build_split_long_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    *,
    easy_mult: float,
    finish_mult: float,
    finish_zone: str = "M",
) -> List[Dict[str, Any]]:
    """Easy-start + faster-finish long run (no warm-up/cool-down).

    ``easy_mult``/``finish_mult`` mirror the description rewrite's split (e.g.
    0.60/0.40). The split is normalised proportionally onto the actual distance
    so the two blocks total it exactly and match the cited fractions.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    easy_raw = round(distance_km * easy_mult, 1)
    finish_raw = round(distance_km * finish_mult, 1)
    ratio = easy_raw + finish_raw
    if ratio <= 0:
        return []
    easy_km = distance_km * easy_raw / ratio
    easy_m = int(round(easy_km * 1000))
    finish_m = total_m - easy_m
    return [
        _step(
            "run",
            "Easy start",
            distance_m=easy_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="conversational",
        ),
        _step(
            "run",
            "Faster finish",
            distance_m=finish_m,
            pace_zone=finish_zone,
            pace_str=_pace_str(finish_zone, pace_zones),
            effort="comfortably hard",
        ),
    ]
