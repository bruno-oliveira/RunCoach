"""Shared constants for the RunCoach application.

Race distances are sourced from the ``DISTANCE_CONSTRAINTS`` registry in
``app.core.training.training_config`` — adding a new race distance means
adding one entry there, and the supported-distance list / display-name map
fall out automatically.
"""

from app.core.training.training_config import DISTANCE_CONSTRAINTS
from app.core.training.workout_registry import (
    ALL_WORKOUT_TYPE_NAMES as _ALL_WORKOUT_TYPE_NAMES,
)

# Supported race distances in km, derived from the constraints registry.
SUPPORTED_DISTANCES: list[float] = list(DISTANCE_CONSTRAINTS.keys())

# Display name per distance, derived from the same source.
DISTANCE_NAMES: dict[float, str] = {
    km: cfg.name for km, cfg in DISTANCE_CONSTRAINTS.items()
}

# Valid workout types emitted by the plan generator and accepted by run logging.
# Sourced from the workout registry so adding a new type is one-place.
WORKOUT_TYPES: list[str] = list(_ALL_WORKOUT_TYPE_NAMES)
