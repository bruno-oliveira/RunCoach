"""Per-frequency plan structure: the Protocol composers implement.

Frequency determines plan *structure* (what each day is for), distance
determines plan *content* (intensities and long-run caps within that
structure).  A 3-run half-marathon and a 3-run 10K share the same weekly
template shape — they differ in workout intensities and long-run targets,
not in the number or role of each slot.

This module lives in domain/ (pure, no I/O) so the dependency rule is
respected: concrete composers in core/training/frequency/ implement the
Protocol, and the orchestrator in contexts/plan/ consumes it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class SlotType(Enum):
    EASY = "easy"
    QUALITY = "quality"
    LONG = "long"
    MEDIUM_LONG = "medium_long"
    RECOVERY = "recovery"


class IntensityZone(Enum):
    EASY = "easy"
    MODERATE = "moderate"
    THRESHOLD = "threshold"
    VO2MAX = "vo2max"
    SPEED = "speed"


@dataclass(frozen=True)
class WorkoutSlot:
    slot_type: SlotType
    volume_pct: float
    intensity: IntensityZone
    is_protected: bool = False
    allows_quality_swap: bool = False
    label: str = ""


@dataclass(frozen=True)
class AdaptationPolicy:
    long_run_pct_floor: float
    long_run_pct_cap: float
    medium_long_pct_floor: float | None
    protected_slots: list[SlotType] = field(default_factory=list)
    min_quality_count: int = 0
    max_quality_count: int = 2
    can_suggest_frequency_change: bool = False
    frequency_change_direction: int | None = None


class FrequencyComposer(Protocol):
    @property
    def frequency(self) -> int: ...

    def slots(self, phase: str) -> list[WorkoutSlot]:
        """Ordered workout slots for one week in the given phase."""
        ...

    def long_run_pct(self, phase: str) -> tuple[float, float]:
        """(min_pct, max_pct) for the long run in this phase."""
        ...

    def quality_budget(self, phase: str) -> int:
        """Maximum quality sessions allowed in this phase."""
        ...

    def adaptation_policy(self) -> AdaptationPolicy: ...

    def validate_week(self, distances: list[float], types: list[str]) -> list[str]:
        """Return violation descriptions, empty if valid."""
        ...
