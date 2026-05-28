"""Preconditions for ``_run_adjust``: gather signals or bail with an early result.

When the orchestrator can't proceed (plan missing, plan not started, fewer
than 3 logged runs, no past workouts to evaluate), this module shapes the
early-exit result so the orchestrator can return it verbatim.
"""

from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.models import RunLog

from . import change_reasons as _reasons
from .change_plan_builder import empty_change_plan


def check_preconditions_or_gather(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    mode: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Gather adjustment signals or bail with an early-exit result.

    Returns ``(None, gathered)`` when ``gather_signals`` produced data;
    ``(early_exit_dict, None)`` when it didn't. The early-exit dict carries
    a ``change_plan`` shaped via ``empty_change_plan`` plus a human-readable
    ``reason`` and (where applicable) ``total_runs``.

    Why a tuple rather than a sentinel object: ``None`` already means
    "no early exit, proceed"; a tuple keeps the call site to two
    assignments without inventing a new dataclass.
    """
    # Local import avoids the circular dependency:
    # plan_adjuster → precondition_guards → plan_adjuster.gather_signals.
    from .plan_adjuster import gather_signals

    gathered = gather_signals(plan_id, user_id, db)
    if gathered is not None:
        return None, gathered

    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
    if not training_plan:
        cp = empty_change_plan(
            action="adjust",
            mode=mode,
            headline_reason="Plan not found.",
        )
        return (
            {"adjusted": False, "reason": "Plan not found", "change_plan": cp},
            None,
        )

    if not training_plan.start_date:
        cp = empty_change_plan(
            action="adjust",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_PLAN_NOT_STARTED,
        )
        return (
            {
                "adjusted": False,
                "reason": "Plan has no start date.",
                "change_plan": cp,
            },
            None,
        )

    total_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan_id).count()
    if total_runs < 3:
        cp = empty_change_plan(
            action="adjust",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_INSUFFICIENT_DATA,
        )
        return (
            {
                "adjusted": False,
                "reason": "Not enough data (need at least 3 logged runs linked to this plan)",
                "total_runs": total_runs,
                "change_plan": cp,
            },
            None,
        )

    cp = empty_change_plan(
        action="adjust",
        mode=mode,
        headline_reason="No past workouts to evaluate yet.",
    )
    return (
        {
            "adjusted": False,
            "reason": "No past workouts to evaluate yet.",
            "change_plan": cp,
        },
        None,
    )
