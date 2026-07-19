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


def build_tempo_steps(
    distance_km: float,
    pace_zones: Optional[Dict] = None,
    variant: int = 0,
) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
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
    identically. Below that, 400 m reps are the default.
    """
    if distance_km <= 0:
        return []
    total_m = int(round(distance_km * 1000))
    wu_m = _wucd_m(total_m)
    cd_m = wu_m
    work_m = max(1600, total_m - wu_m - cd_m)

    if total_km >= 50:
        default_rep_m = 800
    else:
        default_rep_m = 400

    default_reps = max(4, work_m // default_rep_m)

    if total_km >= 50:
        return _build_interval_steps_high_base(
            variant,
            pace_zones,
            reps_400 or default_reps,
            reps_800 or default_reps,
            reps_1000 or max(3, work_m // 2000),
            wu_m,
            cd_m,
        )
    return _build_interval_steps_low_base(
        variant,
        pace_zones,
        default_reps,
        reps_400 or default_reps,
        reps_800 or max(3, work_m // 1600),
        reps_200 or max(6, work_m // 400),
        wu_m,
        cd_m,
    )


def _build_interval_steps_high_base(
    variant: int,
    pace_zones: Optional[Dict],
    reps_400: int,
    reps_800: int,
    reps_1000: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
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
                "400 m jog recovery",
                distance_m=400,
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
            "400 m jog recovery",
            distance_m=400,
            repeat=reps_400 - 1,
            pace_zone="E",
            effort="jog",
        ),
        _cooldown(pace_zones, cd_m),
    ]


def _build_interval_steps_low_base(
    variant: int,
    pace_zones: Optional[Dict],
    default_reps: int,
    reps_400: int,
    reps_800: int,
    reps_200: int,
    wu_m: int = _WARMUP_M,
    cd_m: int = _COOLDOWN_M,
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
                "200 m jog recovery",
                distance_m=200,
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
            "90 s jog recovery",
            duration_s=90,
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
    wu_m = _wucd_m(total_m) if total_m > 0 else _WARMUP_M
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
