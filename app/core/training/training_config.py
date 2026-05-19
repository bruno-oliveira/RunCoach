"""Per-distance training constraints and messages.

Replaces the flat `min_mileage_5k`, `max_weeks_marathon`, etc. attributes on
``Settings`` with a structured registry keyed by target distance (km).

Values are sourced from ``Settings`` so existing environment-variable overrides
keep working. New code should depend on this registry rather than touching
``settings`` directly for per-distance values.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from app.config import settings


@dataclass(frozen=True)
class DistanceConstraints:
    """Bracket of weeks, mileage, and guidance for a single target distance."""

    min_weeks: int
    max_weeks: int
    min_mileage: float
    max_mileage: float
    low_mileage_msg: str
    high_mileage_msg: str
    perf_min_mileage: Optional[int] = None
    insufficient_time_reason: str = ""
    excessive_time_reason: str = ""


DISTANCE_CONSTRAINTS: Dict[float, DistanceConstraints] = {
    5.0: DistanceConstraints(
        min_weeks=settings.min_weeks_5k,
        max_weeks=settings.max_weeks_5k,
        min_mileage=settings.min_mileage_5k,
        max_mileage=settings.max_mileage_5k,
        low_mileage_msg=settings.low_mileage_msg_5k,
        high_mileage_msg=settings.high_mileage_msg_5k,
        perf_min_mileage=settings.perf_min_mileage_5k,
        insufficient_time_reason="4 weeks provides a solid foundation for 5K improvement",
        excessive_time_reason="Training beyond 16 weeks for 5K can lead to burnout",
    ),
    10.0: DistanceConstraints(
        min_weeks=settings.min_weeks_10k,
        max_weeks=settings.max_weeks_10k,
        min_mileage=settings.min_mileage_10k,
        max_mileage=settings.max_mileage_10k,
        low_mileage_msg=settings.low_mileage_msg_10k,
        high_mileage_msg=settings.high_mileage_msg_10k,
        perf_min_mileage=settings.perf_min_mileage_10k,
        insufficient_time_reason="6 weeks allows for proper 10K preparation",
        excessive_time_reason="16 weeks is optimal for 10K preparation",
    ),
    21.1: DistanceConstraints(
        min_weeks=settings.min_weeks_half,
        max_weeks=settings.max_weeks_half,
        min_mileage=settings.min_mileage_half,
        max_mileage=settings.max_mileage_half,
        low_mileage_msg=settings.low_mileage_msg_half,
        high_mileage_msg=settings.high_mileage_msg_half,
        perf_min_mileage=settings.perf_min_mileage_half,
        insufficient_time_reason="Half marathon training needs time to build endurance safely",
        excessive_time_reason="Half marathon training beyond 20 weeks may cause fatigue",
    ),
    30.0: DistanceConstraints(
        min_weeks=settings.min_weeks_30k,
        max_weeks=settings.max_weeks_30k,
        min_mileage=settings.min_mileage_30k,
        max_mileage=settings.max_mileage_30k,
        low_mileage_msg=settings.low_mileage_msg_30k,
        high_mileage_msg=settings.high_mileage_msg_30k,
    ),
    42.2: DistanceConstraints(
        min_weeks=settings.min_weeks_marathon,
        max_weeks=settings.max_weeks_marathon,
        min_mileage=settings.min_mileage_marathon,
        max_mileage=settings.max_mileage_marathon,
        low_mileage_msg=settings.low_mileage_msg_marathon,
        high_mileage_msg=settings.high_mileage_msg_marathon,
        perf_min_mileage=settings.perf_min_mileage_marathon,
        insufficient_time_reason="Marathon training requires adequate time to prevent injury",
        excessive_time_reason="24 weeks is the maximum recommended for marathon training",
    ),
}


def get_constraints(distance_km: float) -> Optional[DistanceConstraints]:
    """Return the constraints for a target distance, or None if unsupported."""
    return DISTANCE_CONSTRAINTS.get(distance_km)
