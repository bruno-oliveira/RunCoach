"""Auto-triggered adaptation recommendations.

Computes adjustment signals after a training week completes and stores
the result as a pending recommendation on the plan. The user can then
accept (apply) or dismiss it from the plan page.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.utils import to_date as _to_date

from ._helpers import today_date
from .plan_adjuster import gather_signals
from .vdot_recalibrator import check_vdot_recalibration
from .week_adjuster import apply_adjustment_to_future_weeks

logger = logging.getLogger(__name__)

MIN_RUNS_FOR_RECOMMENDATION = 3

# Minimum spacing between consecutive auto-adjustments. Manual adjustments are unaffected.
AUTO_ADJUST_THROTTLE = timedelta(hours=24)
# Confidence thresholds for the auto-adjust decision.
_HIGH_CONFIDENCE_DELTA = 0.05
_MED_CONFIDENCE_DELTA = 0.05


def evaluate_weekly_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Compute signals for the most recently completed week and store as pending recommendation.

    Returns the recommendation dict if created, None if skipped.
    """
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return None

    if training_plan.pending_recommendation and not force:
        return None

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    days_elapsed = (today - start_date).days
    if days_elapsed < 0:
        return None

    total_weeks = training_plan.weeks_duration or 0
    current_week = min(max(1, days_elapsed // 7 + 1), total_weeks)

    last_completed_week = current_week - 1 if current_week > 1 else None
    if last_completed_week is None:
        return None

    if (
        not force
        and training_plan.last_recommendation_week is not None
        and training_plan.last_recommendation_week >= last_completed_week
    ):
        return None

    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None

    signals = gathered["signals"]
    multiplier = signals["multiplier"]

    if abs(multiplier - 1.0) < 0.02:
        training_plan.last_recommendation_week = last_completed_week
        db.commit()
        return None

    direction = "increase" if multiplier > 1.0 else "reduce"
    pct = abs(round((multiplier - 1.0) * 100))

    reason = (
        f"Based on your week {last_completed_week} performance, "
        f"we recommend {'increasing' if direction == 'increase' else 'reducing'} "
        f"your training by {pct}%."
    )

    volume_ratio = signals.get("volume_ratio", 1.0)
    completion_rate = signals.get("completion_rate", 0)
    avg_effort = signals.get("avg_effort")

    details = []
    if volume_ratio > 1.1:
        details.append("You've been exceeding volume targets.")
    elif volume_ratio < 0.85:
        details.append("Volume has been below target.")
    if completion_rate < 0.7:
        details.append(f"Completion rate is {round(completion_rate * 100)}%.")
    if avg_effort is not None and avg_effort > 7.5:
        details.append(f"Effort is trending high ({avg_effort:.1f}/10).")
    if signals.get("overreach_detected"):
        details.append("Overreach signals detected — recovery prioritized.")
    if details:
        reason += " " + " ".join(details)

    recommendation = {
        "week_evaluated": last_completed_week,
        "multiplier": multiplier,
        "direction": direction,
        "reason": reason,
        "signals": {
            k: signals[k]
            for k in (
                "multiplier", "volume_ratio", "effort_factor", "avg_effort",
                "effort_trend", "completion_rate", "completion_factor",
                "overreach_detected", "current_phase", "per_type_ratios",
            )
            if k in signals
        },
        "created_at": today.isoformat(),
    }

    training_plan.pending_recommendation = recommendation
    training_plan.last_recommendation_week = last_completed_week
    db.commit()

    logger.info(
        "Auto-recommendation for plan %s week %d: %s by %d%% (x%.2f)",
        plan_id, last_completed_week, direction, pct, multiplier,
    )

    return recommendation


def accept_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Accept the pending recommendation and apply the stored multiplier."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"accepted": False, "reason": "We couldn't find that training plan."}

    rec = training_plan.pending_recommendation
    if not rec:
        return {"accepted": False, "reason": "There's no pending recommendation to apply — it may have already been accepted or dismissed."}

    multiplier = rec.get("multiplier", 1.0)
    per_type_ratios = rec.get("signals", {}).get("per_type_ratios")

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    days_elapsed = (today - start_date).days
    current_week = max(1, days_elapsed // 7 + 1)
    current_day_of_week = today.isoweekday()

    from app.models import WeeklyPlan
    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= current_week,
        )
        .all()
    )

    if not adjustable_weeks:
        training_plan.pending_recommendation = None
        db.commit()
        return {
            "accepted": False,
            "reason": "All remaining workouts in your plan are already completed or locked — there's nothing left for this recommendation to adjust.",
        }

    weeks_changed, any_distance_changed, counts = apply_adjustment_to_future_weeks(
        training_plan, adjustable_weeks, multiplier, db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=per_type_ratios,
    )

    vdot_result = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration failed (non-fatal): %s", e)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.adjustment_multiplier = multiplier
    training_plan.last_adjusted_at = now
    training_plan.pending_recommendation = None

    direction = rec.get("direction", "kept")
    summary = _build_accept_summary(
        direction=direction,
        multiplier=multiplier,
        weeks_changed=weeks_changed,
        workouts_changed=counts["workouts_changed"],
        workouts_skipped_protected=counts["workouts_skipped_protected"],
    )

    _record_event(training_plan, {
        "type": "auto_accept",
        "multiplier": multiplier,
        "direction": direction,
        "week_evaluated": rec.get("week_evaluated"),
        "reason": summary,
    })

    db.commit()

    result = {
        "accepted": True,
        "adjusted": any_distance_changed or bool(vdot_result),
        "multiplier": multiplier,
        "weeks_changed": weeks_changed,
        "workouts_changed": counts["workouts_changed"],
        "workouts_skipped_protected": counts["workouts_skipped_protected"],
        "reason": summary,
    }
    if vdot_result:
        result["vdot_recalibration"] = vdot_result
    return result


def dismiss_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Dismiss the pending recommendation without applying it."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"dismissed": False, "reason": "Plan not found"}

    rec = training_plan.pending_recommendation
    if not rec:
        return {"dismissed": False, "reason": "No pending recommendation"}

    _record_event(training_plan, {
        "type": "auto_dismiss",
        "multiplier": rec.get("multiplier", 1.0),
        "direction": rec.get("direction", "kept"),
        "week_evaluated": rec.get("week_evaluated"),
        "reason": "User dismissed recommendation.",
    })

    training_plan.pending_recommendation = None
    db.commit()

    return {"dismissed": True}


def _build_accept_summary(
    *,
    direction: str,
    multiplier: float,
    weeks_changed: int,
    workouts_changed: int,
    workouts_skipped_protected: int,
) -> str:
    """Human-readable summary of what an accepted recommendation actually did."""
    if workouts_changed == 0:
        if workouts_skipped_protected > 0:
            return (
                "No distances changed — every affected workout is a key workout, "
                "tempo, interval, or hill session and is preserved as prescribed."
            )
        return "No distances needed adjustment."

    pct = abs(round((multiplier - 1.0) * 100))
    verb = "Increased" if direction in ("increase", "increased") else "Reduced"
    sentence = (
        f"{verb} {workouts_changed} workout{'s' if workouts_changed != 1 else ''} "
        f"by ~{pct}% across {weeks_changed} week{'s' if weeks_changed != 1 else ''}."
    )
    if workouts_skipped_protected > 0:
        sentence += (
            f" {workouts_skipped_protected} key/tempo/interval workout"
            f"{'s were' if workouts_skipped_protected != 1 else ' was'} preserved."
        )
    return sentence


def _build_auto_adjust_reason(
    *,
    direction: str,
    multiplier: float,
    workouts_changed: int,
    week_numbers: list,
    total_km_delta: float,
    signals: Dict[str, Any],
) -> str:
    """Human-readable summary of what auto-adjust actually changed."""
    if workouts_changed == 0:
        return "No distances needed adjustment."

    pct = abs(round((multiplier - 1.0) * 100))
    verb = "Increased" if direction == "increased" else "Reduced"
    sign = "+" if total_km_delta > 0 else ""

    if week_numbers:
        first, last = week_numbers[0], week_numbers[-1]
        weeks_label = (
            f"week {first}" if first == last else f"weeks {first}–{last}"
        )
    else:
        weeks_label = "remaining weeks"

    workout_label = "workout" if workouts_changed == 1 else "workouts"
    return (
        f"{verb} {workouts_changed} {workout_label} across {weeks_label} "
        f"by ~{pct}% ({sign}{total_km_delta} km total)."
    )


def _record_event(training_plan: TrainingPlan, event: Dict[str, Any]) -> None:
    event["date"] = today_date().isoformat()
    event.setdefault(
        "applied_at",
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    )
    history = list(training_plan.adaptation_history or [])
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history


def evaluate_on_run_logged(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Compute signals after a single run was logged.

    Returns an evaluation dict with confidence ("high", "medium", "low"),
    multiplier, and the underlying signals — but writes nothing. The caller
    decides whether to auto-apply or park as a pending recommendation.
    """
    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None

    signals = gathered["signals"]
    multiplier = signals.get("multiplier", 1.0)
    delta = abs(multiplier - 1.0)

    if delta < 0.02:
        return None

    overreach = bool(signals.get("overreach_detected"))
    readiness_factor = signals.get("readiness_factor", 1.0) or 1.0
    tsb_form = signals.get("tsb_form")

    if delta >= _HIGH_CONFIDENCE_DELTA and (
        overreach
        or readiness_factor < 0.95
        or tsb_form == "overreached"
    ):
        confidence = "high"
    elif delta >= _MED_CONFIDENCE_DELTA:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "plan_id": plan_id,
        "multiplier": multiplier,
        "confidence": confidence,
        "signals": signals,
        "training_plan": gathered["training_plan"],
        "current_week": gathered["current_week"],
        "current_day_of_week": gathered["current_day_of_week"],
        "adjustable_weeks": gathered["adjustable_weeks"],
    }


def apply_or_park(
    plan_id: str,
    user_id: str,
    db: Session,
    evaluation: Dict[str, Any],
    auto_enabled: bool,
) -> Dict[str, Any]:
    """Either auto-apply the adjustment or write a pending recommendation.

    - High confidence + auto_enabled (+ not throttled) → apply.
    - Otherwise → write pending recommendation (existing path).
    - Low confidence → no-op.
    """
    confidence = evaluation.get("confidence")
    if confidence == "low":
        return {"action": "skipped", "reason": "low_confidence"}

    training_plan = evaluation.get("training_plan")
    if training_plan is None:
        training_plan = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.id == plan_id, TrainingPlan.user_id == user_id)
            .first()
        )
        if not training_plan:
            return {"action": "skipped", "reason": "plan_not_found"}

    # Throttle: avoid auto-adjusting if a recent adjustment already ran.
    if confidence == "high" and auto_enabled and training_plan.last_adjusted_at:
        last = training_plan.last_adjusted_at
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if (now - last) < AUTO_ADJUST_THROTTLE:
            return {"action": "throttled", "reason": "recently_adjusted"}

    if confidence == "high" and auto_enabled:
        return _apply_auto_adjustment(
            training_plan=training_plan,
            user_id=user_id,
            db=db,
            evaluation=evaluation,
        )

    return _park_recommendation(
        training_plan=training_plan,
        evaluation=evaluation,
        db=db,
    )


def _apply_auto_adjustment(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
    evaluation: Dict[str, Any],
) -> Dict[str, Any]:
    """High-confidence path: actually mutate the plan."""
    signals = evaluation["signals"]
    multiplier = evaluation["multiplier"]
    current_week = evaluation["current_week"]
    current_day_of_week = evaluation["current_day_of_week"]
    adjustable_weeks = evaluation["adjustable_weeks"]

    if not adjustable_weeks:
        return {"action": "skipped", "reason": "no_remaining_weeks"}

    pre_totals = {w.week_number: (w.total_km or 0.0) for w in adjustable_weeks}

    weeks_changed, any_distance_changed, counts = apply_adjustment_to_future_weeks(
        training_plan, adjustable_weeks, multiplier, db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=signals.get("per_type_ratios"),
    )

    changed_week_numbers = sorted(
        w.week_number
        for w in adjustable_weeks
        if (w.total_km or 0.0) != pre_totals.get(w.week_number, 0.0)
    )
    total_km_delta = round(
        sum((w.total_km or 0.0) - pre_totals.get(w.week_number, 0.0) for w in adjustable_weeks),
        1,
    )

    vdot_result = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration in auto-adjust failed (non-fatal): %s", e)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.adjustment_multiplier = multiplier
    training_plan.last_adjusted_at = now
    training_plan.pending_recommendation = None

    direction = (
        "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
    )
    reason = _build_auto_adjust_reason(
        direction=direction,
        multiplier=multiplier,
        workouts_changed=counts["workouts_changed"],
        week_numbers=changed_week_numbers,
        total_km_delta=total_km_delta,
        signals=signals,
    )
    _record_event(training_plan, {
        "type": "auto_adjust",
        "multiplier": multiplier,
        "direction": direction,
        "confidence": "high",
        "applied_at": now.isoformat(),
        "week_numbers": changed_week_numbers,
        "weeks_changed": weeks_changed,
        "workouts_changed": counts["workouts_changed"],
        "total_km_delta": total_km_delta,
        "reason": reason,
    })

    db.commit()

    logger.info(
        "Auto-adjust applied: plan=%s multiplier=%.2f direction=%s",
        training_plan.id, multiplier, direction,
    )

    return {
        "action": "auto_adjusted",
        "multiplier": multiplier,
        "direction": direction,
        "weeks_changed": weeks_changed,
        "week_numbers": changed_week_numbers,
        "workouts_changed": counts["workouts_changed"],
        "total_km_delta": total_km_delta,
        "reason": reason,
        "adjusted": any_distance_changed or bool(vdot_result),
        "vdot_recalibration": vdot_result,
    }


def _park_recommendation(
    training_plan: TrainingPlan,
    evaluation: Dict[str, Any],
    db: Session,
) -> Dict[str, Any]:
    """Medium-confidence or auto-disabled path: write pending recommendation."""
    signals = evaluation["signals"]
    multiplier = evaluation["multiplier"]
    direction = "increase" if multiplier > 1.0 else "reduce"
    pct = abs(round((multiplier - 1.0) * 100))

    reason = (
        f"Based on your recent runs, we suggest "
        f"{'increasing' if direction == 'increase' else 'reducing'} "
        f"your training by {pct}%."
    )

    recommendation = {
        "week_evaluated": evaluation["current_week"],
        "multiplier": multiplier,
        "direction": direction,
        "reason": reason,
        "signals": {
            k: signals[k]
            for k in (
                "multiplier", "volume_ratio", "effort_factor", "avg_effort",
                "effort_trend", "completion_rate", "completion_factor",
                "overreach_detected", "current_phase", "per_type_ratios",
                "readiness_factor", "tsb_form",
            )
            if k in signals
        },
        "created_at": today_date().isoformat(),
        "source": "run_logged",
    }

    training_plan.pending_recommendation = recommendation
    db.commit()

    return {
        "action": "parked",
        "multiplier": multiplier,
        "direction": direction,
        "confidence": evaluation.get("confidence"),
    }
