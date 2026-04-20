"""Proactive adaptation alerts — detect when a plan needs attention."""

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

    # Graduated cooldown after recalibration:
    #   Week 1: suppress all alerts
    #   Week 2: suppress volume alerts, allow effort alerts
    #   Week 3+: full alerting resumed
    cooldown_level = _cooldown_level(training_plan, start_date, current_week)

    if cooldown_level == "full":
        if training_plan.adaptation_alert is not None:
            training_plan.adaptation_alert = None
            db.commit()
        return None

    # 3-week window: W-3, W-2, W-1
    window_weeks = [current_week - 3, current_week - 2, current_week - 1]

    # During partial cooldown, only look at effort-related types
    excluded_types = ["rest", "recovery"]
    if cooldown_level == "volume_only":
        excluded_types += ["easy", "long"]

    window_workouts = (
        db.query(DailyWorkout.id)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number.in_(window_weeks),
            DailyWorkout.workout_type.notin_(excluded_types),
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
        alert_type = "missed_workouts"
        if cooldown_level == "volume_only":
            alert_type = "missed_quality_workouts"
        alert = {
            "type": alert_type,
            "severity": "high",
            "message": (
                f"{pct}% of workouts missed in the last 3 weeks. "
                "Your plan needs attention."
            ),
            "created_at": today.isoformat(),
        }
        training_plan.adaptation_alert = alert
        db.commit()
        return alert

    if training_plan.adaptation_alert is not None:
        training_plan.adaptation_alert = None
        db.commit()

    return None


def _cooldown_level(
    training_plan: TrainingPlan,
    start_date,
    current_week: int,
) -> str:
    """Determine the post-recalibration cooldown level.

    Returns:
      "full"        — suppress all alerts (week 1 after recalibration)
      "volume_only" — suppress volume alerts, allow effort (week 2)
      "none"        — full alerting (week 3+)
    """
    recalibrated_at = training_plan.last_recalibrated_at
    if not recalibrated_at:
        return "none"

    recalibrated_date = _to_date(recalibrated_at)
    if not recalibrated_date or not start_date:
        return "none"

    d = (recalibrated_date - start_date).days
    if d < 0:
        return "none"

    recalibrated_week = d // 7 + 1
    weeks_since = current_week - recalibrated_week

    if weeks_since <= 1:
        return "full"
    elif weeks_since <= 2:
        return "volume_only"
    return "none"
