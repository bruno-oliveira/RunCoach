"""The single last word after any post-generation change to a plan.

Generation ends in ``plan_finalizer.finalize_plan``, so a fresh plan's cards,
executable steps and weekly totals agree. Everything that edits a plan
afterwards — intents, undo, reset, type swaps, day swaps, pace recalibration —
used to hand-patch a different subset of the two representations (the ORM
tree and the ``plan_data`` JSON snapshot). Each one left a different seam: an
undo restored the distance but not the steps, an eased tempo kept its tempo
reps, a reset week rendered its adjusted steps total. The runner saw one
session and their watch got another.

:func:`finalize_plan_mutation` closes that seam for every writer at once: the
ORM distances are authoritative, the JSON (steps, prose, card distance, week
totals) is re-projected from them, the structure guard sees the result, and
the adaptation revision moves so optimistic-concurrency clients notice.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training.workouts import key_workout_library as _kwlib
from app.core.training.workouts import workout_steps as _steps_mod
from app.models import TrainingPlan, WeeklyPlan
from app.utils import persist_json

from ._helpers import batch_workouts_by_week, parse_plan_data_lookups
from .reconcile import pace_zones_for, reconcile_plan_data_to_orm

logger = logging.getLogger(__name__)

# Below the view enricher's 0.2 km tolerance, so a finalized plan never gives
# the render-time repair anything to do.
_KEY_STEPS_DRIFT_KM = 0.15

# Fields that describe *what the watch executes* rather than how far it is.
# A day that stops being that session (rest, an eased-to-easy tempo) must lose
# all of them, or the card and the watch keep the old workout.
_SESSION_PAYLOAD_KEYS = (
    "steps",
    "segments",
    "structure",
    "key_workout_id",
    "key_workout_name",
    "key_workout_rationale",
    "target_pace",
    "target_pace_formatted",
    "fixed_structure",
)


def clear_session_payload(pd_wo: Dict[str, Any]) -> None:
    """Strip a plan_data workout of the executable session it used to carry."""
    for key in _SESSION_PAYLOAD_KEYS:
        pd_wo.pop(key, None)
    pd_wo["steps"] = []


def _rebuild_drifted_key_workouts(
    weeks: List[WeeklyPlan],
    workouts_by_week: Dict[str, List[Any]],
    pd_workout: Dict[Any, Dict[str, Any]],
    pace_zones: Optional[Dict[str, Any]],
) -> None:
    """Regenerate key sessions whose steps no longer total their ORM distance.

    ``reconcile_plan_data_to_orm`` leaves key workouts alone because the
    weekly adjuster rebuilds them inline. Every other writer does not, so a
    reset or undo of a key session is caught here instead.
    """
    for week in weeks:
        for workout in workouts_by_week.get(week.id, []):
            if not workout.key_workout_id:
                continue
            pd_wo = pd_workout.get((week.week_number, int(workout.day_of_week)))
            if pd_wo is None:
                continue
            target = float(workout.distance_km or 0)
            if target <= 0:
                continue
            steps = pd_wo.get("steps") or []
            steps_km = _steps_mod._compute_distance_from_steps(steps) if steps else 0
            drifted = steps_km > 0 and abs(steps_km - target) > _KEY_STEPS_DRIFT_KM
            if pd_wo.get("distance") == target and not drifted:
                continue
            pd_wo["distance"] = target
            if _kwlib.rebuild_key_workout(pd_wo, pace_zones):
                workout.distance_km = round(pd_wo.get("distance") or target, 1)


def finalize_plan_mutation(
    training_plan: TrainingPlan,
    db: Session,
    *,
    week_numbers: Optional[Iterable[int]] = None,
    bump_revision: bool = True,
) -> Dict[str, List[str]]:
    """Re-project ``plan_data`` from the ORM and re-check the touched weeks.

    Call after the ORM rows reflect the intended change. Does not commit —
    the caller owns the transaction, so preview flows can still roll back.

    Args:
        training_plan: The plan that was edited.
        db: Session holding the pending edits.
        week_numbers: Weeks that changed; ``None`` reconciles every week.
        bump_revision: Advance ``adaptation_revision``. Pass ``False`` when the
            caller already bumped it for this change.

    Returns:
        The structure guard's ``{"fatal": [...], "warnings": [...]}`` for the
        touched weeks. Never raises on them: a user asking for a rest week is
        entitled to a week with nothing runnable in it.
    """
    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)
    query = db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == training_plan.id)
    if week_numbers is not None:
        wanted = sorted({int(n) for n in week_numbers})
        if not wanted:
            return {"fatal": [], "warnings": []}
        query = query.filter(WeeklyPlan.week_number.in_(wanted))
    weeks = query.all()
    workouts_by_week = batch_workouts_by_week([w.id for w in weeks], db)
    pace_zones = pace_zones_for(training_plan)

    _rebuild_drifted_key_workouts(weeks, workouts_by_week, pd_workout, pace_zones)
    reconcile_plan_data_to_orm(weeks, workouts_by_week, pd_workout, pd_week, pace_zones)
    for week in weeks:
        week.total_km = round(
            sum((w.distance_km or 0) for w in workouts_by_week.get(week.id, [])), 1
        )
        if week.week_number in pd_week:
            pd_week[week.week_number]["total_km"] = week.total_km

    training_plan.plan_data = plan_data
    persist_json(training_plan, "plan_data")
    if bump_revision:
        training_plan.adaptation_revision = (training_plan.adaptation_revision or 0) + 1

    touched = [pd_week[w.week_number] for w in weeks if w.week_number in pd_week]
    issues = check_plan_structure(touched) if touched else {"fatal": [], "warnings": []}
    # Card-versus-steps disagreement after a finalize is a bug in a writer, not
    # a runner's choice — surface it. Empty or sub-floor weeks usually are a
    # choice (away, sick), so they stay at debug.
    for warning in issues["warnings"]:
        if "steps total" in warning:
            logger.warning("Plan %s after mutation: %s", training_plan.id, warning)
    for fatal in issues["fatal"]:
        logger.debug("Plan %s after mutation: %s", training_plan.id, fatal)
    return issues
