"""Plan type registry — replaces stringly-typed `plan_type` if/elif dispatches.

Each handler encapsulates the behavior that varies by plan kind:
- ``display_label`` for plan listings / sharing views
- ``enrich_view_context`` for per-type context augmentation in the plan view

PDF rendering uses a parallel registry: ``app.infrastructure.export.pdf_plan_renderers``
(``PdfPlanRenderer`` subclasses selected via ``get_renderer_for_plan``).

Add a new plan type by writing one handler class and prepending it to
``PLAN_TYPE_REGISTRY`` (and, if it renders differently, a matching
``PdfPlanRenderer``).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy.orm import Session

from app.constants import DISTANCE_NAMES

if TYPE_CHECKING:
    from app.models.training_plan import TrainingPlan

logger = logging.getLogger(__name__)


class PlanTypeHandler(ABC):
    """Per-plan-type behavior for views and listings."""

    kind: str = ""

    @abstractmethod
    def matches(self, plan: "TrainingPlan") -> bool: ...

    @abstractmethod
    def display_label(self, plan: "TrainingPlan") -> str: ...

    def enrich_view_context(
        self,
        plan: "TrainingPlan",
        db: Session,
        extra: Dict[str, Any],
        plan_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mutate / augment plan view context. Default: no-op."""
        return extra


class PerformancePlanHandler(PlanTypeHandler):
    kind = "performance"

    def matches(self, plan: "TrainingPlan") -> bool:
        return getattr(plan, "plan_type", "") == "performance"

    def display_label(self, plan: "TrainingPlan") -> str:
        return "Performance"

    def enrich_view_context(
        self,
        plan: "TrainingPlan",
        db: Session,
        extra: Dict[str, Any],
        plan_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from app.application.ports import PerformanceService
        from app.contexts.plan.generators.performance_plan_generator import (
            PerformancePlanGenerator,
        )
        from app.utils import format_pace

        try:
            perf_service = PerformanceService(db)
            gen = PerformancePlanGenerator()
            zones = gen.calculate_training_zones(plan.goal_pace, plan.max_heart_rate)
            for zone_data in zones.values():
                zone_data["pace_formatted"] = format_pace(zone_data["pace"])
                if "pace_range" in zone_data:
                    pr = zone_data["pace_range"]
                    zone_data["pace_range_formatted"] = (
                        f"{format_pace(pr[0])} - {format_pace(pr[1])}"
                    )
            extra["training_zones"] = zones
            extra["today_workout"] = perf_service.get_todays_workout(plan)
            extra["perf_progress_data"] = perf_service.get_plan_progress(plan)
        except Exception as e:
            logger.warning(f"Performance context enrichment failed: {e}")
        return extra


class FitnessPlanHandler(PlanTypeHandler):
    kind = "fitness"

    def matches(self, plan: "TrainingPlan") -> bool:
        return getattr(plan, "plan_type", "") == "fitness"

    def display_label(self, plan: "TrainingPlan") -> str:
        return "Fitness"

    def enrich_view_context(
        self,
        plan: "TrainingPlan",
        db: Session,
        extra: Dict[str, Any],
        plan_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from app.contexts.plan.generators.fitness_plan_generator import (
            _PHASE_METADATA,
            FitnessPlanGenerator,
        )
        from app.core.training.vdot_calculator import VDOTCalculator
        from app.utils import format_pace

        try:
            gen = FitnessPlanGenerator()
            vdot = plan.vdot
            zones = gen.calculate_training_zones(vdot, plan.max_heart_rate)
            for zone_data in zones.values():
                zone_data["pace_formatted"] = format_pace(zone_data["pace"])
                if "pace_range" in zone_data:
                    pr = zone_data["pace_range"]
                    zone_data["pace_range_formatted"] = (
                        f"{format_pace(pr[0])} - {format_pace(pr[1])}"
                    )
            extra["training_zones"] = zones
            focus_area = (
                plan.target_distance.replace("fitness_", "")
                if plan.target_distance.startswith("fitness_")
                else "vo2max"
            )
            extra["fitness_focus_area"] = focus_area
            phase_durations = gen._calculate_fitness_phases(
                plan.weeks_duration, focus_area
            )
            extra["phases"] = {
                phase: {"weeks": phase_durations[phase], **_PHASE_METADATA[phase]}
                for phase in phase_durations
            }
            time_trial_weeks: List[Dict[str, Any]] = []
            for week_data in plan_data or []:
                if week_data.get("is_time_trial_week"):
                    for dw in week_data.get("daily_workouts", []):
                        if dw.get("type") == "time_trial":
                            time_trial_weeks.append(
                                {
                                    "week": week_data["week"],
                                    "distance": dw.get("distance", 0),
                                    "description": dw.get("description", ""),
                                }
                            )
            extra["time_trial_weeks"] = time_trial_weeks
            if vdot:
                extra["vdot_zones"] = VDOTCalculator.get_pace_zones(vdot)
        except Exception as e:
            logger.warning(f"Fitness context enrichment failed: {e}")
        return extra


class DistancePlanHandler(PlanTypeHandler):
    """Fallback handler for traditional distance-based plans."""

    kind = "distance"

    def matches(self, plan: "TrainingPlan") -> bool:
        return True  # last in registry — always matches

    def display_label(self, plan: "TrainingPlan") -> str:
        td = plan.target_distance_km
        return DISTANCE_NAMES.get(td, f"{td}km")


PLAN_TYPE_REGISTRY: List[PlanTypeHandler] = [
    PerformancePlanHandler(),
    FitnessPlanHandler(),
    DistancePlanHandler(),
]


def get_handler_for_plan(plan: "TrainingPlan") -> PlanTypeHandler:
    """Return the first registered handler that matches the plan."""
    for handler in PLAN_TYPE_REGISTRY:
        if handler.matches(plan):
            return handler
    raise ValueError(
        f"No handler matched plan with plan_type={getattr(plan, 'plan_type', None)!r}"
    )


def display_label(plan: "TrainingPlan", *, space_before_km: bool = False) -> str:
    """Resolve the user-facing label for a plan.

    Distance-bearing plans (target_distance_km > 0) always render the distance
    name regardless of plan_type. Special-purpose plans (performance/fitness)
    fall through to their handler's label.
    """
    td = plan.target_distance_km
    if td and td > 0:
        suffix = " km" if space_before_km else "km"
        return DISTANCE_NAMES.get(td, f"{td}{suffix}")
    handler = get_handler_for_plan(plan)
    if handler.kind == "distance":
        suffix = " km" if space_before_km else "km"
        return f"{td}{suffix}"
    return handler.display_label(plan)
