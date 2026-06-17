"""External fitness-signal sources used during adaptation.

``gather_signals`` reads a VDOT trend, training load, and a mountain
simulation score from the runner context. Wrapping those callables in a
provider dataclass keeps the static cross-context import out of
``plan_adjuster`` — the runner-fitness modules are touched only when
``default_provider()`` is resolved (lazy) or when a test injects a
substitute.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class FitnessSignalsProvider:
    """Callables that ``gather_signals`` invokes when scoring adjustment.

    Each call site in ``plan_adjuster.gather_signals`` reads through the
    matching field instead of importing the runner module directly.
    """

    get_vdot_history: Callable[..., List[Dict[str, Any]]]
    calculate_vdot_trend: Callable[[List[Dict[str, Any]]], str]
    get_training_load: Callable[..., Optional[Dict[str, Any]]]
    score_mountain_simulation: Callable[..., int]


def default_provider() -> FitnessSignalsProvider:
    """Build the production provider, wiring runner-context implementations.

    The imports happen inside the function body so importing this module
    (and thus ``plan_adjuster``) does not pull in the runner context at
    module-load time. Resolution is fast — Python caches the import after
    the first call.
    """
    from app.application.ports import (
        RacePredictorService,
        TrainingLoadService,
        score_mountain_simulation,
    )

    return FitnessSignalsProvider(
        get_vdot_history=RacePredictorService.get_vdot_history,
        calculate_vdot_trend=RacePredictorService.calculate_vdot_trend,
        get_training_load=TrainingLoadService.get_training_load,
        score_mountain_simulation=score_mountain_simulation,
    )
