"""Race-specific key workout library.

Curated workouts that replace generic interval/tempo sessions during Build and
Peak phases to make training plans feel coached, not generated.

Split by concern:
    rewrites  — distance-driven prose/structure rewrites + reconciliation
    builders  — step builders + the per-workout builder registry
    selection — candidate filtering, bracket gating, KeyWorkoutLibrary, overlay

The names below are re-exported so callers keep importing from
``app.core.training.key_workout_library`` unchanged.
"""

from app.core.training.key_workout_library.builders import (
    _KEY_WORKOUT_STEP_BUILDERS,
    _RUNNING_DISTANCE_FRACTION,
    build_key_workout_steps,
    rebuild_key_workout,
)
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _STRUCTURE_REWRITES,
    _derive_structure,
    _fartlek_reps,
    _mp_cutdown_reps,
    _proprioception_circuit_cadence,
    _pyramid_pattern,
    _rewrite_key_workout_description,
    _vo2max_400_reps,
    _wu_cd,
    _yasso_800_reps,
    reconcile_key_workout_text,
)
from app.core.training.key_workout_library.selection import (
    _BRACKET_RESTRICTIONS,
    _ITW_ONLY_IDS,
    _KEY_WORKOUT_MIN_DISTANCE_KM,
    _LONG_ULTRA_NIGHT_RUN,
    _WORKOUTS,
    KeyWorkoutLibrary,
    overlay_key_workout,
)

__all__ = [
    "KeyWorkoutLibrary",
    "overlay_key_workout",
    "build_key_workout_steps",
    "rebuild_key_workout",
    "reconcile_key_workout_text",
    # Tables / helpers re-exported for cross-module and test use.
    "_WORKOUTS",
    "_DISTANCE_REWRITES",
    "_STRUCTURE_REWRITES",
    "_KEY_WORKOUT_STEP_BUILDERS",
    "_KEY_WORKOUT_MIN_DISTANCE_KM",
    "_RUNNING_DISTANCE_FRACTION",
    "_LONG_ULTRA_NIGHT_RUN",
    "_BRACKET_RESTRICTIONS",
    "_ITW_ONLY_IDS",
    "_rewrite_key_workout_description",
    "_derive_structure",
    "_wu_cd",
    "_vo2max_400_reps",
    "_yasso_800_reps",
    "_mp_cutdown_reps",
    "_pyramid_pattern",
    "_fartlek_reps",
    "_proprioception_circuit_cadence",
]
