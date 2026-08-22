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


# A shakeout's strides are part of its distance, not an extra on top. Four
# 100 m strides is 0.4 km, reserved out of the run block so the card, the steps
# and the description all report the same number.
_SHAKEOUT_STRIDE_REPS = 4
_SHAKEOUT_STRIDE_M = 100


def build_shakeout_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Day-before-race shakeout: easy running plus a few strides.

    The strides are carved *out of* ``distance_km`` rather than added to it, so
    the priced step total equals the distance on the card exactly. (Reusing
    ``build_easy_steps(with_strides=True)`` here silently overshot by 0.6 km,
    which on a 4 km shakeout is a 15% lie.)
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    strides_m = _SHAKEOUT_STRIDE_REPS * _SHAKEOUT_STRIDE_M
    easy_m = max(500, total_m - strides_m)
    return [
        _step(
            "run",
            "Easy shakeout",
            distance_m=easy_m,
            pace_zone="E",
            pace_str=_pace_str("E", pace_zones),
            effort="very easy",
            note="Slower than you think. Nothing to prove today",
        ),
        _step(
            "strides",
            f"{_SHAKEOUT_STRIDE_REPS} × {_SHAKEOUT_STRIDE_M} m strides",
            distance_m=_SHAKEOUT_STRIDE_M,
            repeat=_SHAKEOUT_STRIDE_REPS,
            pace_zone="R",
            pace_str=_pace_str("R", pace_zones),
            effort="fast, relaxed",
            note="Full recovery between — these wake the legs up, not tire them",
        ),
    ]


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


# Race-day pacing plan. The race is run in three acts rather than as one
# undifferentiated block: the opening is the only part a runner can ruin
# cheaply (going out hard costs far more later than it gains), the middle is
# where goal pace is simply held, and the closing third is what the taper was
# for. Fractions are deliberately front-light: a slightly conservative first
# act is the single most transferable piece of race advice there is.
_RACE_SPLIT = (0.30, 0.40, 0.30)


def race_pace_zone_key(target_distance_km: float, pace_zones: Optional[Dict]) -> str:
    """Pace-zone key holding the goal race pace for ``target_distance_km``.

    ``VDOTCalculator.get_pace_zones`` files 5K/10K under their own labels and
    every other target under ``"race"`` — but only when it was given the target
    distance. Falls back through the zones that bracket race effort (M for
    long races, T for short) so a race day still carries a usable pace when no
    race-specific entry was computed.
    """
    zones = pace_zones or {}
    if abs(target_distance_km - 5.0) < 0.5 and "5K" in zones:
        return "5K"
    if abs(target_distance_km - 10.0) < 0.5 and "10K" in zones:
        return "10K"
    if "race" in zones:
        return "race"
    return "M" if target_distance_km > 15.0 else "T"


def build_race_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    target_distance_km: Optional[float] = None,
    is_trail: bool = False,
) -> List[Dict[str, Any]]:
    """Steps for race day: the race itself, as a three-act pacing plan.

    Warm-up and cool-down are deliberately absent from the steps. The step
    total is what the card reports, and a race day must report the race
    distance exactly — a 5K that says 7.0 km because it priced in a warm-up
    is wrong on the one day the number is not an estimate. Warm-up guidance
    lives in the description instead.

    Trail races are paced by effort, not by a goal pace, so they get a single
    steady block with a hike-the-climbs cue rather than a split.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    target = target_distance_km if target_distance_km is not None else distance_km

    if is_trail:
        return [
            _step(
                "run",
                "Race",
                distance_m=total_m,
                pace_zone="E",
                pace_str=_pace_str("E", pace_zones),
                effort="steady, sustainable",
                note="Hike the steep climbs, eat and drink on schedule",
            )
        ]

    zone = race_pace_zone_key(target, pace_zones)
    pace = _pace_str(zone, pace_zones)
    opening_m = int(round(total_m * _RACE_SPLIT[0]))
    middle_m = int(round(total_m * _RACE_SPLIT[1]))
    closing_m = total_m - opening_m - middle_m
    return [
        _step(
            "run",
            "Opening — settle in",
            distance_m=opening_m,
            pace_zone=zone,
            pace_str=pace,
            effort="controlled",
            note="Goal pace or a touch slower. It should feel too easy here",
        ),
        _step(
            "run",
            "Middle — hold goal pace",
            distance_m=middle_m,
            pace_zone=zone,
            pace_str=pace,
            effort="goal race pace",
            note="Lock onto rhythm and stay on your fuelling plan",
        ),
        _step(
            "run",
            "Closing — race it home",
            distance_m=closing_m,
            pace_zone=zone,
            pace_str=pace,
            effort="everything left",
            note="This is what the taper was for",
        ),
    ]
