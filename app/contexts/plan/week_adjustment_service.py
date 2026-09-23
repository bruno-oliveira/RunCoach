"""Domain logic for per-week plan overrides.

All distance-mutating actions route through the single
``apply_adjustment_to_future_weeks`` pipeline so they share one baseline
model, one safety stack, and the adaptation revision bump. The reset
actions (``skip_bump``, ``reset_week``) restore baseline directly.
"""

from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    parse_plan_data_lookups,
    today_date,
)
from app.contexts.plan.adaptation.finalize import finalize_plan_mutation
from app.contexts.plan.adaptation.week_adjuster import apply_adjustment_to_future_weeks
from app.core.training.periodization.plan_calendar import compute_current_week
from app.exceptions import ConflictException, NotFoundException, ValidationException
from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

_BUMP_MULTIPLIER = 1.08
_REDUCE_MULTIPLIER = 0.70
_EASE_DEFICIT_MULTIPLIER = 0.85
_EXTEND_LONG_RUN_KM = 2.0

# Sessions that shouldn't land on consecutive days after a manual swap.
_DEMANDING_TYPES = frozenset(
    {"interval", "tempo", "threshold", "vo2max", "race_pace", "fartlek", "hill", "long"}
)
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def get_week_workouts(plan_id: str, week_number: int, db: Session):
    """Fetch weekly plan and its workouts."""
    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .first()
    )
    if not weekly_plan:
        return None, []
    workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
        .all()
    )
    return weekly_plan, workouts


