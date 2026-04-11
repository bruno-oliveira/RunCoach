"""Recalibration and weekly inline suggestions."""

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import batch_workouts_by_week, parse_plan_data_lookups, today_date
from .performance_analyzer import analyze_performance
from .skipped_detector import detect_skipped_workouts


def recalibrate(
    plan_id: str,
    user_id: str,
    strategy: str,
    db: Session,
) -> Dict[str, Any]:
    """Recalibrate remaining plan weeks based on a user-chosen strategy.

    Strategies:
    - "time_off": Rebuild remaining weeks with a gentler ramp
    - "ahead": Bump up remaining weeks' targets
    """
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

    if strategy == "time_off":
        factor = 0.8
    elif strategy == "ahead":
        factor = 1.1
    else:
        return {"ok": False, "error": f"Unknown strategy: {strategy}"}

    weeks_changed = 0
    for week in weekly_plans.values():
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
            new_dist = round(workout.distance_km * week_factor, 1)
            if abs(new_dist - workout.distance_km) > 0.05:
                workout.distance_km = new_dist
                week_changed = True
                pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                if pd_wo:
                    pd_wo["distance"] = new_dist

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.plan_data = json.dumps(plan_data)
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now
    db.commit()

    strategy_labels = {
        "time_off": "Plan recalibrated with a gentler ramp from current fitness.",
        "ahead": "Plan targets increased based on your strong performance.",
    }

    return {
        "ok": True,
        "strategy": strategy,
        "weeks_changed": weeks_changed,
        "reason": strategy_labels.get(strategy, "Plan recalibrated."),
    }


def get_weekly_suggestions(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[Dict[str, Any]]:
    """Generate per-week suggestion cards for in-plan display."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    total_weeks = training_plan.weeks_duration or 0

    delta_days = (today - start_date).days
    if delta_days < 0:
        return []

    current_week = min((delta_days // 7) + 1, total_weeks)

    perf = analyze_performance(plan_id, db)
    skipped = detect_skipped_workouts(plan_id, db)
    adherence = perf.get("adherence_rate", 0)
    effort_trend = perf.get("effort_trend", "stable")
    avg_effort = perf.get("avg_effort")

    plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []

    # Get recent run volumes by week
    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan_id,
        )
        .order_by(RunLog.date.asc())
        .all()
    )

    weekly_actual = defaultdict(float)
    for run in runs:
        rd = _to_date(run.date)
        if rd and start_date:
            d = (rd - start_date).days
            if d >= 0:
                wk = d // 7 + 1
                weekly_actual[wk] += run.distance_km or 0

    exceeding_count = 0
    deficit_count = 0
    for wk in range(max(1, current_week - 3), current_week + 1):
        week_data = next((w for w in plan_data if w.get("week") == wk), None)
        if not week_data:
            continue
        planned = week_data.get("total_km", 0)
        actual = weekly_actual.get(wk, 0)
        if planned > 0:
            ratio = actual / planned
            if ratio >= 1.05:
                exceeding_count += 1
            elif ratio < 0.75:
                deficit_count += 1

    multiplier = training_plan.adjustment_multiplier

    suggestions = []

    for week_data in plan_data:
        wk_num = week_data.get("week", 0)
        if wk_num <= current_week or wk_num > current_week + 3:
            continue

        week_suggestions = _build_week_suggestions(
            week_data, exceeding_count, deficit_count, multiplier,
            skipped, effort_trend, avg_effort, adherence,
        )

        if week_suggestions:
            suggestions.append({
                "week": wk_num,
                "suggestions": week_suggestions[:2],
            })

    return suggestions


def _build_week_suggestions(
    week_data: Dict,
    exceeding_count: int,
    deficit_count: int,
    multiplier,
    skipped: Dict,
    effort_trend: str,
    avg_effort,
    adherence: float,
) -> List[Dict[str, Any]]:
    """Build suggestion cards for a single upcoming week."""
    week_suggestions = []

    if exceeding_count >= 3:
        pct = (
            "+" + str(round((multiplier - 1) * 100)) + "%"
            if multiplier and multiplier > 1
            else "+8%"
        )
        week_suggestions.append({
            "type": "exceeding",
            "message": (
                f"You've exceeded targets {exceeding_count} weeks in a row "
                f"— this week's distances have been bumped {pct}"
            ),
            "action": "accept",
        })

    if deficit_count >= 2 and not any(s["type"] == "exceeding" for s in week_suggestions):
        week_suggestions.append({
            "type": "deficit",
            "message": "Volume has been below target — consider adding an extra easy run this week",
            "action": "accept",
        })

    long_wo = next(
        (wo for wo in week_data.get("daily_workouts", []) if wo.get("type") == "long"),
        None,
    )
    if long_wo and skipped.get("skipped", 0) > 2:
        km = long_wo.get("distance", 0)
        week_suggestions.append({
            "type": "long_run",
            "message": (
                f"Long run completion is behind — consider extending "
                f"Sunday's run to {round(km + 2)}km"
            ),
            "action": "accept",
        })

    if effort_trend == "increasing" and avg_effort and avg_effort > 7:
        is_recovery = week_data.get("phase", "").lower() in ("recovery", "taper")
        if is_recovery:
            week_suggestions.append({
                "type": "effort_recovery",
                "message": "Effort trending high — this recovery week is well-timed",
                "action": None,
            })
        else:
            week_suggestions.append({
                "type": "effort_high",
                "message": "Effort is trending high — consider reducing intensity this week",
                "action": "reduce",
            })

    if adherence < 60 and not any(s["type"] in ("deficit",) for s in week_suggestions):
        week_suggestions.append({
            "type": "adherence",
            "message": "Consistency is low — focus on completing the key workouts this week",
            "action": None,
        })

    return week_suggestions
