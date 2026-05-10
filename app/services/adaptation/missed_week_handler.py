"""Missed week detection and recalibration."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan
from app.core.training import workout_steps as _steps_mod
from app.utils import to_date as _to_date

from ._helpers import today_date
from .safety import enforce_future_growth_cap, enforce_week_structure


def detect_missed_weeks(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[int]:
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    total_weeks = training_plan.weeks_duration or 0
    current_week = min(((today - start_date).days // 7) + 1, total_weeks)

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan_id,
        )
        .all()
    )

    weekly_runs: Dict[int, int] = defaultdict(int)
    for run in runs:
        rd = _to_date(run.date)
        if rd and start_date:
            d = (rd - start_date).days
            if d >= 0:
                wk = d // 7 + 1
                weekly_runs[wk] += 1

    missed = []
    for wk in range(1, current_week):
        if weekly_runs.get(wk, 0) == 0:
            missed.append(wk)
    return missed


def recalibrate_missed_week(
    training_plan: TrainingPlan,
    plan_data: list,
    pd_week: Dict,
    pd_workout: Dict,
    weekly_plans: Dict,
    workouts_by_week: Dict,
    current_week: int,
    db: Session,
) -> Dict[str, Any]:
    _PHASE_EASE_IN = {
        "base": 0.80,
        "build": 0.75,
        "peak": 0.65,
        "taper": 0.80,
    }

    total_weeks = training_plan.weeks_duration or 0
    future_weeks = sorted(
        wk for wk in weekly_plans if wk > current_week and wk <= total_weeks
    )

    if not future_weeks:
        return {"ok": False, "error": "No future weeks to adjust"}

    ease_in_week = future_weeks[0]
    phase = pd_week.get(ease_in_week, {}).get("phase", "build")
    ease_factor = _PHASE_EASE_IN.get(phase, 0.70)

    ease_workouts = workouts_by_week.get(
        weekly_plans[ease_in_week].id, []
    )
    for workout in ease_workouts:
        if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
            continue
        if workout.key_workout_id or workout.workout_type in (
            "tempo", "interval", "hill", "vo2max", "race_pace", "fartlek",
        ):
            continue
        old_distance = workout.distance_km
        workout.distance_km = round(workout.distance_km * ease_factor, 1)
        pd_wo = pd_workout.get((ease_in_week, workout.day_of_week))
        if pd_wo:
            pd_wo["distance"] = workout.distance_km
            if pd_wo.get("steps") and old_distance and old_distance > 0:
                pd_wo["steps"] = _steps_mod.scale_steps(
                    pd_wo["steps"], workout.distance_km / old_distance,
                )

    phase = pd_week.get(ease_in_week, {}).get("phase", "build")
    enforce_week_structure(
        ease_workouts,
        training_plan.target_distance_km,
        phase,
        is_trail=bool(getattr(training_plan, "is_trail", False)),
        target_elevation_gain_m=getattr(training_plan, "target_elevation_gain_m", None),
        training_terrain=getattr(training_plan, "training_terrain", None),
    )

    new_total = round(sum(w.distance_km for w in ease_workouts if w.distance_km), 1)
    if ease_in_week in weekly_plans:
        weekly_plans[ease_in_week].total_km = new_total
    if ease_in_week in pd_week:
        pd_week[ease_in_week]["total_km"] = new_total

    remaining = [w for w in future_weeks if w > ease_in_week]
    if len(remaining) >= 2:
        for i in range(len(remaining) - 1):
            target_wk = remaining[i]
            source_wk = remaining[i + 1]
            target_workouts = workouts_by_week.get(weekly_plans[target_wk].id, [])
            source_workouts = workouts_by_week.get(weekly_plans[source_wk].id, [])
            source_dists = {w.day_of_week: w.distance_km for w in source_workouts}
            for wo in target_workouts:
                if wo.key_workout_id or wo.workout_type in (
                    "tempo", "interval", "hill", "vo2max", "race_pace", "fartlek",
                ):
                    continue
                if wo.day_of_week in source_dists and source_dists[wo.day_of_week]:
                    old_distance = wo.distance_km or 0
                    wo.distance_km = source_dists[wo.day_of_week]
                    pd_wo = pd_workout.get((target_wk, wo.day_of_week))
                    if pd_wo:
                        pd_wo["distance"] = wo.distance_km
                        if pd_wo.get("steps") and old_distance > 0:
                            pd_wo["steps"] = _steps_mod.scale_steps(
                                pd_wo["steps"], wo.distance_km / old_distance,
                            )
            wk_total = round(sum(w.distance_km for w in target_workouts if w.distance_km), 1)
            if target_wk in weekly_plans:
                weekly_plans[target_wk].total_km = wk_total
            if target_wk in pd_week:
                pd_week[target_wk]["total_km"] = wk_total

    ordered = [wk for wk in future_weeks if wk <= total_weeks]
    enforce_future_growth_cap(
        ordered,
        weekly_plans,
        workouts_by_week,
        pd_week,
        high_water_seed=training_plan.current_weekly_km or 0.0,
    )

    for wk_num in ordered:
        week_workouts = workouts_by_week.get(weekly_plans[wk_num].id, [])
        for wo in week_workouts:
            pd_wo = pd_workout.get((wk_num, wo.day_of_week))
            if pd_wo:
                pd_wo["distance"] = wo.distance_km

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    reason = (
        f"Plan recalibrated for a missed week: next week eased to {int(ease_factor*100)}% "
        f"({phase} phase), remaining weeks shifted to preserve race date."
    )

    from .recalibrator import _record_recalibration_event
    _record_recalibration_event(training_plan, "missed_week", len(future_weeks), reason)
    db.commit()

    return {
        "ok": True,
        "strategy": "missed_week",
        "weeks_changed": len(future_weeks),
        "reason": reason,
    }
