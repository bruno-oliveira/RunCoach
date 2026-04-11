"""Proactive adaptation alerts — detect when a plan needs attention."""

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import today_date


def check_alerts(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Check if a plan needs a proactive adaptation alert.

    Looks at the 3 most recent completed weeks (W-1, W-2, W-3 relative
    to the current week W).  If 50%+ of non-rest workouts in that
    window are unlinked (no matching RunLog), an alert is raised.

    After recalibration the alert is suppressed for 3 full weeks.

    Returns an alert dict if the threshold is met, or None.
    """
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return None

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    delta_days = (today - start_date).days
    if delta_days < 0:
        return None

    current_week = min(
        (delta_days // 7) + 1, training_plan.weeks_duration or 0
    )

    if current_week < 4:
        return None

    # Cooldown after recalibration
    recalibrated_at = training_plan.last_recalibrated_at
    if recalibrated_at:
        recalibrated_date = _to_date(recalibrated_at)
        if recalibrated_date and start_date:
            d = (recalibrated_date - start_date).days
            if d >= 0:
                recalibrated_week = d // 7 + 1
                if current_week < recalibrated_week + 4:
                    if training_plan.adaptation_alert is not None:
                        training_plan.adaptation_alert = None
                        db.commit()
                    return None

    # 3-week window: W-3, W-2, W-1
    window_weeks = [current_week - 3, current_week - 2, current_week - 1]

    window_workouts = (
        db.query(DailyWorkout.id)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number.in_(window_weeks),
            DailyWorkout.workout_type.notin_(["rest", "recovery"]),
        )
        .all()
    )

    total = len(window_workouts)
    if total == 0:
        if training_plan.adaptation_alert is not None:
            training_plan.adaptation_alert = None
            db.commit()
        return None

    workout_ids = {row[0] for row in window_workouts}

    linked_ids = set(
        row[0]
        for row in db.query(RunLog.daily_workout_id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.daily_workout_id.in_(workout_ids),
        )
        .all()
    )

    missed = total - len(linked_ids)

    if missed / total >= 0.5:
        pct = round(missed / total * 100)
        alert = {
            "type": "missed_workouts",
            "severity": "high",
            "message": (
                f"{pct}% of workouts missed in the last 3 weeks. "
                "Your plan needs attention."
            ),
            "created_at": today.isoformat(),
        }
        training_plan.adaptation_alert = json.dumps(alert)
        db.commit()
        return alert

    if training_plan.adaptation_alert is not None:
        training_plan.adaptation_alert = None
        db.commit()

    return None
