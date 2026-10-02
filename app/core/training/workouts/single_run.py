"""Build one workout on its own, with no training plan around it.

Every other builder in this package is called by a plan generator that already
knows the week: its volume, its phase, which day it is. A single run has none
of that — just "a tempo, about 8 km, today". This module is the thin layer that
supplies the missing context so the *same* builders produce the session, which
keeps a one-off tempo identical in structure and pacing to a planned one.

Two things a plan would otherwise decide are pinned here:

* **The variant.** The builders rotate flavours by day number (strides on one
  easy day, cruise intervals on one tempo day). A runner asking for "a tempo"
  means the canonical one, so each type maps to the day index that yields it.
* **The range.** Inside a plan the periodiser never asks for a 2 km interval
  session or a 15 km threshold block. Here the runner types the number, so each
  type carries the shortest distance at which its structure is still honest (a
  warm-up, real work, a cool-down), and quality sessions take the plan
  generator's own default quality caps as their ceiling.
"""

from typing import Any, Callable, Dict, Optional

from app.core.training.tuning import DEFAULT_QUALITY_CAPS
from app.core.training.workouts import workout_builders
from app.core.training.workouts.workout_steps.intervals_export import (
    build_intervals_workout,
)

PaceZones = Optional[Dict[str, Any]]
_Builder = Callable[[int, float, float, PaceZones], Dict[str, Any]]

# Ceiling for the aerobic types; quality types are capped tighter below.
MAX_DISTANCE_KM = 50.0

# type -> (builder, day index selecting the canonical variant, name, floor km)
_SPEC: Dict[str, tuple[_Builder, int, str, float]] = {
    "easy": (workout_builders.generate_easy_run, 2, "Easy Run", 2.0),
    "tempo": (workout_builders.generate_tempo_run, 0, "Tempo Run", 4.0),
    "interval": (workout_builders.generate_interval_run, 0, "Intervals", 5.0),
    "long": (workout_builders.generate_long_run, 0, "Long Run", 8.0),
}

SINGLE_RUN_TYPES = tuple(_SPEC)

# Plan and inferred workout types, folded onto the four a single run can be.
# Used to tell a single run apart from a planned session on the same day: a
# "cruise_interval" in the plan and a "tempo" single run are the same kind of
# effort, a "recovery" jog and a "tempo" are not. Types with no clear family
# (hill, fartlek, race) are left out and compare as unknown.
_FAMILY: Dict[str, str] = {
    "easy": "easy",
    "recovery": "easy",
    "long": "long",
    "medium_long": "long",
    "tempo": "tempo",
    "cruise_interval": "tempo",
    "interval": "interval",
    "vo2max": "interval",
    "vo2max_ladder": "interval",
}

# Two distances are "the same session" within this share of the prescribed
# one (or the absolute floor, for short sessions). Wide enough for a session
# cut short or run long, narrow enough that an unrelated 20 km long run is not
# mistaken for a 6 km tempo.
SIMILAR_DISTANCE_SHARE = 0.4
SIMILAR_DISTANCE_MIN_KM = 1.5

# Duration requests are solved by building, timing and rescaling. The step
# builders snap to whole reps and 100 m, so this converges in a pass or two;
# the cap only guards against a pathological oscillation.
_DURATION_PASSES = 4


def single_run_family(workout_type: Optional[str]) -> Optional[str]:
    """The single-run type a workout type belongs to, or None if unclear."""
    return _FAMILY.get(workout_type or "")


def is_similar_distance(prescribed_km: float, other_km: float) -> bool:
    """Whether ``other_km`` could plausibly be the ``prescribed_km`` session."""
    tolerance = max(SIMILAR_DISTANCE_MIN_KM, prescribed_km * SIMILAR_DISTANCE_SHARE)
    return abs(other_km - prescribed_km) <= tolerance


def min_distance_km(run_type: str) -> float:
    """Shortest distance at which ``run_type`` still has its real structure."""
    return _SPEC[run_type][3]


def max_distance_km(run_type: str) -> float:
    """Longest sensible session of ``run_type`` outside a plan's progression."""
    return float(DEFAULT_QUALITY_CAPS.get(run_type, MAX_DISTANCE_KM))


def build_single_run(
    run_type: str,
    distance_km: float,
    pace_zones: PaceZones,
    weekly_km: float,
) -> Dict[str, Any]:
    """Build a standalone workout as a ``plan_data``-shaped day dict.

    Args:
        run_type: One of ``SINGLE_RUN_TYPES``.
        distance_km: Requested total distance. The result's ``distance`` is
            what the steps actually cover, which can differ slightly for
            interval sessions (whole reps).
        pace_zones: ``VDOTCalculator.get_pace_zones`` output, or None when the
            runner has no fitness on record — the session is then described by
            effort.
        weekly_km: The runner's recent weekly volume. The interval builder
            gates its longer reps on it, exactly as it does inside a plan.

    Raises:
        ValueError: Unknown type, or a distance outside the type's range.
    """
    if run_type not in _SPEC:
        raise ValueError(f"Unknown single run type: {run_type}")
    builder, day, name, floor = _SPEC[run_type]
    ceiling = max_distance_km(run_type)
    if distance_km < floor or distance_km > ceiling:
        raise ValueError(f"{name} must be between {floor:g} and {ceiling:g} km")

    workout = builder(day, round(distance_km, 1), weekly_km, pace_zones)
    # `day` is a position in a plan week; a single run has no week.
    workout.pop("day", None)
    workout["key_workout_name"] = name
    return workout


def estimated_minutes(workout: Dict[str, Any]) -> Optional[int]:
    """Estimated moving time, or None when the session has no real paces.

    Without pace zones the exporter prices steps at generic fallback paces.
    Those are fine as a watch alert floor but are not this runner's, so no
    duration is claimed from them.
    """
    steps = workout.get("steps") or []
    if not any(step.get("pace_str") for step in steps):
        return None
    try:
        seconds = build_intervals_workout(workout)["moving_time"]
    except ValueError:
        return None
    return int(round(seconds / 60.0)) if seconds else None


def distance_for_duration(
    run_type: str,
    minutes: float,
    pace_zones: Dict[str, Any],
    weekly_km: float,
) -> float:
    """The distance whose session of ``run_type`` takes about ``minutes``.

    Solved against the real builder rather than a pace guess, so warm-ups,
    recoveries and faster work segments are all priced the way the session
    will actually be run.

    Raises:
        ValueError: The duration is too short for the type's shortest session
            or longer than the longest one.
    """
    if run_type not in _SPEC:
        raise ValueError(f"Unknown single run type: {run_type}")
    floor, ceiling = min_distance_km(run_type), max_distance_km(run_type)
    easy = pace_zones["E"]
    easy_pace = (easy["pace_min_km_slow"] + easy["pace_min_km_fast"]) / 2.0
    distance = minutes / easy_pace

    for _ in range(_DURATION_PASSES):
        clamped = min(max(distance, floor), ceiling)
        took = estimated_minutes(
            build_single_run(run_type, clamped, pace_zones, weekly_km)
        )
        if not took:
            break
        distance = clamped * minutes / took
        if abs(took - minutes) <= 1:
            break

    distance = round(distance, 1)
    if distance < floor or distance > ceiling:
        name = _SPEC[run_type][2]
        raise ValueError(
            f"{minutes:g} minutes is outside what a {name.lower()} can be "
            f"({floor:g}-{ceiling:g} km at your paces)"
        )
    return distance
