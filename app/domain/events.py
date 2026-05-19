"""Domain events emitted by bounded contexts.

Defined first so producers and handlers can be wired incrementally during the
migration to a domain-driven layout. No producers publish these yet.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DomainEvent:
    """Base class for all domain events."""

    aggregate_id: str
    occurred_at: datetime = field(default_factory=_utcnow)


@dataclass
class PlanGenerated(DomainEvent):
    plan_type: str = ""
    target_distance: float = 0.0
    weeks: int = 0


@dataclass
class PlanAdapted(DomainEvent):
    adjustment_reason: str = ""
    weeks_affected: int = 0


@dataclass
class PlanCustomized(DomainEvent):
    customization_kind: str = ""


@dataclass
class PlanDeleted(DomainEvent):
    pass


@dataclass
class RunLogged(DomainEvent):
    distance_km: float = 0.0
    duration_min: float = 0.0
    workout_type: Optional[str] = None


@dataclass
class FitnessUpdated(DomainEvent):
    current_vdot: Optional[float] = None
    avg_weekly_km: Optional[float] = None


@dataclass
class ReadinessRecorded(DomainEvent):
    score: float = 0.0


@dataclass
class VDOTUpdated(DomainEvent):
    old_vdot: float = 0.0
    new_vdot: float = 0.0


@dataclass
class ZoneRecalculated(DomainEvent):
    zone_type: str = ""  # "pace" | "hr"


@dataclass
class NutritionPlanGenerated(DomainEvent):
    target_distance: float = 0.0
