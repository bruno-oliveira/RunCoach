"""Shared training constants used across plan generation modules."""

from typing import Dict

LONG_RUN_HARD_CEILINGS: Dict[float, float] = {
    5.0: 14.0,
    10.0: 22.0,
    21.1: 24.0,
    30.0: 30.0,
    42.2: 40.0,
}

DEFAULT_HARD_CEILING_RATIO = 0.9


def get_hard_ceiling(target_distance: float) -> float:
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
