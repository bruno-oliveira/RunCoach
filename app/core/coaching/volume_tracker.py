"""Volume feedback — weekly mileage progress vs planned."""

from datetime import timedelta
from typing import Optional


def volume_feedback(run_log, db) -> Optional[str]:
    """Weekly mileage progress vs planned."""
    if not run_log.training_plan_id:
        return None

    from app.models import RunLog, TrainingPlan, WeeklyPlan

    plan = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.id == run_log.training_plan_id)
        .first()
    )
    if not plan or not plan.start_date:
        return None

    run_date = run_log.date.replace(tzinfo=None) if hasattr(run_log.date, 'replace') and run_log.date.tzinfo else run_log.date
    plan_start = plan.start_date.replace(tzinfo=None) if hasattr(plan.start_date, 'replace') and plan.start_date.tzinfo else plan.start_date
    days_since_start = (run_date - plan_start).days
    if days_since_start < 0:
        return None
    current_week_num = (days_since_start // 7) + 1

    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == current_week_num,
        )
        .first()
    )
    if not wp:
        return None

    planned_km = wp.total_km or 0
    if planned_km <= 0:
        return None

    week_start = plan.start_date + timedelta(weeks=current_week_num - 1)
    week_end = week_start + timedelta(days=7)
    logged_km = sum(
        r.distance_km
        for r in db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan.id,
            RunLog.user_id == run_log.user_id,
            RunLog.date >= week_start,
            RunLog.date < week_end,
        )
        .all()
    )

    pct = (logged_km / planned_km) * 100
    if pct >= 100:
        return (
            f"Week {current_week_num} target reached! "
            f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
        )
    elif pct >= 75:
        return (
            f"Week {current_week_num} is on track: "
            f"{logged_km:.1f}/{planned_km:.1f} km ({pct:.0f}%)."
        )
    else:
        remaining = planned_km - logged_km
        return (
            f"Week {current_week_num}: {logged_km:.1f}/{planned_km:.1f} km "
            f"({pct:.0f}%). {remaining:.1f} km still to go."
        )
