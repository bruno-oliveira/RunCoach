"""Weekly plan builder.

Handles distance budgeting, scaling, fill-up, and ceiling enforcement for a
single week of training. Split into ``budget`` (leaf helpers),
``daily_workouts`` (sizing, placing and building the day cards),
``intensive_weekend`` (ITW reshaping), ``backyard_week`` (loop-simulation
reshaping), ``long_run_contract`` (the road long run's final settlement), and
``orchestrator`` (assembly). Names are re-exported so callers import from this
package unchanged.
"""

from app.contexts.plan.generators.weekly_plan_builder.backyard_week import (
    apply_backyard_week,
)
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
from app.contexts.plan.generators.weekly_plan_builder.daily_workouts import (
    generate_daily_workouts,
)
from app.contexts.plan.generators.weekly_plan_builder.intensive_weekend import (
    apply_intensive_weekend,
)
from app.contexts.plan.generators.weekly_plan_builder.orchestrator import (
    _vertical_simulation_targets,
    build_weekly_plan,
)

__all__ = [
    "build_weekly_plan",
    "generate_daily_workouts",
    "apply_intensive_weekend",
    "apply_backyard_week",
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
