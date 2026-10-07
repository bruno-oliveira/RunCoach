"""Keep a plan's easy band on the pace the runner jogs at today.

The band a plan is generated with is a measurement taken on the day it was
made. Left there it goes stale in exactly the way that makes a plan feel
canned: the runner gets fitter, their easy runs come in quicker at the same
heart rate, and the plan keeps prescribing last season's jog.

This is the easy-pace counterpart of ``vdot_recalibrator`` and deliberately
separate from it. Fitness moves the quality paces and is read from hard
efforts; the easy band is read from easy ones. Neither implies the other, so
each sync asks both questions and either can answer alone.
"""

import logging
import re
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.training.physiology.personal_easy_band import (
    easy_pace_moved,
    has_personal_easy_band,
)
from app.core.training.workouts.workout_steps import repace_steps
from app.models import TrainingPlan

from ._helpers import parse_plan_data_lookups
from .reconcile import pace_zones_for
from .vdot_recalibrator import _current_week, _store_new_paces

logger = logging.getLogger(__name__)

# The prose a workout carries beside its steps; both quote the easy band.
_PACED_TEXT_FIELDS = ("description", "coaching_rationale")
_EASY_SUB_ZONES = ("recovery", "easy", "long_run")


def _easy_pace_strings(zones: Dict[str, Any]) -> list[str]:
    """Every pace string the easy zone prints: its sub-zones, then the band."""
    easy = zones.get("E") or {}
    subs = easy.get("sub_zones") or {}
    strings = [(subs.get(name) or {}).get("pace_str") or "" for name in _EASY_SUB_ZONES]
    return [*strings, easy.get("pace_str") or ""]


def _text_repacer(
    old_zones: Dict[str, Any], new_zones: Dict[str, Any]
) -> Callable[[str], str]:
    """A function swapping the old easy paces quoted in prose for the new ones.

    One pass over the text, not one replace per pace: a band that moves by its
    own width makes the new recovery range read exactly like the old easy one,
    and a second replace would then move it again.
    """
    swaps: Dict[str, str] = {}
    for before, after in zip(
        _easy_pace_strings(old_zones), _easy_pace_strings(new_zones)
    ):
        if before and after:
            swaps.setdefault(before, after)
    if not swaps:
        return lambda text: text
    pattern = re.compile("|".join(re.escape(before) for before in swaps))
    return lambda text: pattern.sub(lambda found: swaps[found.group(0)], text)


def _repace_text(workout: Dict[str, Any], repace: Callable[[str], str]) -> None:
    for name in _PACED_TEXT_FIELDS:
        text = workout.get(name)
        if isinstance(text, str):
            workout[name] = repace(text)


def refresh_easy_band(
    training_plan: TrainingPlan, user_id: str, db: Session
) -> Optional[Dict[str, Any]]:
    """Re-pace the weeks ahead when the runner's easy pace has moved.

    Does nothing for a plan with no VDOT (it has no paces at all yet, and its
    first sync seeds both at once), when nothing was measured, or when the
    measured pace sits within the dead band of the one already in use. Weeks
    already run are left as they were prescribed.

    Returns:
        The before/after pace and band when steps were re-paced, else ``None``.
    """
    from app.application.ports import current_easy_pace

    if not training_plan.vdot:
        return None
    stored = training_plan.easy_pace_min_km
    observed = current_easy_pace(user_id, db)
    if observed is None or not easy_pace_moved(stored, observed):
        return None
    current_week = _current_week(training_plan)
    old_zones = pace_zones_for(training_plan)
    new_zones = pace_zones_for(training_plan, easy_pace=observed)
    if current_week is None or not old_zones or not new_zones:
        return None
    if not has_personal_easy_band(new_zones):
        # The measured pace cannot be squared with this plan's threshold pace;
        # the VDOT band stays rather than a band that reaches tempo.
        return None

    plan_data, _, pd_workout = parse_plan_data_lookups(training_plan)
    repace_text = _text_repacer(old_zones, new_zones)
    pace_updates = 0
    for (week_num, _day), workout in pd_workout.items():
        if week_num < current_week:
            continue
        changed = repace_steps(workout.get("steps") or [], old_zones, new_zones)
        if changed:
            _repace_text(workout, repace_text)
        pace_updates += changed
    if pace_updates == 0:
        return None

    training_plan.easy_pace_min_km = observed
    weekly_updates = _store_new_paces(
        training_plan, plan_data, training_plan.vdot, current_week, new_zones, db
    )
    logger.info(
        "Easy band refresh: plan=%s old=%s new=%.3f pace_updates=%d weekly_updates=%d",
        training_plan.id,
        stored,
        observed,
        pace_updates,
        weekly_updates,
    )
    return {
        "old_easy_pace": stored,
        "new_easy_pace": observed,
        "old_band": old_zones["E"]["pace_str"],
        "new_band": new_zones["E"]["pace_str"],
        "pace_updates": pace_updates,
        "weekly_plans_updated": weekly_updates,
    }
