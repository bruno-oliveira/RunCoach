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
WORKOUT_TYPES: list[str] = [
    "easy",
    "tempo",
    "interval",
    "long",
    "hill",
    "rest",
    "recovery",
    "race",
    "strength",
]
