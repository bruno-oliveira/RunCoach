"""Plan type registry — replaces stringly-typed `plan_type` if/elif dispatches.

Each handler encapsulates the behavior that varies by plan kind:
- ``display_label`` for plan listings / sharing views
- ``enrich_view_context`` for per-type context augmentation in the plan view

PDF export needs no parallel registry: ``app.infrastructure.export.runna``
renders every plan type from the same weekly structure.

Add a new plan type by writing one handler class and prepending it to
``PLAN_TYPE_REGISTRY``.
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
        from app.core.training.goal_pace_model import goal_vdot_from_time
        from app.core.training.vdot_calculator import VDOTCalculator
        from app.utils import format_pace

        try:
            perf_service = PerformanceService(db)
            gen = PerformancePlanGenerator()
            # Display the runner's goal-fitness Daniels zones (the paces they
            # are training toward), not a crude goal-pace×multiplier fallback.
            target_km = plan.target_distance_km
            goal_vdot = None
            if plan.goal_pace and target_km:
                goal_vdot = goal_vdot_from_time(
                    target_km, int(plan.goal_pace * target_km * 60)
                )
            goal_vdot_zones = (
                VDOTCalculator.get_pace_zones(goal_vdot, target_km)
                if goal_vdot
                else None
            )
            # Anchor the pace panel's HR bands on the SAME resting/LTHR the
            # stored canonical zones used, so the "your training paces" BPM band
            # matches the "Heart Rate Training Zones" panel exactly.
            stored_zones = plan.hr_zones_data or {}
            zones = gen.calculate_training_zones(
                plan.goal_pace,
                plan.max_heart_rate,
                vdot_zones=goal_vdot_zones,
                race_distance_km=target_km or None,
                resting_hr=stored_zones.get("resting_hr"),
                lthr=stored_zones.get("lthr"),
            )
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
    name regardless of plan_type. Special-purpose plans (performance)
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
