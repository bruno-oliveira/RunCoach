"""Performance plan progress and today's-workout logic.

Extracted from PerformanceService to keep the main service under 500 lines.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan

logger = logging.getLogger(__name__)


def get_plan_with_data(
    db: Session,
    plan_id: str,
    performance_generator,
) -> Optional[Tuple[TrainingPlan, Dict]]:
    """Get a training plan with parsed plan data and training zones.

    Args:
        db: Database session.
        plan_id: Plan ID to look up.
        performance_generator: PerformancePlanGenerator instance
            (used to recalculate training zones).

    Returns:
        (TrainingPlan, full_data dict) or None.
    """
    training_plan = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.plan_type == "performance",
        )
        .first()
    )
    if not training_plan:
        return None

    plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []

    zones = performance_generator.calculate_training_zones(
        training_plan.goal_pace,
        training_plan.max_heart_rate,
    )

    full_data = {
        "weekly_plans": plan_data,
        "training_zones": zones,
        "target_distance": training_plan.target_distance_km,
        "current_pace": training_plan.current_pace,
        "goal_pace": training_plan.goal_pace,
        "weeks": training_plan.weeks_duration,
        "max_heart_rate": training_plan.max_heart_rate,
    }

    return training_plan, full_data


def get_todays_workout(db: Session, plan: TrainingPlan) -> Dict[str, Any]:
    """Determine today's workout from the training plan.

    Args:
        db: Database session.
        plan: The training plan to check.

    Returns:
        Dictionary with status and workout details if applicable.
    """
    start = plan.start_date or plan.created_at
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    start_d = start.date() if isinstance(start, datetime) else start
    days_elapsed = (today - start_d).days

    if days_elapsed < 0:
        return {"status": "not_started"}

    week = days_elapsed // 7 + 1
    day_of_week = days_elapsed % 7 + 1  # 1=Mon, 7=Sun (ISO style)

    plan_data = json.loads(plan.plan_data) if plan.plan_data else []

    if week > len(plan_data):
        return {"status": "completed"}

    week_data = None
    for w in plan_data:
        if w.get("week") == week:
            week_data = w
            break

    if not week_data:
        return {"status": "rest_day", "week": week, "day": day_of_week}

    workout = None
    for w in week_data.get("daily_workouts", []):
        if w.get("day") == day_of_week:
            workout = w
            break

    if not workout:
        return {"status": "rest_day", "week": week, "day": day_of_week}

    already_logged = False
    if plan.user_id:
        today_start = datetime(today.year, today.month, today.day)
        today_end = today_start + timedelta(days=1)
        existing = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == plan.user_id,
                RunLog.date >= today_start,
                RunLog.date < today_end,
            )
            .first()
        )
        already_logged = existing is not None

    return {
        "status": "workout",
        "week": week,
        "day": day_of_week,
        "workout": workout,
        "already_logged": already_logged,
    }


def get_plan_progress(db: Session, plan: TrainingPlan) -> Dict[str, Any]:
    """Calculate progress metrics for a training plan.

    Args:
        db: Database session.
        plan: The training plan to analyze.

    Returns:
        Dictionary with progress stats.
    """
    plan_data = json.loads(plan.plan_data) if plan.plan_data else []
    start = plan.start_date or plan.created_at
    start_date = start.date() if isinstance(start, datetime) else start
    total_weeks = len(plan_data)
    end_date = start_date + timedelta(days=total_weeks * 7)

    planned_weekly_km = [w.get("total_km", 0) for w in plan_data]

    planned_count = sum(
        1
        for w in plan_data
        for wo in w.get("daily_workouts", [])
        if wo.get("type") not in ("rest", "recovery")
    )

    plan_start_dt = datetime(start_date.year, start_date.month, start_date.day)
    plan_end_dt = datetime(end_date.year, end_date.month, end_date.day)

    runs = []
    if plan.user_id:
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == plan.user_id,
                RunLog.date >= plan_start_dt,
                RunLog.date < plan_end_dt,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

    actual_weekly_km = [0.0] * total_weeks
    pace_by_week_data: Dict[int, list] = {}

    for run in runs:
        run_date = run.date.date() if isinstance(run.date, datetime) else run.date
        days_from_start = (run_date - start_date).days
        if days_from_start < 0:
            continue
        week_idx = days_from_start // 7
        if week_idx >= total_weeks:
            continue
        actual_weekly_km[week_idx] += run.distance_km or 0

        if run.avg_pace_min_km:
            if week_idx not in pace_by_week_data:
                pace_by_week_data[week_idx] = []
            pace_by_week_data[week_idx].append(run.avg_pace_min_km)

    actual_weekly_km = [round(km, 1) for km in actual_weekly_km]

    pace_by_week = []
    for week_idx in sorted(pace_by_week_data.keys()):
        paces = pace_by_week_data[week_idx]
        avg_pace = round(sum(paces) / len(paces), 2)
        pace_by_week.append({
            "week_label": f"W{week_idx + 1}",
            "avg_pace": avg_pace,
        })

    completed_count = len(runs)
    total_km_logged = round(sum(r.distance_km or 0 for r in runs), 1)

    completion_pct = round(completed_count / planned_count * 100) if planned_count > 0 else 0

    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    days_elapsed = (today - start_date).days
    current_week = days_elapsed // 7  # 0-indexed
    past_run_count = sum(
        1
        for week_idx, w in enumerate(plan_data)
        for wo in w.get("daily_workouts", [])
        if wo.get("type") not in ("rest", "recovery")
        and week_idx < current_week
    )
    missed_count = max(0, past_run_count - completed_count)

    streak_days = 0
    if runs:
        run_dates = set()
        for r in runs:
            rd = r.date.date() if isinstance(r.date, datetime) else r.date
            run_dates.add(rd)

        check_date = today
        while check_date in run_dates:
            streak_days += 1
            check_date -= timedelta(days=1)

    return {
        "planned_weekly_km": planned_weekly_km,
        "actual_weekly_km": actual_weekly_km,
        "pace_by_week": pace_by_week,
        "completed_count": completed_count,
        "planned_count": planned_count,
        "missed_count": missed_count,
        "completion_pct": completion_pct,
        "streak_days": streak_days,
        "total_km_logged": total_km_logged,
    }
