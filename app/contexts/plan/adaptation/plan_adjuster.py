"""Plan adjustment — scale future workout distances based on performance."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.plan_date_utils import compute_current_week
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.fitness.readiness_scoring import score_mountain_simulation
from app.contexts.runner.fitness.training_load_service import TrainingLoadService
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
from .change_plan_builder import (
    build_change_plan,
    empty_change_plan,
    snapshot_workouts,
)
from .run_mapper import map_runs_to_plan
from .signal_computer import compute_adjustment_signals
from .tuning import RECENCY_HALF_LIFE_WEEKS
from .vdot_recalibrator import check_vdot_recalibration
from .week_adjuster import apply_adjustment_to_future_weeks

logger = logging.getLogger(__name__)


def gather_signals(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    run_map: bool = True,
) -> Optional[Dict[str, Any]]:
    """Gather runs, workouts, and compute adjustment signals.

    Returns None if insufficient data, otherwise a dict with signals,
    current_week, all_plan_runs, adjustable_weeks, and training_plan.
    """
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
        vdot_history = RacePredictorService.get_vdot_history(
            user_id,
            weeks=8,
            db=db,
        )
        vdot_trend = RacePredictorService.calculate_vdot_trend(vdot_history)
    except Exception as e:
        logger.warning("VDOT trend lookup failed (non-fatal): %s", e)

    training_load = None
    try:
        training_load = TrainingLoadService.get_training_load(
            user_id,
            db,
            lookback_days=42,
        )
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
        mountain_simulation=score_mountain_simulation(
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
    gathered = gather_signals(plan_id, user_id, db)
    if gathered is None:
        training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
        if not training_plan:
            cp = empty_change_plan(
                action="adjust",
                mode=mode,
                headline_reason="Plan not found.",
            )
            return {"adjusted": False, "reason": "Plan not found", "change_plan": cp}
        if not training_plan.start_date:
            cp = empty_change_plan(
                action="adjust",
                mode=mode,
                headline_reason=_reasons.NO_CHANGE_PLAN_NOT_STARTED,
            )
            return {
                "adjusted": False,
                "reason": "Plan has no start date.",
                "change_plan": cp,
            }
        total_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan_id).count()
        if total_runs < 3:
            cp = empty_change_plan(
                action="adjust",
                mode=mode,
                headline_reason=_reasons.NO_CHANGE_INSUFFICIENT_DATA,
            )
            return {
                "adjusted": False,
                "reason": "Not enough data (need at least 3 logged runs linked to this plan)",
                "total_runs": total_runs,
                "change_plan": cp,
            }
        cp = empty_change_plan(
            action="adjust",
            mode=mode,
            headline_reason="No past workouts to evaluate yet.",
        )
        return {
            "adjusted": False,
            "reason": "No past workouts to evaluate yet.",
            "change_plan": cp,
        }

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
        cp = empty_change_plan(
            action="adjust",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_NO_REMAINING_WORKOUTS,
        )
        cp["summary"]["multiplier"] = multiplier
        cp["signals"] = _build_signals_summary(signals, runs_count=len(all_plan_runs))
        return {
            "adjusted": False,
            **{
                k: signals[k]
                for k in (
                    "multiplier",
                    "volume_ratio",
                    "avg_effort",
                    "completion_rate",
                )
            },
            "total_runs": len(all_plan_runs),
            "weeks_changed": 0,
            "reason": _reasons.NO_CHANGE_NO_REMAINING_WORKOUTS,
            "change_plan": cp,
        }

    before = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    recorder: List[Dict[str, Any]] = []
    weeks_changed, any_distance_changed, _counts = apply_adjustment_to_future_weeks(
        training_plan,
        adjustable_weeks,
        multiplier,
        db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=signals.get("per_type_ratios"),
        recorder=recorder,
    )

    vdot_result = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration failed (non-fatal): %s", e)

    after = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    volume_ratio = signals["volume_ratio"]
    completion_rate = signals["completion_rate"]
    avg_effort = signals["avg_effort"]
    effort_trend = signals.get("effort_trend", "stable")
    overreach_detected = signals.get("overreach_detected", False)
    current_phase = signals.get("current_phase", "build")
    phase_weights = signals.get("phase_weights", {})

    direction = (
        "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
    )
    # The user-facing verb has to track the actual net change. A baseline-
    # relative multiplier below 1.0 can still produce a net increase when a
    # previous, more aggressive adjustment had pulled distances further down
    # — so the modal showed "Reduced ... +26 km" until this was decoupled.
    net_delta_km = round(
        sum(
            (
                after.get(wid, {}).get("distance_km", 0.0)
                - before.get(wid, {}).get("distance_km", 0.0)
            )
            for wid in set(before) | set(after)
        ),
        1,
    )
    if net_delta_km > 0.05:
        verb = "increased"
    elif net_delta_km < -0.05:
        verb = "reduced"
    else:
        verb = "kept"
    reason_parts = [f"Remaining workouts {verb} (x{multiplier})."]
    reason_parts.append(
        f"Volume ratio: {round(volume_ratio, 2)}, "
        f"completion: {round(completion_rate * 100)}%."
    )
    if avg_effort is not None:
        reason_parts.append(
            f"Avg effort: {round(avg_effort, 1)}/10 (trend: {effort_trend})."
        )
    if overreach_detected:
        reason_parts.append(
            "Overreach detected — forced reduction to protect recovery."
        )
    if signals.get("vdot_trend") == "declining":
        reason_parts.append("VDOT declining — capping volume to prevent overtraining.")
    tsb_form = signals.get("tsb_form")
    if tsb_form:
        reason_parts.append(f"Form: {tsb_form} (TSB {signals.get('tsb')}).")
    if vdot_result:
        reason_parts.append(
            f"VDOT recalibrated: {vdot_result['old_vdot']} → {vdot_result['new_vdot']} "
            f"({vdot_result['direction']})."
        )
    reason_parts.append(
        f"Phase: {current_phase} (weights: V={phase_weights.get('volume', 0):.0%} E={phase_weights.get('effort', 0):.0%} C={phase_weights.get('completion', 0):.0%})."
    )

    hr_zone_adherence = signals.get("hr_zone_adherence")
    if hr_zone_adherence is not None:
        reason_parts.append(
            f"HR zone adherence: {round(hr_zone_adherence * 100)}% "
            f"(trend: {signals.get('hr_zone_trend', 'unknown')})."
        )

    warning_ratio = signals.get("warning_ratio")
    if warning_ratio is not None and warning_ratio > 0:
        reason_parts.append(
            f"Feedback warnings: {round(warning_ratio * 100)}% of runs."
        )

    mountain_score = signals.get("mountain_simulation_score")
    if mountain_score is not None:
        reason_parts.append(
            "Mountain simulation score: "
            f"{mountain_score}/100 (factor x{signals.get('mountain_simulation_factor', 1.0)})."
        )

    if in_progress and adjustable_weeks:
        reason_parts.insert(
            0,
            f"Current week {current_week} left in place — adjustments apply "
            f"from week {current_week + 1}.",
        )

    headline_reason = " ".join(reason_parts)

    vdot_change_payload = None
    if vdot_result:
        vdot_change_payload = {
            "before": vdot_result.get("old_vdot"),
            "after": vdot_result.get("new_vdot"),
            "direction": vdot_result.get("direction"),
        }

    change_plan = build_change_plan(
        action="adjust",
        mode=mode,
        training_plan=training_plan,
        before=before,
        after=after,
        recorder=recorder,
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
                "effort_trend": effort_trend,
                "overreach": overreach_detected,
                "phase": current_phase,
                "reason": headline_reason,
            },
        )
        db.commit()

        logger.info(
            "adjust_plan applied: multiplier=%.2f raw=%.3f "
            "volume_ratio=%.2f effort_factor=%.2f(avg=%.1f) "
            "completion_factor=%.2f(rate=%.2f) trend=%s overreach=%s runs=%d phase=%s "
            "workouts_changed=%d weeks_changed=%d",
            multiplier,
            signals["raw_multiplier"],
            volume_ratio,
            signals["effort_factor"],
            avg_effort if avg_effort is not None else 0,
            signals["completion_factor"],
            completion_rate,
            effort_trend,
            overreach_detected,
            len(all_plan_runs),
            current_phase,
            change_plan["summary"]["workouts_changed_count"],
            weeks_changed,
        )

    result = {
        "adjusted": any_distance_changed or bool(vdot_result),
        **signals,
        "total_runs": len(all_plan_runs),
        "weeks_changed": weeks_changed,
        "reason": headline_reason,
        "change_plan": change_plan,
    }
    if vdot_result:
        result["vdot_recalibration"] = vdot_result
    return result


def _build_signals_summary(
    signals: Dict[str, Any], *, runs_count: Optional[int] = None
) -> Dict[str, Any]:
    """Subset of signals safe to expose to the change-plan modal."""
    out = {
        "effort_trend": signals.get("effort_trend"),
        "completion_rate": signals.get("completion_rate"),
        "volume_ratio": signals.get("volume_ratio"),
        "phase": signals.get("current_phase"),
        "avg_effort": signals.get("avg_effort"),
        "tsb_form": signals.get("tsb_form"),
        "overreach_detected": signals.get("overreach_detected"),
    }
    if runs_count is not None:
        out["runs_analyzed"] = runs_count
    return out


def _record_adaptation_event(
    training_plan: TrainingPlan, event: Dict[str, Any]
) -> None:
    event["date"] = today_date().isoformat()
    history = list(training_plan.adaptation_history or [])
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history


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
