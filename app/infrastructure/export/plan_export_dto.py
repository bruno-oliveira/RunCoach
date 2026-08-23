"""Data transfer object for PDF export.

Decouples the PDF generator from the SQLAlchemy ``TrainingPlan`` ORM model so
the export code can be tested from fixtures and exercised without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.models.training_plan import TrainingPlan


@dataclass
class PlanExportDTO:
    """Plan data shaped for the PDF generator.

    Mirrors the subset of ``TrainingPlan`` attributes the export code touches.
    Construct via :meth:`from_orm` at the router boundary.
    """

    id: str
    plan_type: str
    target_distance: str
    target_distance_km: float
    weeks_duration: int
    current_weekly_km: float
    created_at: datetime
    plan_data: List[Dict[str, Any]]
    nutrition_plan_data: Optional[Dict[str, Any]] = None
    max_heart_rate: Optional[int] = None
    current_pace: Optional[float] = None
    goal_pace: Optional[float] = None
    vdot: Optional[float] = None
    is_trail: bool = False
    target_elevation_gain_m: Optional[float] = None
    # A backyard plan is stored as a trail plan over a *clamped* projection, so
    # the cover has to read the loop count or it prints a race nobody entered.
    is_backyard: bool = False
    backyard_target_loops: Optional[int] = None

    @classmethod
    def from_orm(
        cls, plan: "TrainingPlan", plan_data: Optional[List[Dict[str, Any]]] = None
    ) -> "PlanExportDTO":
        """Build a DTO from a SQLAlchemy TrainingPlan.

        ``plan_data`` may be supplied separately for callers that already
        loaded / decoded it; otherwise falls back to ``plan.plan_data``.
        """
        data = plan_data if plan_data is not None else (plan.plan_data or [])
        return cls(
            id=plan.id,
            plan_type=getattr(plan, "plan_type", "distance") or "distance",
            target_distance=plan.target_distance,
            target_distance_km=plan.target_distance_km,
            weeks_duration=plan.weeks_duration,
            current_weekly_km=plan.current_weekly_km,
            created_at=plan.created_at,
            plan_data=data,
            nutrition_plan_data=plan.nutrition_plan_data,
            max_heart_rate=plan.max_heart_rate,
            current_pace=plan.current_pace,
            goal_pace=plan.goal_pace,
            vdot=plan.vdot,
            is_trail=bool(getattr(plan, "is_trail", False)),
            target_elevation_gain_m=getattr(plan, "target_elevation_gain_m", None),
            is_backyard=bool(getattr(plan, "is_backyard", False)),
            backyard_target_loops=getattr(plan, "backyard_target_loops", None),
        )
