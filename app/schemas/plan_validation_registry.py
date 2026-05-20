"""Plan-type validation registry.

Allows adding new plan types (e.g. couch-to-10K) without modifying the
PlanRequest schema. Each rule registers validators keyed by a plan-type
identifier; PlanRequest queries the registry instead of hard-coding
distance branches.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class PlanValidationRule:
    """Validation rule for a single plan type.

    Each function takes the in-construction PlanRequest instance and
    raises ValueError / a domain exception when the rule fails. None for
    a slot disables that check for this plan type.
    """

    name: str
    description: str = ""
    validate_weeks: Optional[Callable[["object"], None]] = None
    validate_runs_per_week: Optional[Callable[["object"], None]] = None
    validate_current_mileage: Optional[Callable[["object"], None]] = None
    extra_validators: list[Callable[["object"], None]] = field(default_factory=list)


class PlanValidationRegistry:
    """Open-for-extension registry of plan-type validation rules."""

    _rules: dict[str, PlanValidationRule] = {}

    @classmethod
    def register(cls, plan_type: str, rule: PlanValidationRule) -> None:
        cls._rules[plan_type] = rule

    @classmethod
    def get(cls, plan_type: str) -> Optional[PlanValidationRule]:
        return cls._rules.get(plan_type)

    @classmethod
    def known_types(cls) -> list[str]:
        return list(cls._rules.keys())

    @classmethod
    def clear(cls) -> None:
        """Reset the registry (test helper)."""
        cls._rules.clear()
