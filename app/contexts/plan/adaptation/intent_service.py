"""Intent-driven plan adaptation.

A single, life-event-shaped entry point for adapting a plan. Instead of the
old scattered surfaces (auto-accept toggle, weekly recommendation banner,
mid-plan "Adjust" button, alert/recalibrate modal, standing readiness widget),
the user declares *what's going on* and the plan reshapes itself:

    feeling_tired   – ease the rest of this week (scale down + drop to easy)
    feeling_strong  – bump upcoming weeks a touch
    skip_run        – drop a single run (today by default, or a chosen day)
    away            – mark a date range as rest (travel, etc.)
    sick_injured    – rest the next few days, then ramp back gently
    busy_week       – trim the rest of this week's volume

Every intent produces a ``ChangePlan`` and rides the existing preview → apply
modal, so the UX is identical regardless of intent. Intents are *repeatable
and non-compounding*: each mutation is computed from each workout's frozen
``baseline_distance_km`` (never stacked on a previous adjustment), every
application is recorded on the adaptation timeline, and "Reset to original"
restores the baseline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.plan_calendar import compute_current_week
from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from app.utils import persist_json
from app.utils import to_date as _to_date

from ._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    batch_workouts_by_week,
    parse_plan_data_lookups,
    today_date,
)
from .adjustment_results import record_adaptation_event
from .change_plan_builder import build_change_plan, empty_change_plan, snapshot_workouts
from .week_adjuster import apply_adjustment_to_future_weeks

logger = logging.getLogger(__name__)

# Hard sessions get demoted to easy when the user eases a week.
_HARD_TYPES = {
    "tempo",
    "interval",
    "threshold",
    "speed",
    "vo2max",
    "race_pace",
    "fartlek",
    "hill",
}

# Per-intent multipliers (applied to baseline, so repeats don't compound).
_TIRED_FACTOR = 0.85
_BUSY_FACTOR = 0.70
_STRONG_FACTOR = 1.08

# Gentle return ramp after illness/injury: only the first couple of weeks back
# are eased, then training resumes at its original prescription. Each entry is
# the multiplier for one week after the rest window (week 1 back, week 2 back);
# every week beyond the window is left untouched at baseline.
#
# The previous ramp spread 0.70 -> 1.0 across *every* remaining week, so a few
# sick days in week 3 of a 14-week plan quietly shaved volume off all 11
# following weeks. A short, fixed easing window matches how recovery actually
# works — rest, ease back over a week or two, then carry on as planned.
_SICK_RETURN_RAMP = (0.70, 0.85)

VALID_INTENTS = (
    "feeling_tired",
    "feeling_strong",
    "skip_run",
    "away",
    "sick_injured",
    "busy_week",
)


@dataclass
class _IntentContext:
    plan: TrainingPlan
    current_week: int
    current_dow: int
    db: Session


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preview_intent(
    plan_id: str,
    user_id: str,
    intent: str,
    params: Optional[Dict[str, Any]],
    db: Session,
) -> Dict[str, Any]:
    """Compute the ChangePlan an intent would produce, without persisting."""
    try:
        return _run_intent(plan_id, user_id, intent, params or {}, db, mode="preview")
    finally:
        db.rollback()
        db.expire_all()


def apply_intent(
    plan_id: str,
    user_id: str,
    intent: str,
    params: Optional[Dict[str, Any]],
    db: Session,
) -> Dict[str, Any]:
    """Apply an intent and persist the resulting ChangePlan."""
    return _run_intent(plan_id, user_id, intent, params or {}, db, mode="applied")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _run_intent(
    plan_id: str,
    user_id: str,
    intent: str,
    params: Dict[str, Any],
    db: Session,
    *,
    mode: str,
) -> Dict[str, Any]:
    if intent not in VALID_INTENTS:
        return empty_change_plan(
            action=intent,
            mode=mode,
            headline_reason=f"Unknown adaptation: {intent}.",
        )

    repo = SQLAlchemyPlanRepository(db)
    plan = repo.get_for_user(plan_id, user_id)
    if not plan:
        return empty_change_plan(
            action=intent, mode=mode, headline_reason="Plan not found."
        )

    start = _to_date(plan.start_date)
    if not start:
        return empty_change_plan(
            action=intent,
            mode=mode,
            headline_reason="Set a start date first, then RunCoach can adapt your plan.",
        )

    total_weeks = plan.weeks_duration or 0
    current_week = compute_current_week(start, today_date(), clamp_min=1) or 1
    if total_weeks and current_week > total_weeks:
        return empty_change_plan(
            action=intent,
            mode=mode,
            headline_reason="This plan is already complete — nothing left to adapt.",
        )

    backfill_baselines(plan, db)
    ctx = _IntentContext(
        plan=plan,
        current_week=current_week,
        current_dow=today_date().isoweekday(),
        db=db,
    )

    # Snapshot every remaining week so the ChangePlan diff is complete
    # regardless of which weeks the intent ends up touching.
    snapshot_weeks = list(range(current_week, (total_weeks or current_week) + 1))
    before = snapshot_workouts(plan, db, week_numbers=snapshot_weeks)

    recorder: List[Dict[str, Any]] = []
    handler = _HANDLERS[intent]
    headline = handler(ctx, params, recorder)

    after = snapshot_workouts(plan, db, week_numbers=snapshot_weeks)

    change_plan = build_change_plan(
        action=intent,
        mode=mode,
        training_plan=plan,
        before=before,
        after=after,
        recorder=recorder,
        headline_reason=headline,
        current_week=current_week,
        current_day_of_week=ctx.current_dow,
    )

    if mode == "applied":
        changed = change_plan["summary"]["workouts_changed_count"] > 0
        if changed:
            plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
            plan.last_change_plan = change_plan
            record_adaptation_event(
                plan,
                {
                    "type": "intent",
                    "intent": intent,
                    "reason": headline,
                    "workouts_changed": change_plan["summary"][
                        "workouts_changed_count"
                    ],
                    "total_km_delta": change_plan["summary"]["total_km_delta"],
                },
            )
        db.commit()

    return change_plan


# ---------------------------------------------------------------------------
# Intent handlers — each mutates the session and returns a headline reason
# ---------------------------------------------------------------------------


def _handle_feeling_tired(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    edits = _ease_rest_of_week(ctx, _TIRED_FACTOR, "Eased — you're feeling tired.")
    _edit_workouts(ctx, edits, recorder)
    return (
        "Eased the rest of this week and dropped hard sessions to easy — recover well."
    )


def _handle_busy_week(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    edits = _ease_rest_of_week(ctx, _BUSY_FACTOR, "Trimmed — busy week.")
    _edit_workouts(ctx, edits, recorder)
    return "Trimmed the rest of this week's volume so it fits a busy stretch."


def _handle_skip_run(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    target = _resolve_day(ctx, params.get("date"))
    if target is None:
        return "That day isn't in your plan — nothing to skip."
    week, day = target
    edits = {(week, day): _RestEdit("Skipped — you told us you're missing this run.")}
    _edit_workouts(ctx, edits, recorder)
    return "Marked that run as skipped — no need to make it up."


def _handle_away(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    start = _coerce_date(params.get("start_date")) or today_date()
    end = _coerce_date(params.get("end_date")) or start
    if end < start:
        start, end = end, start
    # Never rewrite the past — clamp the window to today onwards.
    start = max(start, today_date())
    if end < start:
        return "That date range is already behind you — nothing to change."

    edits: Dict[Tuple[int, int], "_RestEdit"] = {}
    cursor = start
    while cursor <= end:
        target = _date_to_week_day(ctx, cursor)
        if target is not None:
            edits[target] = _RestEdit("Away — rest day.")
        cursor += timedelta(days=1)

    if not edits:
        return "No training days fall in that window — enjoy the time away."
    _edit_workouts(ctx, edits, recorder)
    days = len(edits)
    return f"Cleared {days} training day{'s' if days != 1 else ''} while you're away."


def _handle_sick_injured(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    days = params.get("days")
    try:
        days = int(days) if days is not None else 3
    except (TypeError, ValueError):
        days = 3
    days = max(1, min(days, 21))

    # 1. Rest the immediate window (today onwards).
    edits: Dict[Tuple[int, int], "_RestEdit"] = {}
    cursor = today_date()
    end = cursor + timedelta(days=days - 1)
    while cursor <= end:
        target = _date_to_week_day(ctx, cursor)
        if target is not None:
            edits[target] = _RestEdit("Resting — sick / injured.")
        cursor += timedelta(days=1)
    if edits:
        _edit_workouts(ctx, edits, recorder)

    # 2. Ramp the weeks that follow the rest window back up gently.
    _ramp_future_weeks(ctx, recorder)

    return (
        "Rested the next few days and rebuilt the following weeks with a gentler "
        "ramp — ease back as you recover."
    )


def _handle_feeling_strong(
    ctx: _IntentContext, params: Dict[str, Any], recorder: List[Dict[str, Any]]
) -> str:
    weeks = _future_week_rows(ctx)
    if not weeks:
        return "No upcoming weeks to build on — keep it up."
    apply_adjustment_to_future_weeks(
        ctx.plan,
        weeks,
        _STRONG_FACTOR,
        ctx.db,
        current_week=ctx.current_week,
        current_day_of_week=ctx.current_dow,
        recorder=recorder,
    )
    pct = round((_STRONG_FACTOR - 1.0) * 100)
    return f"Bumped your upcoming easy/long volume about {pct}% — you're flying."


_HANDLERS: Dict[
    str, Callable[[_IntentContext, Dict[str, Any], List[Dict[str, Any]]], str]
] = {
    "feeling_tired": _handle_feeling_tired,
    "busy_week": _handle_busy_week,
    "skip_run": _handle_skip_run,
    "away": _handle_away,
    "sick_injured": _handle_sick_injured,
    "feeling_strong": _handle_feeling_strong,
}


# ---------------------------------------------------------------------------
# Mutation primitives
# ---------------------------------------------------------------------------


@dataclass
class _RestEdit:
    """Turn a workout into a rest day."""

    reason: str
    kind: str = "rest"


@dataclass
class _EaseEdit:
    """Scale a workout down from baseline and drop hard sessions to easy."""

    factor: float
    reason: str
    kind: str = "ease"


def _ease_rest_of_week(
    ctx: _IntentContext, factor: float, reason: str
) -> Dict[Tuple[int, int], _EaseEdit]:
    """Ease every remaining day of the current week (today onwards)."""
    return {
        (ctx.current_week, day): _EaseEdit(factor, reason)
        for day in range(ctx.current_dow, 8)
    }


def _edit_workouts(
    ctx: _IntentContext,
    edits: Dict[Tuple[int, int], Any],
    recorder: List[Dict[str, Any]],
) -> None:
    """Apply per-workout rest/ease edits to the ORM and plan_data in-session.

    Mutations are computed from each workout's frozen baseline so repeated
    intents never compound. Updates week totals, mirrors plan_data, appends
    recorder hints, and bumps the adaptation revision when anything changes.
    """
    if not edits:
        return

    plan = ctx.plan
    db = ctx.db
    plan_data, pd_week, pd_workout = parse_plan_data_lookups(plan)
    week_numbers = {wk for (wk, _day) in edits}
    weekly_plans = {
        wp.week_number: wp
        for wp in db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number.in_(week_numbers),
        )
        .all()
    }
    workouts_by_week = batch_workouts_by_week(
        [wp.id for wp in weekly_plans.values()], db
    )

    any_changed = False
    for wk_num, weekly_plan in weekly_plans.items():
        workouts = workouts_by_week.get(weekly_plan.id, [])
        week_changed = False
        for workout in workouts:
            edit = edits.get((wk_num, workout.day_of_week))
            if edit is None:
                continue
            if _apply_single_edit(
                workout,
                edit,
                pd_workout.get((wk_num, workout.day_of_week)),
                wk_num,
                recorder,
            ):
                week_changed = True
                any_changed = True
        if week_changed:
            new_total = round(sum(w.distance_km or 0 for w in workouts), 1)
            weekly_plan.total_km = new_total
            if wk_num in pd_week:
                pd_week[wk_num]["total_km"] = new_total

    plan.plan_data = plan_data
    persist_json(plan, "plan_data")
    if any_changed:
        plan.adaptation_revision = (plan.adaptation_revision or 0) + 1


def _apply_single_edit(
    workout: DailyWorkout,
    edit: Any,
    pd_wo: Optional[Dict[str, Any]],
    week_number: int,
    recorder: List[Dict[str, Any]],
) -> bool:
    """Mutate one workout in place. Returns True if anything changed."""
    if workout.baseline_distance_km is None and workout.distance_km:
        workout.baseline_distance_km = workout.distance_km

    old_dist = workout.distance_km or 0.0
    old_type = workout.workout_type

    if edit.kind == "rest":
        if old_type == "rest" and old_dist == 0:
            return False
        new_dist = 0.0
        new_type = "rest"
        new_intensity = "low"
    else:  # ease
        base = workout.baseline_distance_km or workout.distance_km or 0.0
        if base <= 0 or old_type == "rest":
            return False
        new_dist = round(base * edit.factor, 1)
        new_type = "easy" if old_type in _HARD_TYPES else old_type
        new_intensity = "low"

    if new_dist == old_dist and new_type == old_type:
        return False

    clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
    note = edit.reason or clean_notes or None

    workout.distance_km = new_dist
    workout.workout_type = new_type
    workout.intensity = new_intensity
    workout.notes = note

    if pd_wo is not None:
        pd_wo["distance"] = new_dist
        pd_wo["type"] = new_type
        pd_wo["intensity"] = new_intensity
        pd_wo["notes"] = note

    recorder.append(
        {
            "week": week_number,
            "day": workout.day_of_week,
            "type": old_type,
            "old_distance_km": old_dist,
            "new_distance_km": new_dist,
            "delta_km": round(new_dist - old_dist, 2),
            "status": "changed",
            "reason": edit.reason,
        }
    )
    return True


def _ramp_future_weeks(ctx: _IntentContext, recorder: List[Dict[str, Any]]) -> None:
    """Ease only the first weeks back, then leave the rest of the plan intact.

    Weeks within the short return window are scaled down by
    ``_SICK_RETURN_RAMP``; every later week keeps its original prescription
    (no adjustment), so an illness no longer suppresses the entire plan.
    """
    weeks = _future_week_rows(ctx)
    if not weeks:
        return
    for week in weeks:
        idx = week.week_number - ctx.current_week - 1  # 0 = first week back
        if idx < 0 or idx >= len(_SICK_RETURN_RAMP):
            continue  # outside the easing window — leave at baseline
        apply_adjustment_to_future_weeks(
            ctx.plan,
            [week],
            _SICK_RETURN_RAMP[idx],
            ctx.db,
            current_week=ctx.current_week,
            current_day_of_week=ctx.current_dow,
            recorder=recorder,
        )


def _future_week_rows(ctx: _IntentContext) -> List[WeeklyPlan]:
    rows = (
        ctx.db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == ctx.plan.id,
            WeeklyPlan.week_number > ctx.current_week,
        )
        .order_by(WeeklyPlan.week_number)
        .all()
    )
    return rows


# ---------------------------------------------------------------------------
# Date / day resolution
# ---------------------------------------------------------------------------


def _coerce_date(value: Any) -> Optional[date_cls]:
    """Coerce a date/datetime/ISO-string into a plain date, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return date_cls.fromisoformat(value[:10])
        except ValueError:
            return None
    return _to_date(value)


def _resolve_day(
    ctx: _IntentContext, date_str: Optional[Any]
) -> Optional[Tuple[int, int]]:
    """Resolve a target (week, day) from an optional ISO date.

    Defaults to today when no date is supplied (the "skip today" case).
    """
    if not date_str:
        return (ctx.current_week, ctx.current_dow)
    target_date = _coerce_date(date_str)
    if target_date is None:
        return (ctx.current_week, ctx.current_dow)
    return _date_to_week_day(ctx, target_date)


def _date_to_week_day(ctx: _IntentContext, target) -> Optional[Tuple[int, int]]:
    """Map a calendar date to a (week_number, day_of_week) in this plan."""
    start = _to_date(ctx.plan.start_date)
    if start is None:
        return None
    days_elapsed = (target - start).days
    if days_elapsed < 0:
        return None
    week = days_elapsed // 7 + 1
    day = days_elapsed % 7 + 1
    total_weeks = ctx.plan.weeks_duration or 0
    if total_weeks and week > total_weeks:
        return None
    return (week, day)
