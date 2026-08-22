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

# Trail / ultra hard ceilings by bracket. The single long run plateaus at
# ~38 km even for 100-mile prep — the rest of the long-day volume goes into
# back-to-back doubles, not a single 50 km grind.
_TRAIL_HARD_CEILINGS: Dict[str, float] = {
    "short": 20.0,
    "standard": 32.0,
    "ultra": 36.0,
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
        return week_number - phases["base"] - phases["build"] - phases["peak"] - 1


def training_km(week: Dict) -> float:
    """Weekly volume excluding race day — the week's *training* load.

    ``week["total_km"]`` is the honest total: on race week it includes the
    race, because the runner does cover that ground. But every progression
    rule in the plan — the 10 % cap, the taper drawdown, deload ratios —
    is about training load, and a marathon dropped into the final week
    would make race week look like a 60 % spike on top of a taper.

    Use this wherever a week's volume is being compared to another week's;
    use ``total_km`` wherever the number is being shown to the runner.
    """
    return round(
        sum(
            w.get("distance", 0) or 0
            for w in week.get("daily_workouts", [])
            if w.get("type") != "race"
        ),
        1,
    )
