"""Plan-schema helpers shared across PlanRequest / FitnessPlanRequest / PerformancePlanRequest."""

from typing import Optional

from app.core.training.training_config import DISTANCE_CONSTRAINTS

_MILEAGE_CONFIG = {
    distance: {
        "min": c.min_mileage,
        "max": c.max_mileage,
        "low_msg": c.low_mileage_msg,
        "high_msg": c.high_mileage_msg,
    }
    for distance, c in DISTANCE_CONSTRAINTS.items()
}


def parse_target_distance(value: str | float) -> float:
    """
    Convert target_distance from database (string) to float.
    Handles legacy "trail" values by converting to 30.0.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if value.lower() == "trail":
        return 30.0
    return float(value)


def compute_vdot_from_time(
    distance_km: float, time_str: str, field_name: str = "race time"
) -> tuple[float, float]:
    """Parse a finish time and return (VDOT, pace_min_per_km) for the given distance.

    Raises ValueError if the time string is unparseable. Centralised so plan and
    fitness request schemas share one VDOT-derivation path.
    """
    from app.core.training.vdot_calculator import VDOTCalculator

    seconds = VDOTCalculator.parse_time_to_seconds(time_str)
    if not seconds or seconds <= 0:
        raise ValueError(
            f"Could not parse {field_name} '{time_str}'. "
            "Use HH:MM:SS or MM:SS format (e.g. '42:15' or '1:45:30')."
        )
    vdot = VDOTCalculator.calculate_vdot(distance_km, seconds)
    pace_min_km = (seconds / 60) / distance_km
    return vdot, pace_min_km


def get_mileage_warning(
    target_distance: float,
    current_km: float,
    is_trail: bool = False,
    target_elevation_gain_m: Optional[float] = None,
) -> Optional[str]:
    """Get warning message if mileage is unusually high for target distance."""
    if is_trail:
        from app.core.training.trail_profile import (
            classify_trail,
            trail_max_weekly_mileage,
        )

        profile = classify_trail(target_distance, target_elevation_gain_m or 0.0)
        if current_km > trail_max_weekly_mileage(profile):
            return (
                "High mileage for this trail/ultra distance. "
                "Focus on time-on-feet, recovery, and consistency rather than chasing volume."
            )
        return None

    if target_distance in _MILEAGE_CONFIG:
        cfg = _MILEAGE_CONFIG[target_distance]
        if current_km > cfg["max"]:
            return cfg["high_msg"]
    return None
