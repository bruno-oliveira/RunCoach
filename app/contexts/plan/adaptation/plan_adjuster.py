"""Plan adjustment — scale future workout distances based on performance."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.plan_date_utils import compute_current_week
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.models import (
    DailyWorkout,
    ReadinessLog,
    RunFeedback,
    RunLog,
    TrainingPlan,
    WeeklyPlan,
)
from app.utils import persist_json
from app.utils import to_date as _to_date

from . import change_reasons as _reasons
from ._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    batch_workouts_by_week,
    is_current_week_in_progress,
    parse_plan_data_lookups,
    today_date,
)
from .adjustment_results import (
    build_no_adjustable_weeks_result as _build_no_adjustable_weeks_result,
)
from .adjustment_results import (
    build_signal_snapshot as _build_signal_snapshot,
)
from .adjustment_results import (
    build_signals_summary as _build_signals_summary,
)
from .adjustment_results import (
    record_adaptation_event as _record_adaptation_event,
)
from .change_plan_builder import (
    build_change_plan,
    empty_change_plan,
    snapshot_workouts,
)
from .fitness_signals import FitnessSignalsProvider, default_provider
from .precondition_guards import check_preconditions_or_gather
from .reason_builder import build_headline_reason, compute_net_delta_km
from .run_mapper import map_runs_to_plan
from .signal_computer import compute_adjustment_signals
from .tuning import RECENCY_HALF_LIFE_WEEKS
from .week_adjuster import apply_adjustment_stage

# ``_build_signal_snapshot`` is also imported by tests/test_services
# and referenced in app/application/coach_summary_service.py — keep the
# underscore alias here so external callers continue to find it.

logger = logging.getLogger(__name__)


def gather_signals(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    run_map: bool = True,
    fitness_provider: Optional[FitnessSignalsProvider] = None,
) -> Optional[Dict[str, Any]]:
    """Gather runs, workouts, and compute adjustment signals.

    Returns None if insufficient data, otherwise a dict with signals,
    current_week, all_plan_runs, adjustable_weeks, and training_plan.

    ``fitness_provider`` injects VDOT-trend, training-load, and
    mountain-simulation callables. Defaults to the runner-context
    implementations via ``default_provider`` — tests override to avoid
    pulling in the runner context.
    """
    provider = fitness_provider or default_provider()
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return None

    if run_map:
        map_runs_to_plan(plan_id, user_id, db)
    backfill_baselines(training_plan, db)

    hr_zones = None
    if training_plan.hr_zones_data:
        try:
            hr_zones = training_plan.hr_zones_data.get("zones")
        except (AttributeError, TypeError):
            pass

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    current_week = compute_current_week(start_date, today, clamp_min=1, pre_start=1)

    all_plan_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan_id).all()

    run_ids = [run.id for run in all_plan_runs]
    run_feedback_list = (
        (db.query(RunFeedback).filter(RunFeedback.run_log_id.in_(run_ids)).all())
        if run_ids
        else []
    )

    readiness_logs = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == user_id,
            ReadinessLog.log_date >= today_date() - timedelta(days=14),
        )
        .order_by(ReadinessLog.log_date.desc())
        .limit(14)
        .all()
    )

    if len(all_plan_runs) < 3:
        return None

    half_life_weeks = RECENCY_HALF_LIFE_WEEKS

    def _recency_weight(scheduled_date):
        weeks_ago = max(0, (today - scheduled_date).days) / 7.0
        return 2.0 ** (-weeks_ago / half_life_weeks)

    all_workouts_with_week = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            DailyWorkout.workout_type != "rest",
        )
        .all()
    )

    past_workouts: List[Tuple] = []
    past_workout_ids: set = set()
    for workout, week_number in all_workouts_with_week:
        scheduled_date = start_date + timedelta(
            weeks=(week_number - 1),
            days=(workout.day_of_week - 1),
        )
        if scheduled_date <= today:
            past_workouts.append((workout, scheduled_date))
            past_workout_ids.add(workout.id)

    if not past_workouts:
        return None

    vdot_trend = "stable"
    try:
        vdot_history = provider.get_vdot_history(user_id, weeks=8, db=db)
        vdot_trend = provider.calculate_vdot_trend(vdot_history)
    except Exception as e:
        logger.warning("VDOT trend lookup failed (non-fatal): %s", e)

    training_load = None
    try:
        training_load = provider.get_training_load(user_id, db, lookback_days=42)
    except Exception as e:
        logger.warning("Training load lookup failed (non-fatal): %s", e)

    signals = compute_adjustment_signals(
        all_plan_runs,
        past_workouts,
        past_workout_ids,
        today,
        plan_id,
        db,
        _recency_weight,
        current_phase=_get_current_phase(training_plan, current_week),
        adaptation_history=training_plan.adaptation_history,
        hr_zones=hr_zones,
        run_feedback_list=run_feedback_list,
        vdot_trend=vdot_trend,
        readiness_logs=readiness_logs,
        training_load=training_load,
        mountain_simulation=provider.score_mountain_simulation(
            training_plan.plan_data or [],
            all_plan_runs,
            start_date,
            current_week,
            is_trail=getattr(training_plan, "is_trail", False),
            training_terrain=getattr(training_plan, "training_terrain", None),
            target_elevation_gain_m=getattr(
                training_plan, "target_elevation_gain_m", None
            ),
            plan_id=training_plan.id,
        ),
    )

    current_day_of_week = today.isoweekday()
    in_progress = is_current_week_in_progress(
        plan_id,
        start_date,
        current_week,
        current_day_of_week,
        db,
    )
    first_adjustable_week = current_week + 1 if in_progress else current_week
    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= first_adjustable_week,
        )
        .all()
    )

    return {
        "training_plan": training_plan,
        "signals": signals,
        "all_plan_runs": all_plan_runs,
        "current_week": current_week,
        "current_day_of_week": current_day_of_week,
        "current_week_in_progress": in_progress,
        "first_adjustable_week": first_adjustable_week,
        "adjustable_weeks": adjustable_weeks,
    }


def preview_adjust_signals(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Read-only: the full adaptation signal breakdown, without any writes.

    Unlike ``preview_adjust_plan`` (which mutates then rolls back), this
    calls ``gather_signals`` with ``run_map=False`` so no run→workout
    mapping is committed — safe to call on a GET request. Returns the
    complete ``compute_adjustment_signals`` dict (every factor, weight,
    TSB/form, trends) plus ``current_week`` and ``adjustable_week_count``,
    or ``None`` when there is insufficient data (fewer than 3 linked runs,
    no start date, or no past workouts to evaluate).
    """
    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None
    signals = dict(gathered["signals"])
    signals["current_week"] = gathered["current_week"]
    signals["adjustable_week_count"] = len(gathered["adjustable_weeks"])
    return signals


