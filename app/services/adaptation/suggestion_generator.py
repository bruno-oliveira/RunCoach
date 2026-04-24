"""Per-week suggestion cards for in-plan display."""

from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan
from app.utils import to_date as _to_date

from ._helpers import today_date
from .performance_analyzer import analyze_performance
from .skipped_detector import detect_skipped_workouts


def get_weekly_suggestions(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[Dict[str, Any]]:
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

    plan_data = training_plan.plan_data if training_plan.plan_data else []

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
