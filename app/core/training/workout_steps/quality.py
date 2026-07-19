"""Quality builders: tempo, interval, hill, and key-workout step builders."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import (
    _COOLDOWN_M,
    _WARMUP_M,
    _cooldown,
    _pace_str,
    _step,
    _warmup,
    _wucd_m,
)
from app.utils import format_km


def cruise_recovery_m(main_m: int) -> int:
    """Jog recovery per cruise-interval rep (variant 1), scaled to the budget.

    Distance-based so the whole session is priced inside the budget
    (duration-based recoveries added distance on top of it and the card and
    steps disagreed). Capped at 300 m and scaled down on micro budgets so
    the two recoveries never dominate the reps. Mirrored by
    ``generate_tempo_run``'s description text.
    """
    return min(300, max(100, (main_m // 10) // 50 * 50))


def interval_rep_plan(
    work_m: int, rep_m: int, *, min_reps: int = 2, work_share: float = 0.6
) -> tuple:
    """(reps, recovery_m) for a rep session that fills its work budget.

    ~60% of the warm-up/cool-down-adjusted budget goes to the reps; the
    remainder becomes the jog recovery between them, snapped to 50 m and
    clamped to a sane band (100 m .. min(600, max(300, rep_m))) so the jog
    stays shorter than a rep at the long end and never degenerates to a
    standing rest at the short end. Because the recovery absorbs the budget
    leftover, the priced step total tracks the assigned distance instead of
    rounding a whole rep's worth of kilometres away — which froze adaptation
    (a boosted session rebuilt to its old card) and let cards drop below the
    week's quality dose. Used by both the step builders and
    ``generate_interval_run``'s prose so the two cite identical numbers.
    """
    if rep_m <= 0 or work_m <= 0:
        return (min_reps, 100)
    reps = max(min_reps, round(work_m * work_share / rep_m))
    gaps = max(1, reps - 1)
    leftover = max(0, work_m - reps * rep_m)
    hi = min(600, max(300, rep_m))
    rec_m = min(hi, max(100, (leftover // gaps) // 50 * 50))
    return (reps, rec_m)


def interval_session_plan(distance_km: float, total_km: float) -> Dict[str, int]:
    """Shared arithmetic for the generic interval session.

    Both ``build_interval_steps`` (the executable steps) and
    ``generate_interval_run`` (the prose) derive their warm-up, rep counts and
    recovery distances from this one plan so they can never cite different
    numbers. The 50 km/week threshold selects the high-base variant table.
    """
    total_m = max(0, int(round(distance_km * 1000)))
    wu_m = _wucd_m(total_m, hard=True) if total_m > 0 else _WARMUP_M
    work_m = max(500, total_m - 2 * wu_m)
    work_km = work_m / 1000.0
    if total_km >= 50:
        reps_400, rec_400 = interval_rep_plan(work_m, 400, min_reps=4)
        reps_1000, rec_1000 = interval_rep_plan(work_m, 1000, min_reps=3)
        reps_200, rec_200 = interval_rep_plan(work_m, 200, min_reps=6)
        reps_800 = max(4, round(work_km / 1.6))
    else:
        reps_400, rec_400 = interval_rep_plan(work_m, 400)
        reps_1000, rec_1000 = 0, 0
        reps_200, rec_200 = interval_rep_plan(work_m, 200, min_reps=4)
        reps_800 = max(2, round(work_km / 1.6))
    return {
        "wu_m": wu_m,
        "work_m": work_m,
        "reps_400": reps_400,
        "rec_400": rec_400,
        "reps_800": reps_800,
        "reps_1000": reps_1000,
        "rec_1000": rec_1000,
        "reps_200": reps_200,
        "rec_200": rec_200,
    }


def build_tempo_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    variant: int = 0,
) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m, hard=False)
    cd_m = wu_m
    main_m = max(500, total_m - wu_m - cd_m)

    if variant == 1:
        rec_m = cruise_recovery_m(main_m)
        rep_m_raw = max(600, main_m - 2 * rec_m) // 3
        # Snap to the same 100 m (at/above 1 km) or 50 m (below) boundaries
        # that build_km_rep_steps uses, so format_km is lossless and the step
        # label matches the description precisely.
        if rep_m_raw >= 1000:
            rep_m = int(round(rep_m_raw / 100.0)) * 100
        else:
            rep_m = int(round(rep_m_raw / 50.0)) * 50
        rep_m = max(200, rep_m)
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"3 × {format_km(rep_m / 1000.0)} km",
                distance_m=rep_m,
                repeat=3,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="comfortably hard",
            ),
            _step(
                "recovery",
                f"{rec_m} m jog recovery",
                distance_m=rec_m,
                repeat=2,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{format_km(main_m / 1000.0)} km tempo with surges",
                distance_m=main_m,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="comfortably hard",
                note="4 × 30 s faster surges within the tempo block",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{format_km(main_m / 1000.0)} km tempo",
            distance_m=main_m,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="comfortably hard",
            note="Relaxed rhythm, not a race",
        ),
        _cooldown(pace_zones, cd_m),
    ]


def build_interval_steps(
    distance_km: float,
    total_km: float,
    pace_zones: Optional[Dict] = None,
    variant: int = 0,
    reps_400: int = 0,
    reps_800: int = 0,
    reps_1000: int = 0,
    reps_200: int = 0,
) -> List[Dict[str, Any]]:
    """Interval session — step structure matches the selected description variant.

    The 50 km/week threshold matches ``generate_interval_run`` so the
    description variant table and the step variant table are sized
    identically. Below that, 400 m reps are the default. Rep counts and jog
    recoveries default to :func:`interval_session_plan` (shared with the
    prose); explicit ``reps_*`` arguments override the plan's counts.
    """
    if distance_km <= 0:
        return []
    plan = interval_session_plan(distance_km, total_km)
    wu_m = plan["wu_m"]
    cd_m = wu_m

    if total_km >= 50:
        return _build_interval_steps_high_base(
            variant,
            pace_zones,
            reps_400 or plan["reps_400"],
            reps_800 or plan["reps_800"],
            reps_1000 or plan["reps_1000"],
            wu_m,
            cd_m,
            rec_400=plan["rec_400"],
            rec_1000=plan["rec_1000"],
        )
    return _build_interval_steps_low_base(
        variant,
        pace_zones,
        reps_400 or plan["reps_400"],
        reps_800 or plan["reps_800"],
        reps_200 or plan["reps_200"],
        wu_m,
        cd_m,
        rec_400=plan["rec_400"],
        rec_200=plan["rec_200"],
    )


def _build_interval_steps_high_base(
    variant: int,
    pace_zones: Optional[Dict],
    reps_400: int,
    reps_800: int,
    reps_1000: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
    *,
    rec_400: int = 400,
    rec_1000: int = 400,
) -> List[Dict[str, Any]]:
    if variant == 1:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                "400 m",
                distance_m=400,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step(
                "run",
                "800 m",
                distance_m=800,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step(
                "run",
                "1200 m",
                distance_m=1200,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step(
                "run",
                "800 m",
                distance_m=800,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step(
                "run",
                "400 m",
                distance_m=400,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step("recovery", "Equal-distance recovery jog", effort="jog"),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                "8 × 45 s hill repeats",
                duration_s=45,
                repeat=8,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="hard uphill",
            ),
            _step(
                "recovery", "Jog-down recovery", duration_s=90, repeat=8, effort="jog"
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 3:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{reps_800} × 800 m (Yasso)",
                distance_m=800,
                repeat=reps_800,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="hard",
            ),
            _step(
                "recovery",
                "Equal-time jog recovery",
                duration_s=180,
                repeat=reps_800 - 1,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 4:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{reps_1000} × 1000 m",
                distance_m=1000,
                repeat=reps_1000,
                pace_zone="I",
                pace_str=_pace_str("I", pace_zones),
                effort="hard",
            ),
            _step(
                "recovery",
                f"{rec_1000} m jog recovery",
                distance_m=rec_1000,
                repeat=reps_1000 - 1,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{reps_400} × 400 m",
            distance_m=400,
            repeat=reps_400,
            pace_zone="I",
            pace_str=_pace_str("I", pace_zones),
            effort="hard",
        ),
        _step(
            "recovery",
            f"{rec_400} m jog recovery",
            distance_m=rec_400,
            repeat=reps_400 - 1,
            pace_zone="E",
            effort="jog",
        ),
        _cooldown(pace_zones, cd_m),
    ]


def _build_interval_steps_low_base(
    variant: int,
    pace_zones: Optional[Dict],
    reps_400: int,
    reps_800: int,
    reps_200: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
    *,
    rec_400: int = 400,
    rec_200: int = 200,
) -> List[Dict[str, Any]]:
    if variant == 1:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{reps_800} × 800 m",
                distance_m=800,
                repeat=reps_800,
                pace_zone="T",
                pace_str=_pace_str("T", pace_zones),
                effort="comfortably hard",
            ),
            _step(
                "recovery",
                "90 s rest",
                duration_s=90,
                repeat=reps_800 - 1,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 2:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                f"{reps_200} × 200 m",
                distance_m=200,
                repeat=reps_200,
                pace_zone="R",
                pace_str=_pace_str("R", pace_zones),
                effort="fast",
            ),
            _step(
                "recovery",
                f"{rec_200} m jog recovery",
                distance_m=rec_200,
                repeat=reps_200 - 1,
                pace_zone="E",
                effort="jog",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    if variant == 3:
        return [
            _warmup(pace_zones, wu_m),
            _step(
                "run",
                "8 × 30 s hill repeats",
                duration_s=30,
                repeat=8,
                pace_zone="R",
                effort="hard uphill",
            ),
            _step(
                "recovery",
                "Walk-down recovery",
                duration_s=60,
                repeat=8,
                pace_zone="WALK",
                effort="walk",
            ),
            _cooldown(pace_zones, cd_m),
        ]

    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            f"{reps_400} × 400 m",
            distance_m=400,
            repeat=reps_400,
            pace_zone="I",
            pace_str=_pace_str("I", pace_zones),
            effort="hard",
        ),
        _step(
            "recovery",
            f"{rec_400} m jog recovery",
            distance_m=rec_400,
            repeat=reps_400 - 1,
            pace_zone="E",
            effort="jog",
        ),
        _cooldown(pace_zones, cd_m),
    ]


def build_hill_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    total_m = max(0, int(round(distance_km * 1000)))
    wu_m = _wucd_m(total_m, hard=True) if total_m > 0 else _WARMUP_M
    cd_m = wu_m
    return [
        _warmup(pace_zones, wu_m),
        _step(
            "run",
            "10 × 30 s hill",
            duration_s=30,
            repeat=10,
            pace_zone="R",
            effort="hard uphill",
            note="Strong arms, quick turnover",
        ),
        _step(
            "recovery",
            "Walk down recovery",
            duration_s=60,
            repeat=10,
            pace_zone="WALK",
            effort="walk",
        ),
        _cooldown(pace_zones, cd_m),
    ]
