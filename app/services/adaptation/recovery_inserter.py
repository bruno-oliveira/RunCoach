"""Ad-hoc recovery week insertion."""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models import TrainingPlan


def recalibrate_recovery_insertion(
    training_plan: TrainingPlan,
    plan_data: list,
    pd_week: Dict,
    pd_workout: Dict,
    weekly_plans: Dict,
    workouts_by_week: Dict,
    current_week: int,
    db: Session,
) -> Dict[str, Any]:
    total_weeks = training_plan.weeks_duration or 0

    history = training_plan.adaptation_history or []
    insertion_count = sum(
        1 for e in history if e.get("type") == "recalibrate" and e.get("strategy") == "recovery_insertion"
    )
    if insertion_count >= 2:
        return {"ok": False, "error": "Maximum recovery insertions (2) already used for this plan."}

    target_week_num = None
    for wk_num in sorted(weekly_plans.keys()):
        if wk_num <= current_week or wk_num > total_weeks:
            continue
        week_data = pd_week.get(wk_num, {})
        if not week_data.get("is_recovery", False):
            target_week_num = wk_num
            break

    if target_week_num is None:
        return {"ok": False, "error": "No eligible week found for recovery insertion."}

    recovery_factor = 0.60
    workouts = workouts_by_week.get(weekly_plans[target_week_num].id, [])

    for workout in workouts:
        if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
            continue
        workout.distance_km = round(workout.distance_km * recovery_factor, 1)
        pd_wo = pd_workout.get((target_week_num, workout.day_of_week))
        if pd_wo:
            pd_wo["distance"] = workout.distance_km

    new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
    weekly_plans[target_week_num].total_km = new_total
    if target_week_num in pd_week:
        pd_week[target_week_num]["total_km"] = new_total
        pd_week[target_week_num]["is_recovery"] = True
        pd_week[target_week_num]["recovery_inserted"] = True

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    reason = (
        f"Week {target_week_num} converted to recovery (60% volume). "
        "Listen to your body — easy pace only this week."
    )

    from .recalibrator import _record_recalibration_event
    _record_recalibration_event(training_plan, "recovery_insertion", 1, reason)
    db.commit()

    return {
        "ok": True,
        "strategy": "recovery_insertion",
        "weeks_changed": 1,
        "target_week": target_week_num,
        "reason": reason,
    }
