"""Auto-triggered adaptation recommendations.

Computes adjustment signals after a training week completes and stores
the result as a pending recommendation on the plan. The user can then
accept (apply) or dismiss it from the plan page.
"""

import logging
from datetime import datetime, timezone
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
        return {"accepted": False, "reason": "Plan not found"}

    rec = training_plan.pending_recommendation
    if not rec:
        return {"accepted": False, "reason": "No pending recommendation"}

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
        return {"accepted": False, "reason": "No remaining workouts to adjust."}

    weeks_changed, any_distance_changed = apply_adjustment_to_future_weeks(
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
    _record_event(training_plan, {
        "type": "auto_accept",
        "multiplier": multiplier,
        "direction": direction,
        "week_evaluated": rec.get("week_evaluated"),
        "reason": rec.get("reason", ""),
    })

    db.commit()

    result = {
        "accepted": True,
        "adjusted": any_distance_changed or bool(vdot_result),
        "multiplier": multiplier,
        "weeks_changed": weeks_changed,
        "reason": rec.get("reason", "Recommendation applied."),
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


def _record_event(training_plan: TrainingPlan, event: Dict[str, Any]) -> None:
    event["date"] = today_date().isoformat()
    history = training_plan.adaptation_history or []
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history
