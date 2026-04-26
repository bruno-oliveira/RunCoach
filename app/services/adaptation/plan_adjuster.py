"""Plan adjustment — scale future workout distances based on performance."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, RunFeedback, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    batch_workouts_by_week,
    parse_plan_data_lookups,
    today_date,
)
from .run_mapper import map_runs_to_plan
from .signal_computer import compute_adjustment_signals
from .vdot_recalibrator import check_vdot_recalibration
from .week_adjuster import apply_adjustment_to_future_weeks

logger = logging.getLogger(__name__)


def adjust_plan(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Adjust future plan weeks using full-history weighted signals."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"adjusted": False, "reason": "Plan not found"}
    if not training_plan.start_date:
        return {"adjusted": False, "reason": "Plan has no start date."}

    map_runs_to_plan(plan_id, user_id, db)
    backfill_baselines(training_plan, db)

    # Fetch HR zones from training plan
    hr_zones = None
    if training_plan.hr_zones_data:
        try:
            hr_zones = training_plan.hr_zones_data.get("zones")
        except (AttributeError, TypeError):
            pass

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    days_elapsed = (today - start_date).days
    current_week = max(1, days_elapsed // 7 + 1)

    all_plan_runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == plan_id)
        .all()
    )

    # Fetch feedback for all runs
    run_ids = [run.id for run in all_plan_runs]
    run_feedback_list = (
        db.query(RunFeedback)
        .filter(RunFeedback.run_log_id.in_(run_ids))
        .all()
    ) if run_ids else []

    if len(all_plan_runs) < 3:
        return {
            "adjusted": False,
            "reason": "Not enough data (need at least 3 logged runs linked to this plan)",
            "total_runs": len(all_plan_runs),
        }

    half_life_weeks = 3.0

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
        return {"adjusted": False, "reason": "No past workouts to evaluate yet."}

    signals = compute_adjustment_signals(
        all_plan_runs, past_workouts, past_workout_ids,
        today, plan_id, db, _recency_weight,
        current_phase=_get_current_phase(training_plan, current_week),
        adaptation_history=training_plan.adaptation_history,
        hr_zones=hr_zones,
        run_feedback_list=run_feedback_list,
    )
    multiplier = signals["multiplier"]

    current_day_of_week = today.isoweekday()
    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= current_week,
        )
        .all()
    )

    if not adjustable_weeks:
        return {
            "adjusted": False,
            **{k: signals[k] for k in (
                "multiplier", "volume_ratio", "avg_effort", "completion_rate",
            )},
            "total_runs": len(all_plan_runs),
            "weeks_changed": 0,
            "reason": "No remaining workouts to adjust.",
        }

    weeks_changed, any_distance_changed = apply_adjustment_to_future_weeks(
        training_plan, adjustable_weeks, multiplier, db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=signals.get("per_type_ratios"),
    )

    vdot_result = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration failed (non-fatal): %s", e)

    training_plan.adjustment_multiplier = multiplier
    training_plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    volume_ratio = signals["volume_ratio"]
    completion_rate = signals["completion_rate"]
    avg_effort = signals["avg_effort"]
    effort_trend = signals.get("effort_trend", "stable")
    overreach_detected = signals.get("overreach_detected", False)
    current_phase = signals.get("current_phase", "build")
    phase_weights = signals.get("phase_weights", {})

    direction = "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
    reason_parts = [f"Remaining workouts {direction} (x{multiplier})."]
    reason_parts.append(
        f"Volume ratio: {round(volume_ratio, 2)}, "
        f"completion: {round(completion_rate * 100)}%."
    )
    if avg_effort is not None:
        reason_parts.append(f"Avg effort: {round(avg_effort, 1)}/10 (trend: {effort_trend}).")
    if overreach_detected:
        reason_parts.append("Overreach detected — forced reduction to protect recovery.")
    if vdot_result:
        reason_parts.append(
            f"VDOT recalibrated: {vdot_result['old_vdot']} → {vdot_result['new_vdot']} "
            f"({vdot_result['direction']})."
        )
    reason_parts.append(f"Phase: {current_phase} (weights: V={phase_weights.get('volume', 0):.0%} E={phase_weights.get('effort', 0):.0%} C={phase_weights.get('completion', 0):.0%}).")

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

    logger.info(
        "adjust_plan result: multiplier=%.2f raw=%.3f "
        "volume_ratio=%.2f effort_factor=%.2f(avg=%.1f) "
        "completion_factor=%.2f(rate=%.2f) trend=%s overreach=%s runs=%d phase=%s",
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
    )

    _record_adaptation_event(training_plan, {
        "type": "adjust",
        "multiplier": multiplier,
        "direction": direction,
        "effort_trend": effort_trend,
        "overreach": overreach_detected,
        "phase": current_phase,
        "reason": " ".join(reason_parts),
    })

    result = {
        "adjusted": any_distance_changed or bool(vdot_result),
        **signals,
        "total_runs": len(all_plan_runs),
        "weeks_changed": weeks_changed,
        "reason": " ".join(reason_parts),
    }
    if vdot_result:
        result["vdot_recalibration"] = vdot_result
    return result


def _record_adaptation_event(training_plan: TrainingPlan, event: Dict[str, Any]) -> None:
    event["date"] = today_date().isoformat()
    history = training_plan.adaptation_history or []
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
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"reset": False, "reason": "Plan not found"}

    has_adjustment = training_plan.adjustment_multiplier is not None
    has_recalibration = training_plan.last_recalibrated_at is not None

    if not has_adjustment and not has_recalibration:
        return {"reset": False, "reason": "Plan has no active adjustment."}

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    all_weeks = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    )

    workouts_by_week_map = batch_workouts_by_week(
        [week.id for week in all_weeks], db
    )

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
                    "", pd_wo.get("notes", pd_wo.get("description", "")),
                ).strip()
                pd_wo["notes"] = pd_clean

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.adjustment_multiplier = None
    training_plan.last_recalibrated_at = None
    training_plan.plan_data = plan_data
    db.commit()

    return {
        "reset": True,
        "weeks_changed": weeks_changed,
        "reason": "Plan restored to original distances.",
    }
