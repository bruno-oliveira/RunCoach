"""Shared value objects for plan-adjustment signal computation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session


@dataclass
class SignalContribution:
    """One signal's contribution to the final multiplier.

    ``factor`` is the signal's raw factor (e.g. 0.95, 1.05). ``weight`` is the
    base phase weight; the orchestrator may redistribute it onto data-bearing
    signals when ``has_data`` is False. ``extras`` carries signal-specific
    debug fields merged into the final result dict.
    """

    factor: float
    weight: float
    has_data: bool = True
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _SignalContext:
    """Bundle of inputs shared by the registered signal computers."""

    all_plan_runs: List
    past_workouts: List[Tuple]
    past_workout_ids: set
    today: Any
    plan_id: str
    db: Session
    recency_weight_fn: Any
    hr_zones: Optional[list[dict]]
    run_feedback_list: Optional[List]
    readiness_logs: Optional[List]
