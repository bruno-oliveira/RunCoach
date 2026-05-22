"""Shared quality cap enforcement for plan generation and adaptation.

Both the initial plan generator and the adaptation adjuster need to enforce
the same structural constraints. This module provides the single source of
truth for those caps.
"""

from typing import Dict, List, Optional

# Quality workouts (tempo/interval/hill) may not exceed this fraction of the
# long run distance.
MAX_QUALITY_VS_LONG_RUN = 0.85

# Individual easy runs may not exceed this fraction of the long run distance.
MAX_EASY_VS_LONG_RUN = 0.95

# Base phase reduces quality caps by this factor.
BASE_PHASE_QUALITY_REDUCTION = 0.80

# Distance-scaled physiological quality caps (km).
QUALITY_CAPS_BY_DISTANCE = {
    5.0: {"tempo": 6.0, "interval": 5.0, "hill": 5.0},
    10.0: {"tempo": 10.0, "interval": 8.0, "hill": 6.0},
    21.1: {"tempo": 14.0, "interval": 10.0, "hill": 8.0},
    30.0: {"tempo": 12.0, "interval": 8.0, "hill": 12.0},
    42.2: {"tempo": 18.0, "interval": 12.0, "hill": 10.0},
}
DEFAULT_QUALITY_CAPS = {"tempo": 12.0, "interval": 10.0, "hill": 8.0}


def get_quality_caps(target_distance: float, phase: str) -> Dict[str, float]:
    """Distance-scaled physiological caps for quality workout distances (km)."""
    caps = QUALITY_CAPS_BY_DISTANCE.get(target_distance, DEFAULT_QUALITY_CAPS)
    if phase == "base":
        return {k: round(v * BASE_PHASE_QUALITY_REDUCTION, 1) for k, v in caps.items()}
    return dict(caps)


def cap_quality_distance(
    distance: float,
    long_run_distance: float,
    workout_type: str,
    target_distance: float,
    phase: str,
) -> float:
    """Cap a single quality workout distance against structural limits."""
    ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
    phys_caps = get_quality_caps(target_distance, phase)
    cap = min(ceiling, phys_caps.get(workout_type, ceiling))
    return min(distance, round(cap, 1))


def cap_easy_distance(distance: float, long_run_distance: float) -> float:
    """Cap a single easy run distance against the long run."""
    max_easy = long_run_distance * MAX_EASY_VS_LONG_RUN
    return min(distance, round(max_easy, 1))


def enforce_week_caps(workouts: List, target_distance: float, phase: str) -> bool:
    """Enforce quality and easy caps on a list of workouts (in place).

    Works with both plan_data workout dicts (with 'type' and 'distance' keys)
    and DailyWorkout ORM objects (with 'workout_type' and 'distance_km' attrs).

    Key workouts are skipped: their distance is the prescription. Capping
    them silently would leave the cached description and steps describing a
    different session than the runner is told to do. If a key workout's
    distance breaches a cap, that is a planning bug to surface, not to mask.

    Returns True if any distance was capped.
    """
    long_run_distance = _find_long_run_distance(workouts)
    if long_run_distance <= 0:
        return False

    any_capped = False
    quality_types = ("tempo", "interval", "hill", "vo2max", "race_pace", "fartlek")

    for workout in workouts:
        if _has_key_workout_id(workout):
            continue
        wtype = _get_type(workout)
        dist = _get_distance(workout)
        if not dist or dist <= 0:
            continue

        if wtype in quality_types:
            capped = cap_quality_distance(
                dist, long_run_distance, wtype, target_distance, phase
            )
            if capped < dist:
                _set_distance(workout, capped)
                any_capped = True
        elif wtype == "easy":
            capped = cap_easy_distance(dist, long_run_distance)
            if capped < dist:
                _set_distance(workout, capped)
                any_capped = True

    return any_capped


def _has_key_workout_id(workout) -> bool:
    """True if this workout carries a prescriptive key-workout overlay."""
    if hasattr(workout, "key_workout_id"):
        return bool(getattr(workout, "key_workout_id", None))
    if isinstance(workout, dict):
        return bool(workout.get("key_workout_id"))
    return False


def _find_long_run_distance(workouts: List) -> float:
    """Find the long run distance in a week's workouts."""
    for w in workouts:
        if _get_type(w) == "long":
            return _get_distance(w) or 0.0
    return 0.0


def _get_type(workout) -> str:
    """Get workout type from either a dict or ORM object."""
    if hasattr(workout, "workout_type"):
        return workout.workout_type or ""
    return workout.get("type", workout.get("workout_type", ""))


def _get_distance(workout) -> Optional[float]:
    """Get distance from either a dict or ORM object."""
    if hasattr(workout, "distance_km"):
        return workout.distance_km
    return workout.get("distance", workout.get("distance_km"))


def _set_distance(workout, value: float) -> None:
    """Set distance on either a dict or ORM object."""
    if hasattr(workout, "distance_km"):
        workout.distance_km = round(value, 1)
    elif "distance_km" in workout:
        workout["distance_km"] = round(value, 1)
    else:
        workout["distance"] = round(value, 1)
