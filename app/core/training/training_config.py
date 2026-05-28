"""Per-distance training constraints and messages.

Single source of truth for the bracket of weeks, mileage thresholds, and
user-facing guidance keyed by target distance (km). New code should depend
on this registry rather than the (now removed) flat ``settings.min_weeks_*``
fields.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class DistanceConstraints:
    """Bracket of weeks, mileage, and guidance for a single target distance."""

    name: str
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
        name="5K",
        min_weeks=6,
        max_weeks=16,
        min_mileage=5.0,
        max_mileage=40,
        low_mileage_msg=(
            "Your current mileage is quite low for 5K training. "
            "Consider building a base with 2-3 weeks of easy running first."
        ),
        high_mileage_msg=(
            "You're already running high mileage for 5K. "
            "Consider focusing on speed work rather than volume."
        ),
        perf_min_mileage=20,
        insufficient_time_reason="4 weeks provides a solid foundation for 5K improvement",
        excessive_time_reason="Training beyond 16 weeks for 5K can lead to burnout",
    ),
    10.0: DistanceConstraints(
        name="10K",
        min_weeks=6,
        max_weeks=16,
        min_mileage=10.0,
        max_mileage=50,
        low_mileage_msg=(
            "Your current mileage may be insufficient for 10K training. "
            "Build to at least 10km/week for 2-3 weeks first."
        ),
        high_mileage_msg=(
            "High mileage for 10K. "
            "You might benefit from focusing on quality over quantity."
        ),
        perf_min_mileage=25,
        insufficient_time_reason="6 weeks allows for proper 10K preparation",
        excessive_time_reason="16 weeks is optimal for 10K preparation",
    ),
    21.1: DistanceConstraints(
        name="Half Marathon",
        min_weeks=8,
        max_weeks=20,
        min_mileage=15.0,
        max_mileage=70,
        low_mileage_msg=(
            "Half marathon training requires a stronger base. "
            "Build to 15km/week for 3-4 weeks before starting."
        ),
        high_mileage_msg=(
            "Very high mileage for half marathon. "
            "Ensure adequate recovery and consider periodization."
        ),
        perf_min_mileage=35,
        insufficient_time_reason="Half marathon training needs time to build endurance safely",
        excessive_time_reason="Half marathon training beyond 20 weeks may cause fatigue",
    ),
    30.0: DistanceConstraints(
        name="Trail Running",
        min_weeks=6,
        max_weeks=20,
        min_mileage=15.0,
        max_mileage=60,
        low_mileage_msg=(
            "Trail running requires a solid base. "
            "Build to 15km/week with some trail experience first."
        ),
        high_mileage_msg=(
            "High mileage for trail running. "
            "Focus on time on feet rather than distance."
        ),
    ),
    42.2: DistanceConstraints(
        name="Marathon",
        min_weeks=12,
        max_weeks=24,
        min_mileage=25.0,
        max_mileage=100,
        low_mileage_msg=(
            "Marathon training requires significant base fitness. "
            "Build to 25km/week for 4-6 weeks before beginning."
        ),
        high_mileage_msg=(
            "Extremely high mileage. "
            "Be cautious about injury risk and ensure proper recovery."
        ),
        perf_min_mileage=50,
        insufficient_time_reason="Marathon training requires adequate time to prevent injury",
        excessive_time_reason="24 weeks is the maximum recommended for marathon training",
    ),
}


def get_constraints(distance_km: float) -> Optional[DistanceConstraints]:
    """Return the constraints for a target distance, or None if unsupported."""
    return DISTANCE_CONSTRAINTS.get(distance_km)
