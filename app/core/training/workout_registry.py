"""Single source of truth for plan workout types and their builders.

Adding a new plan-builder workout type means:

1. Adding a builder function in ``workout_builders``.
2. Adding a ``WorkoutTypeSpec`` entry below.
3. Updating ``workout_distribution`` if the type participates in scheduling.

Run-log-only labels (race, vo2max variants, time trial, …) live in
``LOG_ONLY_TYPES`` — those are produced by ``overlay_key_workout`` or by users
when classifying logged runs, and never need a builder of their own.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

from app.core.training import workout_builders


class WorkoutBuilder(Protocol):
    """Callable signature shared by every plan-builder workout type.

    Builders accept the full per-day context as keyword arguments and may
    ignore fields they don't need (rest days don't read ``distance`` etc.).
    """

    def __call__(
        self,
        *,
        day: int,
        distance: float,
        total_km: float,
        phase: str,
        pace_zones: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]: ...


@dataclass(frozen=True)
class WorkoutTypeSpec:
    name: str
    intensity: str
    description: str
    builder: WorkoutBuilder


def _build_rest(*, day: int, **_: Any) -> Dict[str, Any]:
    return workout_builders.generate_rest_day(day)


def _build_recovery(*, day: int, phase: str, **_: Any) -> Dict[str, Any]:
    return workout_builders.generate_recovery_day(day, phase)


def _build_long(
    *,
    day: int,
    distance: float,
    total_km: float,
    pace_zones: Optional[Dict[str, Any]],
    **_: Any,
) -> Dict[str, Any]:
    return workout_builders.generate_long_run(
        day, distance, total_km, pace_zones=pace_zones
    )


def _build_easy(
    *,
    day: int,
    distance: float,
    total_km: float,
    pace_zones: Optional[Dict[str, Any]],
    **_: Any,
) -> Dict[str, Any]:
    return workout_builders.generate_easy_run(
        day, distance, total_km, pace_zones=pace_zones
    )


def _build_tempo(
    *,
    day: int,
    distance: float,
    total_km: float,
    pace_zones: Optional[Dict[str, Any]],
    **_: Any,
) -> Dict[str, Any]:
    return workout_builders.generate_tempo_run(
        day, distance, total_km, pace_zones=pace_zones
    )


def _build_interval(
    *,
    day: int,
    distance: float,
    total_km: float,
    pace_zones: Optional[Dict[str, Any]],
    **_: Any,
) -> Dict[str, Any]:
    return workout_builders.generate_interval_run(
        day, distance, total_km, pace_zones=pace_zones
    )


def _build_hill(*, day: int, distance: float, **_: Any) -> Dict[str, Any]:
    return workout_builders.generate_hill_workout(day, distance)


WORKOUT_REGISTRY: Dict[str, WorkoutTypeSpec] = {
    "rest": WorkoutTypeSpec("rest", "rest", "Rest day", _build_rest),
    "recovery": WorkoutTypeSpec(
        "recovery", "very_low", "Active recovery", _build_recovery
    ),
    "easy": WorkoutTypeSpec("easy", "low", "Easy recovery run", _build_easy),
    "long": WorkoutTypeSpec("long", "medium", "Long distance run", _build_long),
    "tempo": WorkoutTypeSpec(
        "tempo", "medium", "Tempo run at threshold pace", _build_tempo
    ),
    "interval": WorkoutTypeSpec(
        "interval", "high", "High-intensity intervals", _build_interval
    ),
    "hill": WorkoutTypeSpec(
        "hill", "high", "Hill repeats and strength training", _build_hill
    ),
}

# Labels that may appear on ``RunLog.workout_type`` but are not produced by the
# day-level builder dispatch — they come from key-workout overlays (vo2max,
# fartlek, …) or describe user-logged race / time-trial efforts.
LOG_ONLY_TYPES: Tuple[str, ...] = (
    "race",
    "vo2max",
    "vo2max_ladder",
    "cruise_interval",
    "fartlek",
    "time_trial",
    "race_pace",
)

ALL_WORKOUT_TYPE_NAMES: List[str] = [*WORKOUT_REGISTRY.keys(), *LOG_ONLY_TYPES]


def build_workout(
    workout_type: str,
    *,
    day: int,
    distance: float,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Dispatch to the registered builder for ``workout_type``."""
    spec = WORKOUT_REGISTRY.get(workout_type)
    if spec is None:
        raise ValueError(f"Unknown workout_type: {workout_type}")
    return spec.builder(
        day=day,
        distance=distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
    )
