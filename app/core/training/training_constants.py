"""Shared training constants used across plan generation modules."""

from typing import Dict, Optional

LONG_RUN_HARD_CEILINGS: Dict[float, float] = {
    5.0: 14.0,
    10.0: 22.0,
    21.1: 24.0,
    30.0: 30.0,
    42.2: 40.0,
}

DEFAULT_HARD_CEILING_RATIO = 0.9

# Trail / ultra hard ceilings by bracket. The single long run plateaus at
# ~38 km even for 100-mile prep — the rest of the long-day volume goes into
# back-to-back doubles, not a single 50 km grind.
_TRAIL_HARD_CEILINGS: Dict[str, float] = {
    "short":      20.0,
    "standard":   32.0,
    "ultra":      36.0,
    "long_ultra": 38.0,
}


def get_hard_ceiling(target_distance: float, trail_profile=None) -> float:
    if trail_profile is not None:
        return _TRAIL_HARD_CEILINGS[trail_profile.bracket]
    return LONG_RUN_HARD_CEILINGS.get(
        target_distance, target_distance * DEFAULT_HARD_CEILING_RATIO
    )


def calculate_week_in_phase(
    week_number: int, phase: str, phases: Dict[str, int]
) -> int:
    if phase == "base":
        return week_number - 1
    elif phase == "build":
        return week_number - phases["base"] - 1
    elif phase == "peak":
        return week_number - phases["base"] - phases["build"] - 1
    else:
        return (
            week_number
            - phases["base"]
            - phases["build"]
            - phases["peak"]
            - 1
        )