def apply_week_action(
    action: str,
    training_plan: TrainingPlan,
    plan_data: list,
    week_data: dict,
    week_number: int,
    plan_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Dispatch and execute a per-week override action.

    Returns a payload the router can include in the response so the
    client can patch the DOM without a reload.
    """
    if action == "skip_bump":
        return _restore_baseline(
            training_plan, plan_id, week_number, db, clear_baseline=False
        )
    if action == "reset_week":
        return _restore_baseline(
            training_plan, plan_id, week_number, db, clear_baseline=True
        )
    if action == "bump":
        return _multiplier_action(
            training_plan,
            plan_id,
            [week_number],
            _BUMP_MULTIPLIER,
            db,
        )
    if action == "reduce_30":
        target_weeks = [week_number, week_number + 1]
        return _multiplier_action(
            training_plan,
            plan_id,
            target_weeks,
            _REDUCE_MULTIPLIER,
            db,
        )
    if action == "ease_deficit":
        return _multiplier_action(
            training_plan,
            plan_id,
            [week_number],
            _EASE_DEFICIT_MULTIPLIER,
            db,
        )
    if action == "extend_long_run":
        return _extend_long_run(training_plan, plan_id, week_number, db)
    raise ValidationException(f"Unknown action: {action}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _select_weeks(
    plan_id: str,
    week_numbers: List[int],
    db: Session,
) -> List[WeeklyPlan]:
    if not week_numbers:
        return []
    rows = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number.in_(week_numbers),
        )
        .all()
    )
    rows.sort(key=lambda w: w.week_number)
    return rows


def _current_week_pos(training_plan: TrainingPlan) -> Tuple[int | None, int | None]:
    """Today's plan week + isoweekday, or (None, None) if plan hasn't started."""
    if not training_plan.start_date:
        return None, None
    start = _to_date(training_plan.start_date)
    today = today_date()
    week = compute_current_week(start, today, clamp_min=1)
    if week is None:
        return None, None
    return week, today.isoweekday()


def _multiplier_action(
    training_plan: TrainingPlan,
    plan_id: str,
    week_numbers: List[int],
    multiplier: float,
    db: Session,
) -> Dict[str, Any]:
    """Apply ``multiplier`` (from baseline) to the named weeks."""
    weeks = _select_weeks(plan_id, week_numbers, db)
    if not weeks:
        raise NotFoundException("Week not found in plan")

    backfill_baselines(training_plan, db)

    current_week, current_dow = _current_week_pos(training_plan)
    recorder: List[Dict[str, Any]] = []
    weeks_changed, any_changed, _counts = apply_adjustment_to_future_weeks(
        training_plan,
        weeks,
        multiplier,
        db,
        current_week=current_week,
        current_day_of_week=current_dow,
        recorder=recorder,
    )

    return _build_response(training_plan, weeks, recorder, weeks_changed, any_changed)


def _extend_long_run(
    training_plan: TrainingPlan,
    plan_id: str,
    week_number: int,
    db: Session,
) -> Dict[str, Any]:
    """Bump the long run by ~2 km, capped at baseline × 1.25.

    Computed as a long-only per-type ratio so the math runs through the
    single mutation path (and the baseline cap protects against stacking).
    """
    weeks = _select_weeks(plan_id, [week_number], db)
    if not weeks:
        raise NotFoundException("Week not found in plan")

    backfill_baselines(training_plan, db)
    week_obj = weeks[0]
    long_wo = (
        db.query(DailyWorkout)
        .filter(
            DailyWorkout.weekly_plan_id == week_obj.id,
            DailyWorkout.workout_type == "long",
        )
        .first()
    )
    if not long_wo or not (long_wo.baseline_distance_km or long_wo.distance_km):
        return _build_response(training_plan, weeks, [], 0, False)

    base = long_wo.baseline_distance_km or long_wo.distance_km
    if base <= 0:
        return _build_response(training_plan, weeks, [], 0, False)

    ratio = 1.0 + (_EXTEND_LONG_RUN_KM / base)
    current_week, current_dow = _current_week_pos(training_plan)
    recorder: List[Dict[str, Any]] = []
    weeks_changed, any_changed, _counts = apply_adjustment_to_future_weeks(
        training_plan,
        weeks,
        1.0,
        db,
        current_week=current_week,
        current_day_of_week=current_dow,
        per_type_ratios={"long": ratio},
        recorder=recorder,
    )
    return _build_response(training_plan, weeks, recorder, weeks_changed, any_changed)


def _restore_baseline(
    training_plan: TrainingPlan,
    plan_id: str,
    week_number: int,
    db: Session,
    *,
    clear_baseline: bool,
) -> Dict[str, Any]:
    """Restore the named week's workouts to baseline distances."""
    weeks = _select_weeks(plan_id, [week_number], db)
    if not weeks:
        raise NotFoundException("Week not found in plan")

    week_obj = weeks[0]
    workouts = (
        db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == week_obj.id).all()
    )

    plan_data = training_plan.plan_data or []
    pd_week = next((w for w in plan_data if w.get("week") == week_number), None)
    pd_workouts = {
        wo.get("day"): wo for wo in (pd_week or {}).get("daily_workouts", [])
    }

    recorder: List[Dict[str, Any]] = []
    any_changed = False
    for wo in workouts:
        baseline = wo.baseline_distance_km
        if baseline is None:
            clean = ANNOTATION_RE.sub("", wo.notes or "").strip()
            if clean != (wo.notes or "").strip():
                wo.notes = clean or None
            continue
        old = wo.distance_km
        if old != baseline:
            recorder.append(
                {
                    "week": week_number,
                    "day": wo.day_of_week,
                    "type": wo.workout_type,
                    "old_distance_km": old,
                    "new_distance_km": baseline,
                    "delta_km": round(baseline - (old or 0), 2),
                    "status": "changed",
                    "reason": None,
                }
            )
            wo.distance_km = baseline
            any_changed = True
        clean_notes = ANNOTATION_RE.sub("", wo.notes or "").strip()
        wo.notes = clean_notes or None
        if clear_baseline:
            wo.baseline_distance_km = None
        pd_wo = pd_workouts.get(wo.day_of_week)
        if pd_wo is not None:
            pd_clean = ANNOTATION_RE.sub(
                "",
                pd_wo.get("notes", pd_wo.get("description", "")),
            ).strip()
            pd_wo["notes"] = pd_clean

    # Restoring the distance alone left the adjusted steps behind, and the
    # page re-derives a card's distance from its steps — so a reset week
    # still rendered (and exported) the adjusted session.
    finalize_plan_mutation(
        training_plan, db, week_numbers=[week_number], bump_revision=any_changed
    )
    return _build_response(
        training_plan, weeks, recorder, 1 if any_changed else 0, any_changed
    )


