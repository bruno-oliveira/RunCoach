"""Volume feedback — weekly mileage progress vs planned (pure messaging).

Pure: no I/O, no ORM. The caller (context layer) resolves the run's plan week
and the logged/planned km via
``app.contexts.runner.fitness.coaching_data.fetch_volume_inputs`` and passes the
plain values in.
"""

from typing import Optional


def volume_feedback(
    week_num: int, logged_km: float, planned_km: float
) -> Optional[str]:
    """Render weekly mileage progress vs planned.

    Args:
        week_num: 1-based plan week the run falls in.
        logged_km: Total km logged in that week so far.
        planned_km: Planned km for that week.

    Returns:
        A progress message, or None when there's no planned volume.
    """
    if planned_km <= 0:
        return None

    pct = (logged_km / planned_km) * 100
    if pct >= 100:
        return (
            f"Week {week_num} target reached! "
            f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
        )
    elif pct >= 75:
        return (
            f"Week {week_num} is on track: "
            f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
        )
    else:
        remaining = planned_km - logged_km
        return (
            f"Week {week_num}: {logged_km:.1f}/{planned_km:.1f} km "
            f"({pct:.0f}%). {remaining:.1f} km still to go."
        )