def adjust_plan(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Adjust future plan weeks using full-history weighted signals."""
    return _run_adjust(plan_id, user_id, db, mode="applied")


def preview_adjust_plan(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Compute what an Adjust Plan would do without persisting.

    Performs the same mutations as `adjust_plan` against the SQLAlchemy
    session, captures the resulting ChangePlan, then rolls back the
    session and expires loaded ORM objects so no preview state leaks.
    """
    try:
        result = _run_adjust(plan_id, user_id, db, mode="preview")
    finally:
        db.rollback()
        db.expire_all()
    return result["change_plan"] if "change_plan" in result else result


def _run_adjust(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    mode: str,
) -> Dict[str, Any]:
    early, gathered = check_preconditions_or_gather(plan_id, user_id, db, mode=mode)
    if early is not None:
        return early
    assert gathered is not None  # narrows for type checkers; tuple invariant

    training_plan = gathered["training_plan"]
    signals = gathered["signals"]
    all_plan_runs = gathered["all_plan_runs"]
    current_week = gathered["current_week"]
    current_day_of_week = gathered["current_day_of_week"]
    adjustable_weeks = gathered["adjustable_weeks"]
    in_progress = gathered["current_week_in_progress"]
    multiplier = signals["multiplier"]

    # Clear any pending recommendation since the user is manually adjusting
    # (preview mode rolls this back).
    training_plan.pending_recommendation = None

    week_numbers = [w.week_number for w in adjustable_weeks]

    if not adjustable_weeks:
        return _build_no_adjustable_weeks_result(
            mode=mode,
            signals=signals,
            runs_count=len(all_plan_runs),
        )

    applied = apply_adjustment_stage(
        training_plan,
        adjustable_weeks,
        multiplier=multiplier,
        per_type_ratios=signals.get("per_type_ratios"),
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        user_id=user_id,
        db=db,
        week_numbers=week_numbers,
    )

    direction = (
        "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
    )
    headline_reason = build_headline_reason(
        signals=signals,
        vdot_result=applied.vdot_result,
        net_delta_km=compute_net_delta_km(applied.before, applied.after),
        multiplier=multiplier,
        in_progress=in_progress,
        current_week=current_week,
        has_adjustable_weeks=bool(adjustable_weeks),
    )

    vdot_change_payload = None
    if applied.vdot_result:
        vdot_change_payload = {
            "before": applied.vdot_result.get("old_vdot"),
            "after": applied.vdot_result.get("new_vdot"),
            "direction": applied.vdot_result.get("direction"),
        }

    change_plan = build_change_plan(
        action="adjust",
        mode=mode,
        training_plan=training_plan,
        before=applied.before,
        after=applied.after,
        recorder=applied.recorder,
        signals=_build_signals_summary(signals, runs_count=len(all_plan_runs)),
        multiplier=multiplier,
        vdot_change=vdot_change_payload,
        headline_reason=headline_reason,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
    )

    if mode == "applied":
        training_plan.adjustment_multiplier = multiplier
        training_plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        training_plan.last_change_plan = change_plan
        _record_adaptation_event(
            training_plan,
            {
                "type": "adjust",
                "multiplier": multiplier,
                "direction": direction,
                "effort_trend": signals.get("effort_trend", "stable"),
                "overreach": signals.get("overreach_detected", False),
                "phase": signals.get("current_phase", "build"),
                "reason": headline_reason,
                "signals_snapshot": _build_signal_snapshot(signals),
            },
        )
        db.commit()

        avg_effort = signals["avg_effort"]
        logger.info(
            "adjust_plan applied: multiplier=%.2f raw=%.3f "
            "volume_ratio=%.2f effort_factor=%.2f(avg=%.1f) "
            "completion_factor=%.2f(rate=%.2f) trend=%s overreach=%s runs=%d phase=%s "
            "workouts_changed=%d weeks_changed=%d",
            multiplier,
            signals["raw_multiplier"],
            signals["volume_ratio"],
            signals["effort_factor"],
            avg_effort if avg_effort is not None else 0,
            signals["completion_factor"],
            signals["completion_rate"],
            signals.get("effort_trend", "stable"),
            signals.get("overreach_detected", False),
            len(all_plan_runs),
            signals.get("current_phase", "build"),
            change_plan["summary"]["workouts_changed_count"],
            applied.weeks_changed,
        )

    result = {
        "adjusted": applied.any_distance_changed or bool(applied.vdot_result),
        **signals,
        "total_runs": len(all_plan_runs),
        "weeks_changed": applied.weeks_changed,
        "reason": headline_reason,
        "change_plan": change_plan,
    }
    if applied.vdot_result:
        result["vdot_recalibration"] = applied.vdot_result
    return result


def _get_current_phase(training_plan: TrainingPlan, current_week: int) -> str:
    plan_data = training_plan.plan_data or []
    for week in plan_data:
        if week.get("week") == current_week:
            return week.get("phase", "build")
    return "build"


def reset_adjustment(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Reset plan to original baseline distances, removing any adjustment."""
    return _run_reset(plan_id, user_id, db, mode="applied")


def preview_reset_adjustment(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Preview the reset action without persisting."""
    try:
        result = _run_reset(plan_id, user_id, db, mode="preview")
    finally:
        db.rollback()
        db.expire_all()
    return result["change_plan"] if "change_plan" in result else result


def _run_reset(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    mode: str,
) -> Dict[str, Any]:
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan:
        cp = empty_change_plan(
            action="reset",
            mode=mode,
            headline_reason="Plan not found.",
        )
        return {"reset": False, "reason": "Plan not found", "change_plan": cp}

    has_adjustment = training_plan.adjustment_multiplier is not None
    has_recalibration = training_plan.last_recalibrated_at is not None

    if not has_adjustment and not has_recalibration:
        cp = empty_change_plan(
            action="reset",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_NO_ACTIVE_ADJUSTMENT,
        )
        return {
            "reset": False,
            "reason": "Plan has no active adjustment.",
            "change_plan": cp,
        }

    # Reset restores distance = baseline_distance_km, so a baseline frozen to
    # an already-adjusted value would restore the inflated distance. Normalize
    # first (recovers true baselines, strips stale notes) so reset returns the
    # genuine originals. Reset does not go through gather_signals, so this is
    # the only place the normalize pass runs for this flow.
    backfill_baselines(training_plan, db)

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    all_weeks = (
        db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan_id).all()
    )

    workouts_by_week_map = batch_workouts_by_week([week.id for week in all_weeks], db)

    before = snapshot_workouts(training_plan, db)

    weeks_changed = 0
    for week in all_weeks:
        workouts = workouts_by_week_map.get(week.id, [])
        week_changed = False

        for workout in workouts:
            if not workout.baseline_distance_km:
                clean = ANNOTATION_RE.sub("", workout.notes or "").strip()
                if clean != (workout.notes or "").strip():
                    workout.notes = clean or None
                continue

            if workout.distance_km != workout.baseline_distance_km:
                workout.distance_km = workout.baseline_distance_km
                week_changed = True

            clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
            workout.notes = clean_notes or None

            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = workout.baseline_distance_km
                pd_clean = ANNOTATION_RE.sub(
                    "",
                    pd_wo.get("notes", pd_wo.get("description", "")),
                ).strip()
                pd_wo["notes"] = pd_clean

        if week_changed:
            weeks_changed += 1
            new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.plan_data = plan_data
    persist_json(training_plan, "plan_data")

    after = snapshot_workouts(training_plan, db)

    change_plan = build_change_plan(
        action="reset",
        mode=mode,
        training_plan=training_plan,
        before=before,
        after=after,
        recorder=None,
        signals={},
        multiplier=None,
        vdot_change=None,
        headline_reason="Plan restored to original baseline distances.",
    )

    if mode == "applied":
        training_plan.adjustment_multiplier = None
        training_plan.last_recalibrated_at = None
        training_plan.last_change_plan = change_plan
        _record_adaptation_event(
            training_plan,
            {
                "type": "reset",
                "weeks_changed": weeks_changed,
                "reason": "Plan restored to original baseline distances.",
            },
        )
        db.commit()

    return {
        "reset": True,
        "weeks_changed": weeks_changed,
        "reason": "Plan restored to original distances.",
        "change_plan": change_plan,
    }
