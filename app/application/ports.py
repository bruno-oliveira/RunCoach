"""Application-layer ports: the single seam for cross-context access.

The dependency rule (see ``ARCHITECTURAL_IMPROVEMENT.md``) allows a bounded
context to reach a *sibling* context only through the application layer or via
events — never by importing the sibling's modules directly. This module is
that seam.

Every cross-context symbol a context needs is re-exported here:

* Under ``TYPE_CHECKING`` the real classes / functions are imported so static
  checkers resolve annotations and attribute access to the genuine types.
* At runtime they are resolved lazily by :func:`__getattr__` (PEP 562), which
  imports the owning context module on first access.

Resolution stays lazy on purpose: every one of these edges previously lived
inside a function to dodge an import cycle, and the lazy seam preserves that
timing while making the dependency direction legal (``context -> application
-> sibling``) and auditable in one place. Contexts import the symbol they need
from here — keeping the import inside the function as before — instead of
importing the sibling context directly.

When a context genuinely needs a new sibling capability, add an entry to
``_LAZY`` (and the ``TYPE_CHECKING`` block) rather than importing the sibling.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type-only re-exports (the ``as`` alias marks them intentional re-exports);
    # the runtime values come from ``__getattr__`` below.
    from app.contexts.auth.repositories import (
        SQLAlchemyUserRepository as SQLAlchemyUserRepository,
    )
    from app.contexts.nutrition.nutrition_engine import (
        NutritionEngine as NutritionEngine,
    )
    from app.contexts.plan.adaptation import AdaptationService as AdaptationService
    from app.contexts.plan.adaptation.vdot_recalibrator import (
        recalibrate_zones_only as recalibrate_zones_only,
    )
    from app.contexts.plan.generators.fitness_plan_generator import (
        FitnessPlanGenerator as FitnessPlanGenerator,
    )
    from app.contexts.plan.generators.performance_plan_generator import (
        PerformancePlanGenerator as PerformancePlanGenerator,
    )
    from app.contexts.plan.plan_service import PlanService as PlanService
    from app.contexts.plan.repositories import (
        SQLAlchemyPlanRepository as SQLAlchemyPlanRepository,
    )
    from app.contexts.runner.fitness.hr_zone_service import (
        HRZoneService as HRZoneService,
    )
    from app.contexts.runner.fitness.performance_service import (
        PerformanceService as PerformanceService,
    )
    from app.contexts.runner.fitness.race_predictor_service import (
        RacePredictorService as RacePredictorService,
    )
    from app.contexts.runner.fitness.readiness_scoring import (
        score_mountain_simulation as score_mountain_simulation,
    )
    from app.contexts.runner.fitness.training_load_service import (
        TrainingLoadService as TrainingLoadService,
    )


# Symbol name -> (owning context module, attribute). The single registry of
# every cross-context edge in the codebase.
_LAZY: dict[str, tuple[str, str]] = {
    "SQLAlchemyUserRepository": (
        "app.contexts.auth.repositories",
        "SQLAlchemyUserRepository",
    ),
    "NutritionEngine": (
        "app.contexts.nutrition.nutrition_engine",
        "NutritionEngine",
    ),
    "AdaptationService": ("app.contexts.plan.adaptation", "AdaptationService"),
    "recalibrate_zones_only": (
        "app.contexts.plan.adaptation.vdot_recalibrator",
        "recalibrate_zones_only",
    ),
    "FitnessPlanGenerator": (
        "app.contexts.plan.generators.fitness_plan_generator",
        "FitnessPlanGenerator",
    ),
    "PerformancePlanGenerator": (
        "app.contexts.plan.generators.performance_plan_generator",
        "PerformancePlanGenerator",
    ),
    "PlanService": ("app.contexts.plan.plan_service", "PlanService"),
    "SQLAlchemyPlanRepository": (
        "app.contexts.plan.repositories",
        "SQLAlchemyPlanRepository",
    ),
    "HRZoneService": (
        "app.contexts.runner.fitness.hr_zone_service",
        "HRZoneService",
    ),
    "PerformanceService": (
        "app.contexts.runner.fitness.performance_service",
        "PerformanceService",
    ),
    "RacePredictorService": (
        "app.contexts.runner.fitness.race_predictor_service",
        "RacePredictorService",
    ),
    "score_mountain_simulation": (
        "app.contexts.runner.fitness.readiness_scoring",
        "score_mountain_simulation",
    ),
    "TrainingLoadService": (
        "app.contexts.runner.fitness.training_load_service",
        "TrainingLoadService",
    ),
}

__all__ = list(_LAZY)


def __getattr__(name: str) -> Any:
    """Lazily resolve a cross-context symbol from its owning context."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = target
    return getattr(importlib.import_module(module_path), attr)


def __dir__() -> list[str]:
    return sorted([*globals(), *_LAZY])
