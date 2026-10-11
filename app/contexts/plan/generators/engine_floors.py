"""Engine-level input floors: the inputs the generator refuses to plan from.

``PlanRequest`` enforces these for web traffic, but the generator is also
called directly (backtests, scripts, future endpoints). The sweep that
motivated these guards produced a +21 % ramp breach and a 0.0 km easy card on
a *loading* week from a base the schema would have refused — below-floor
inputs don't just make conservative plans, they compose into broken ones.

Each discipline states its own floor (road reads the ``DISTANCE_CONSTRAINTS``
registry, trail its bracket, backyard its tier), and all of them raise the
same domain exceptions the schema raises rather than inventing a second
vocabulary for the same refusal.
"""

from typing import Optional

from app.core.training.profiles.backyard_profile import (
    BackyardProfile,
    backyard_max_weeks,
    backyard_min_weekly_km,
    backyard_min_weeks,
)
from app.core.training.profiles.trail_profile import (
    TRAIL_SENTINEL_KM,
    TrailProfile,
    trail_min_weekly_mileage,
    trail_min_weeks,
)
from app.core.training.training_config import DISTANCE_CONSTRAINTS, get_constraints
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ValidationException,
)


def enforce_engine_floors(
    current_km: float,
    target_distance: float,
    weeks: int,
    trail_profile: Optional[TrailProfile],
    backyard_profile: Optional[BackyardProfile],
) -> None:
    """Raise the domain exception for inputs no sound plan can be built from.

    A backyard plan always carries a trail profile too (the ultra it projects
    onto), so the backyard floor is checked before the trail one.
    """
    if backyard_profile is not None:
        _enforce_backyard_floors(current_km, weeks, backyard_profile)
    elif trail_profile is not None:
        _enforce_trail_floors(current_km, weeks, trail_profile)
    else:
        _enforce_road_floors(current_km, target_distance, weeks)


def _enforce_road_floors(current_km: float, target_distance: float, weeks: int) -> None:
    constraints = get_constraints(target_distance)
    if constraints is None:
        # 30.0 never reaches here: the legacy sentinel is promoted to a trail
        # profile before the floors are checked.
        road_names = ", ".join(
            c.name for d, c in DISTANCE_CONSTRAINTS.items() if d != TRAIL_SENTINEL_KM
        )
        raise ValidationException(
            f"Unsupported road target distance: {target_distance} km",
            user_message=(
                "Please select a valid distance: "
                f"{road_names}, or pick Trail/Ultra for a custom goal."
            ),
        )
    if current_km < constraints.min_mileage:
        raise InadequateBaseException(
            f"Current mileage ({current_km:g} km/week) is below the "
            f"recommended minimum ({constraints.min_mileage:g} km/week) "
            f"for {constraints.name} training",
            suggestion=constraints.low_mileage_msg,
        )
    if weeks < constraints.min_weeks:
        raise InsufficientTimeException(
            f"Training for {constraints.name} requires at least "
            f"{constraints.min_weeks} weeks",
            suggestion=(
                f"Consider extending your training to "
                f"{constraints.min_weeks} weeks. "
                f"{constraints.insufficient_time_reason}"
            ),
        )
    if weeks > constraints.max_weeks:
        raise ValidationException(
            f"{constraints.name} plans are capped at "
            f"{constraints.max_weeks} weeks; requested {weeks}",
            user_message=(
                f"{constraints.excessive_time_reason}. "
                "Consider a shorter training period."
            ),
        )
    # NOTE: runs-per-week floors (HM ≥ 3, marathon ≥ 4) are *product policy*
    # and stay schema-only. The engine is deliberately permissive here — it
    # composes gracefully at 2-3 runs (the frequency composers, the envelope
    # grid, and the physiological envelope ledger all exercise that space) —
    # so refusing would break the engine's contract, not protect it.


def _enforce_backyard_floors(
    current_km: float, weeks: int, backyard_profile: BackyardProfile
) -> None:
    min_km = backyard_min_weekly_km(backyard_profile)
    if current_km < min_km:
        raise InadequateBaseException(
            f"Current mileage ({current_km:g} km/week) is below the "
            f"recommended minimum ({min_km:g} km/week) for a "
            f"{backyard_profile.target_loops}-loop goal",
            suggestion=(
                "Build a steady base of easy running first — a backyard "
                "asks you to repeat a loop you're already comfortable "
                "with, not to discover one."
            ),
        )
    min_w = backyard_min_weeks(backyard_profile)
    max_w = backyard_max_weeks(backyard_profile)
    if weeks < min_w:
        raise InsufficientTimeException(
            f"Training for {backyard_profile.target_loops} loops requires "
            f"at least {min_w} weeks",
            suggestion=(
                f"This goal needs {min_w}–{max_w} weeks to build the "
                "aerobic base, the loop-pace habit, and enough "
                "simulations to rehearse the format."
            ),
        )


def _enforce_trail_floors(
    current_km: float, weeks: int, trail_profile: TrailProfile
) -> None:
    min_km = trail_min_weekly_mileage(trail_profile)
    if current_km < min_km:
        raise InadequateBaseException(
            f"Current mileage ({current_km:g} km/week) is below the "
            f"recommended minimum ({min_km:g} km/week) for a "
            f"{trail_profile.distance_km:g} km trail/ultra",
            suggestion=(
                "Build a steady base of easy running first — "
                "trail-specific volume and elevation work compounds "
                "the load quickly."
            ),
        )
    if weeks < trail_min_weeks(trail_profile):
        raise InsufficientTimeException(
            f"Training for a {trail_profile.distance_km:g} km trail/ultra "
            f"requires at least {trail_min_weeks(trail_profile)} weeks",
            suggestion=(
                "This bracket needs time to build trail-specific "
                "strength, time-on-feet, and fueling habits."
            ),
        )
