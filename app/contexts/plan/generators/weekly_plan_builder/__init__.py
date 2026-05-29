"""Weekly plan builder.

Handles distance budgeting, scaling, fill-up, and ceiling enforcement for a
single week of training. Split into ``budget`` (leaf helpers), ``intensive_
weekend`` (ITW reshaping), and ``orchestrator`` (assembly). Names are
re-exported so callers import from this package unchanged.
"""

from app.contexts.plan.generators.weekly_plan_builder.budget import (
    _DEFAULT_PACE_MIN_PER_KM,
    _DURATION_HINT_THRESHOLD_KM,
    _PACE_ZONE_FOR_TYPE,
    _QUALITY_DEMOTE_THRESHOLD_KM,
    _pace_for_type,
    allocate_easy_distances,
    apply_quality_caps,
    attach_duration_hints,
    build_workout_for_type,
    resolve_low_budget_quality,
)
from app.contexts.plan.generators.weekly_plan_builder.intensive_weekend import (
    apply_intensive_weekend,
)
from app.contexts.plan.generators.weekly_plan_builder.orchestrator import (
    _vertical_simulation_targets,
    build_weekly_plan,
    generate_daily_workouts,
)

__all__ = [
    "build_weekly_plan",
    "generate_daily_workouts",
    "apply_intensive_weekend",
    "attach_duration_hints",
    "resolve_low_budget_quality",
    "apply_quality_caps",
    "allocate_easy_distances",
    "build_workout_for_type",
    "_pace_for_type",
    "_vertical_simulation_targets",
    "_QUALITY_DEMOTE_THRESHOLD_KM",
    "_DURATION_HINT_THRESHOLD_KM",
    "_PACE_ZONE_FOR_TYPE",
    "_DEFAULT_PACE_MIN_PER_KM",
]
