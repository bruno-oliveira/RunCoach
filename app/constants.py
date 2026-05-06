"""Shared constants for the RunCoach application."""

# Supported race distances in km.
# Add new distances here; validators, generators, and templates reference this list.
SUPPORTED_DISTANCES: list[float] = [5.0, 10.0, 21.1, 30.0, 42.2]

DISTANCE_NAMES: dict[float, str] = {
    5.0: "5K",
    10.0: "10K",
    21.1: "Half Marathon",
    30.0: "Trail Running",
    42.2: "Marathon",
}

# Valid workout types emitted by the plan generator and accepted by run logging.
# Sourced from the workout registry so adding a new type is one-place.
from app.core.training.workout_registry import ALL_WORKOUT_TYPE_NAMES as _ALL_WORKOUT_TYPE_NAMES

WORKOUT_TYPES: list[str] = list(_ALL_WORKOUT_TYPE_NAMES)