def _build_response(
    training_plan: TrainingPlan,
    weeks: List[WeeklyPlan],
    recorder: List[Dict[str, Any]],
    weeks_changed: int,
    any_changed: bool,
) -> Dict[str, Any]:
    workout_changes = [r for r in recorder if r.get("status") == "changed"]
    return {
        "adaptation_revision": training_plan.adaptation_revision or 0,
        "any_distance_changed": any_changed,
        "weeks_changed": weeks_changed,
        "week_totals": [
            {"week": w.week_number, "total_km": w.total_km or 0.0} for w in weeks
        ],
        "workout_changes": [
            {
                "week": c["week"],
                "day": c["day"],
                "new_distance_km": c["new_distance_km"],
            }
            for c in workout_changes
        ],
    }


def swap_week_days(
    training_plan: TrainingPlan,
    week_number: int,
    source_day: int,
    target_day: int,
    db: Session,
) -> Dict[str, Any]:
    """Swap two days of one week, in the ORM and plan_data together.

    The two representations used to be swapped separately, and the JSON half
    silently refused to move a race while the ORM half moved it anyway — the
    rows and the cards then disagreed about which session lived on which day,
    cross-wiring workout ids and run matching. Both halves now pass or fail
    as one, and race day is refused outright.

    Returns:
        ``adaptation_revision`` plus an optional ``warning`` when the swap puts
        two demanding sessions back to back — allowed, but worth saying.
    """
    if not (1 <= source_day <= 7 and 1 <= target_day <= 7):
        raise ValidationException("Days must be between 1 (Mon) and 7 (Sun).")
    if source_day == target_day:
        return {"adaptation_revision": training_plan.adaptation_revision or 0}

    weeks = _select_weeks(training_plan.id, [week_number], db)
    if not weeks:
        raise NotFoundException("Week not found in plan")
    rows = {
        w.day_of_week: w
        for w in db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == weeks[0].id)
        .all()
    }
    _plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)
    src, tgt = rows.get(source_day), rows.get(target_day)
    src_card = pd_workout.get((week_number, source_day))
    tgt_card = pd_workout.get((week_number, target_day))
    if src is None or tgt is None or src_card is None or tgt_card is None:
        raise NotFoundException("That day isn't part of this week of your plan.")

    types = {
        src.workout_type,
        tgt.workout_type,
        src_card.get("type"),
        tgt_card.get("type"),
    }
    if "race" in types:
        raise ConflictException(
            "Race day is fixed — it can't be swapped with another day."
        )

    src.day_of_week, tgt.day_of_week = target_day, source_day
    src_card["day"], tgt_card["day"] = target_day, source_day
    week = pd_week.get(week_number)
    if week is not None:
        week["daily_workouts"] = sorted(
            week.get("daily_workouts", []), key=lambda w: w.get("day", 0)
        )
    finalize_plan_mutation(training_plan, db, week_numbers=[week_number])

    payload: Dict[str, Any] = {
        "adaptation_revision": training_plan.adaptation_revision or 0
    }
    warning = _back_to_back_warning(rows.values())
    if warning:
        payload["warning"] = warning
    return payload


def _back_to_back_warning(workouts) -> str | None:
    by_day = {
        int(w.day_of_week): w.workout_type
        for w in workouts
        if w.workout_type in _DEMANDING_TYPES and (w.distance_km or 0) > 0
    }
    for day in sorted(by_day):
        if day + 1 in by_day:
            return (
                f"{_DAY_NAMES[day - 1]} and {_DAY_NAMES[day]} are now both "
                "demanding sessions — keep one of them honest-easy if your legs "
                "feel it."
            )
    return None
