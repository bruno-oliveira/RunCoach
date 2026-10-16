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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation.reconcile import pace_zones_for
from app.core.training.physiology.zone_calculator import calculate_zones
from app.core.training.training_config import DISTANCE_NAMES

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
        """Mutate / augment plan view context.

        Default: the pace-zone table, for any plan paced off a single VDOT.
        """
        zones = _single_vdot_training_zones(plan)
        if zones:
            extra["training_zones"] = zones
        return extra


def _single_vdot_training_zones(
    plan: "TrainingPlan",
) -> Optional[Dict[str, Dict[str, Any]]]:
    """The pace-zone table for a plan paced off one VDOT, or ``None`` without one.

    Every plan is paced off the single VDOT its steps were built from, and
    used to show a pace on each session with no table to read it against —
    only heart-rate bands. The table comes
    from those same zones, so it cannot disagree with the cards under it; a
    plan with no VDOT still gets none rather than a guessed one.
    """
    vdot_zones = pace_zones_for(plan)
    if not vdot_zones:
        return None
    # A trail goal pace is climbing and terrain as much as fitness, so it is
    # never shown as a flat race-pace band.
    goal_pace = None if getattr(plan, "is_trail", False) else plan.goal_pace
    stored_zones = plan.hr_zones_data or {}
    return calculate_zones(
        vdot_zones=vdot_zones,
        goal_pace=goal_pace,
        max_hr=plan.max_heart_rate,
        resting_hr=stored_zones.get("resting_hr"),
        lthr=stored_zones.get("lthr"),
        race_distance_km=plan.target_distance_km or None,
    )


class BackyardPlanHandler(PlanTypeHandler):
    """Backyard plans are labelled by loop count, never by their projection.

    ``target_distance`` on a backyard row holds the ultra the engine
    periodises against, clamped to the engine's ceiling — so a 36-loop and a
    48-loop goal both store 163 km, and labelling from the distance would
    render two very different races identically (and wrongly: neither runner
    is training for "163km").
    """

    kind = "backyard"

    def matches(self, plan: "TrainingPlan") -> bool:
        return bool(getattr(plan, "is_backyard", False)) and bool(
            getattr(plan, "backyard_target_loops", None)
        )

    def display_label(self, plan: "TrainingPlan") -> str:
        return f"{plan.backyard_target_loops}-Loop Backyard"


class RecoveryPlanHandler(PlanTypeHandler):
    """The easy block after a race. It has no race of its own, so no distance."""

    kind = "recovery"

    def matches(self, plan: "TrainingPlan") -> bool:
        return getattr(plan, "plan_type", "") == "recovery"

    def display_label(self, plan: "TrainingPlan") -> str:
        return "Recovery"


class DistancePlanHandler(PlanTypeHandler):
    """Fallback handler for traditional distance-based plans."""

    kind = "distance"

    def matches(self, plan: "TrainingPlan") -> bool:
        return True  # last in registry — always matches

    def display_label(self, plan: "TrainingPlan") -> str:
        td = plan.target_distance_km
        return DISTANCE_NAMES.get(td, f"{td}km")


PLAN_TYPE_REGISTRY: List[PlanTypeHandler] = [
    BackyardPlanHandler(),
    RecoveryPlanHandler(),
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


def custom_plan_title(plan: "TrainingPlan") -> Optional[str]:
    """ "Custom Plan N · <distance>" for a custom plan, ``None`` for any other.

    A title rather than a label: ``display_label`` names the race (and is
    printed as "<label> Training Plan" or "Optimized for a <label> goal"), so a
    custom plan keeps its race label there and carries its own name here.
    """
    index = getattr(plan, "custom_index", None)
    if getattr(plan, "custom_spec", None) is None or not index:
        return None
    return f"Custom Plan {index} · {display_label(plan)}"


def display_label(plan: "TrainingPlan", *, space_before_km: bool = False) -> str:
    """Resolve the user-facing label for a plan.

    Backyard plans render their loop count. Other distance-bearing plans
    (target_distance_km > 0) always render the distance name regardless of
    plan_type. Plans with no race (recovery) fall through to their handler's
    label.
    """
    # Backyard first: its target_distance is a clamped projection, so the
    # distance shortcut below would label it with a number nobody is racing.
    backyard = BackyardPlanHandler()
    if backyard.matches(plan):
        return backyard.display_label(plan)

    td = plan.target_distance_km
    if td and td > 0:
        suffix = " km" if space_before_km else "km"
        return DISTANCE_NAMES.get(td, f"{td}{suffix}")
    handler = get_handler_for_plan(plan)
    if handler.kind == "distance":
        suffix = " km" if space_before_km else "km"
        return f"{td}{suffix}"
    return handler.display_label(plan)
