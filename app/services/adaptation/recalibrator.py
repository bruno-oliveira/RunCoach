"""Recalibration — strategy dispatch and simple time_off/ahead scaling."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import TrainingPlan, WeeklyPlan
from app.core.training import workout_steps as _steps_mod
from app.utils import to_date as _to_date

from ._helpers import batch_workouts_by_week, parse_plan_data_lookups, today_date
from .missed_week_handler import detect_missed_weeks, recalibrate_missed_week
from .recovery_inserter import recalibrate_recovery_insertion
from .safety import enforce_future_growth_cap, enforce_week_structure
from .suggestion_generator import get_weekly_suggestions


def recalibrate(
    plan_id: str,
    user_id: str,
    strategy: str,
    db: Session,
) -> Dict[str, Any]:
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"ok": False, "error": "Plan not found"}

    start_date = _to_date(training_plan.start_date)
    if not start_date:
        return {"ok": False, "error": "Plan has no start date"}

    today = today_date()
    current_week = min(
        ((today - start_date).days // 7) + 1,
        training_plan.weeks_duration or 0,
    )

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    weekly_plans = {
        wp.week_number: wp
        for wp in db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    }

    week_ids = [wp.id for wp in weekly_plans.values()]
    workouts_by_week = batch_workouts_by_week(week_ids, db)

    if strategy == "missed_week":
        return recalibrate_missed_week(
            training_plan, plan_data, pd_week, pd_workout,
            weekly_plans, workouts_by_week, current_week, db,
        )
    elif strategy == "recovery_insertion":
        return recalibrate_recovery_insertion(
            training_plan, plan_data, pd_week, pd_workout,
            weekly_plans, workouts_by_week, current_week, db,
        )
    elif strategy == "time_off":
        factor = 0.8
    elif strategy == "ahead":
        factor = 1.1
    else:
        return {"ok": False, "error": f"Unknown strategy: {strategy}"}

    weeks_changed = 0
    ordered_future = [
        wk for wk in sorted(weekly_plans.keys())
        if wk > current_week
    ]

    for wk_num in ordered_future:
        week = weekly_plans[wk_num]
        if week.week_number <= current_week:
            continue

        workouts = workouts_by_week.get(week.id, [])
        week_changed = False

        if strategy == "time_off":
            weeks_from_now = week.week_number - current_week
            total_remaining = training_plan.weeks_duration - current_week
            ramp = weeks_from_now / max(total_remaining, 1)
            week_factor = 0.7 + 0.3 * ramp
        else:
            week_factor = factor

        for workout in workouts:
            if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
                continue
            if workout.key_workout_id or workout.workout_type in (
                "tempo", "interval", "hill", "vo2max", "race_pace", "fartlek",
            ):
                continue
            old_distance = workout.distance_km
            new_dist = round(workout.distance_km * week_factor, 1)
            if abs(new_dist - workout.distance_km) > 0.05:
                workout.distance_km = new_dist
                week_changed = True
                pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                if pd_wo:
                    pd_wo["distance"] = new_dist
                    if pd_wo.get("steps") and old_distance and old_distance > 0:
                        pd_wo["steps"] = _steps_mod.scale_steps(
                            pd_wo["steps"], new_dist / old_distance,
                        )

        phase = pd_week.get(week.week_number, {}).get("phase", "build")
        if enforce_week_structure(
            workouts,
            training_plan.target_distance_km,
            phase,
            is_trail=bool(getattr(training_plan, "is_trail", False)),
            target_elevation_gain_m=getattr(training_plan, "target_elevation_gain_m", None),
            training_terrain=getattr(training_plan, "training_terrain", None),
        ):
            week_changed = True

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    growth_changed = enforce_future_growth_cap(
        ordered_future,
        weekly_plans,
        workouts_by_week,
        pd_week,
        high_water_seed=training_plan.current_weekly_km or 0.0,
    )
    if growth_changed > 0:
        weeks_changed += growth_changed

    for wk_num in ordered_future:
        workouts = workouts_by_week.get(weekly_plans[wk_num].id, [])
        for workout in workouts:
            pd_wo = pd_workout.get((wk_num, workout.day_of_week))
            if pd_wo:
                pd_wo["distance"] = workout.distance_km

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    strategy_labels = {
        "time_off": "Plan recalibrated with a gentler ramp from current fitness.",
        "ahead": "Plan targets increased based on your strong performance.",
    }
    reason = strategy_labels.get(strategy, "Plan recalibrated.")

    _record_recalibration_event(training_plan, strategy, weeks_changed, reason)
    db.commit()

    return {
        "ok": True,
        "strategy": strategy,
        "weeks_changed": weeks_changed,
        "reason": reason,
    }


def _record_recalibration_event(
    training_plan: TrainingPlan,
    strategy: str,
    weeks_changed: int,
    reason: str,
) -> None:
    event = {
        "date": today_date().isoformat(),
        "type": "recalibrate",
        "strategy": strategy,
        "weeks_changed": weeks_changed,
        "reason": reason,
    }
    history = training_plan.adaptation_history or []
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history
