"""Pace feedback — compare actual pace vs planned pace."""

from typing import Optional

from app.utils import format_pace_bare


PACE_TOLERANCES: dict[str, tuple[float, float]] = {
    "easy": (0.10, -0.08),
    "recovery": (0.15, -0.05),
    "long": (0.10, -0.08),
    "tempo": (0.05, -0.05),
    "interval": (0.08, -0.08),
    "hill": (0.10, -0.10),
}


def pace_feedback(run_log, planned_workout) -> Optional[str]:
    """Compare actual pace vs planned pace."""
    if not planned_workout:
        return None

    planned_pace = getattr(planned_workout, "planned_pace_min_km", None)
    actual_pace = run_log.avg_pace_min_km
    if not planned_pace or not actual_pace:
        return None

    wtype = (
        planned_workout.workout_type
        or run_log.workout_type
        or "easy"
    ).lower()
    slow_tol, fast_tol = PACE_TOLERANCES.get(wtype, (0.10, -0.08))

    diff_pct = (actual_pace - planned_pace) / planned_pace

    actual_str = format_pace_bare(actual_pace)
    planned_str = format_pace_bare(planned_pace)

    if diff_pct > slow_tol:
        return (
            f"Pace was slower than target ({actual_str}/km vs "
            f"{planned_str}/km). Check if you were tired or "
            "if conditions were challenging."
        )
    elif diff_pct < fast_tol:
        if wtype in ("easy", "recovery", "long"):
            return (
                f"Your {wtype} run was faster than planned "
                f"({actual_str}/km vs {planned_str}/km). "
                "Slow down to protect your aerobic base and recovery."
            )
        return (
            f"Pace was faster than target ({actual_str}/km vs "
            f"{planned_str}/km). Great speed — just make sure "
            "you can sustain this for the full workout."
        )
    else:
        return (
            f"Pace was right on target ({actual_str}/km vs "
            f"{planned_str}/km). Great execution!"
        )
