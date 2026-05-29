"""Phase-periodized, experience-adapted strength training for running plans.

Pure logic — no DB, no I/O. Exercise templates and focus rotations live in
``strength_data`` and are re-exported here for backward-compatible imports.
"""

from typing import Any, Dict, List

from app.core.training.strength_data import (
    _EXERCISES,
    _PHASE_MODIFIERS,
    PHASE_FOCUS_ROTATIONS,
    TRAIL_FOCUS_ROTATIONS,
    TRAIL_ROTATIONS_BY_ELEVATION,
)
from app.core.training.trail_profile import is_trail_target

# ---------------------------------------------------------------------------
# Experience level derivation
# ---------------------------------------------------------------------------


def derive_experience_level(current_km: float) -> str:
    """Derive runner experience level from current weekly mileage."""
    if current_km < 20:
        return "beginner"
    if current_km < 40:
        return "intermediate"
    return "advanced"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_phase_focus_rotation(
    phase: str,
    target_distance: float = 0.0,
    trail_profile=None,
) -> List[str]:
    """Return the ordered focus list for a training phase.

    Trail / ultra plans dispatch to a per-elevation-class rotation: flat
    trails get extra plyometric work to replace the missing hill stimulus;
    mountainous routes get stability + plyometric every phase. Falls back
    to the "build" rotation for unknown phases.
    """
    if trail_profile is not None:
        rotations = TRAIL_ROTATIONS_BY_ELEVATION[trail_profile.elevation_class]
        return rotations.get(phase, rotations["build"])
    if is_trail_target(target_distance, trail_profile):
        return TRAIL_FOCUS_ROTATIONS.get(phase, TRAIL_FOCUS_ROTATIONS["build"])
    return PHASE_FOCUS_ROTATIONS.get(phase, PHASE_FOCUS_ROTATIONS["build"])


def generate_strength_session(
    focus: str,
    phase: str,
    level: str,
    week_number: int,
) -> Dict[str, Any]:
    """Build a strength session dict for embedding into a weekly plan.

    Args:
        focus: "lower_body", "core", or "full_body"
        phase: Training phase — "base", "build", "peak", "taper"
        level: "beginner", "intermediate", or "advanced"
        week_number: 1-indexed week number (unused today but available for
                     future per-week exercise rotation)

    Returns:
        Session dict with keys: type, focus, phase, level, duration,
        warm_up, exercises, cool_down.
    """
    template = _EXERCISES.get(focus, _EXERCISES["full_body"]).get(
        level, _EXERCISES["full_body"]["beginner"]
    )
    modifier = _PHASE_MODIFIERS.get(phase, _PHASE_MODIFIERS["build"])

    # Deep-copy exercises so callers can't mutate the template
    exercises = []
    for ex in template["exercises"]:
        adjusted_sets = max(2, ex["sets"] + modifier["sets_delta"])
        entry: Dict[str, Any] = {
            "name": ex["name"],
            "sets": adjusted_sets,
            "reps": ex["reps"],
        }
        exercises.append(entry)

    # Build duration string with modifier
    duration = template["base_duration"]
    if modifier["duration_delta"]:
        # Parse "25-35 min" → adjust both bounds
        parts = duration.replace(" min", "").split("-")
        if len(parts) == 2:
            lo = max(10, int(parts[0]) + modifier["duration_delta"])
            hi = max(lo + 5, int(parts[1]) + modifier["duration_delta"])
            duration = f"{lo}-{hi} min"

    session: Dict[str, Any] = {
        "type": focus,
        "focus": focus,
        "phase": phase,
        "level": level,
        "duration": duration,
        "warm_up": list(template["warm_up"]),
        "exercises": exercises,
        "cool_down": list(template["cool_down"]),
    }

    if modifier["note"]:
        session["note"] = modifier["note"]

    return session
