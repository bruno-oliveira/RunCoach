"""Proactive adaptation alerts — detect when a plan needs attention."""

from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.plan_calendar import compute_current_week
from app.models import DailyWorkout, ReadinessLog, RunLog, TrainingPlan, WeeklyPlan
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
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return None

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    if (today - start_date).days < 0:
        return None

    current_week = compute_current_week(
        start_date, today, total_weeks=training_plan.weeks_duration or 0
    )

    if current_week < 4:
        # Before the 3-week missed-workout window has data, the lightweight
        # intra-week readiness advisory still applies (audit E1).
        return _check_readiness_alert(training_plan, user_id, db, today)

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

    # Fatigue alert: high effort + increasing trend (improvement #7 trigger)
    fatigue_alert = _check_fatigue_alert(plan_id, training_plan, db, today)
    if fatigue_alert:
        return fatigue_alert

    # Lower-priority intra-week readiness advisory (audit E1).
    readiness_alert = _check_readiness_alert(training_plan, user_id, db, today)
    if readiness_alert:
        return readiness_alert

    if training_plan.adaptation_alert is not None:
        training_plan.adaptation_alert = None
        db.commit()

    return None


def _check_readiness_alert(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
    today,
) -> Optional[Dict[str, Any]]:
    """Light intra-week readiness check from recent self-reported check-ins.

    Unlike the weekly recommendation (which only fires after a week
    completes), this surfaces a same-week nudge when the runner's recent
    morning readiness logs trend low — so a fatigued athlete is advised to
    ease the next quality session rather than push through (audit E1).
    """
    recent = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == user_id,
            ReadinessLog.log_date >= today - timedelta(days=4),
        )
        .order_by(ReadinessLog.log_date.desc())
        .limit(4)
        .all()
    )

    existing = training_plan.adaptation_alert

    scores = [r.score for r in recent if r.score is not None]
    if len(scores) < 2:
        # Not enough signal — clear only a stale readiness advisory.
        if existing and existing.get("type") == "readiness_low":
            training_plan.adaptation_alert = None
            db.commit()
        return None

    avg = sum(scores) / len(scores)
    low_statuses = sum(1 for r in recent if r.status in ("rest", "caution"))
    poor = avg < 45 or low_statuses >= 2

    if not poor:
        if existing and existing.get("type") == "readiness_low":
            training_plan.adaptation_alert = None
            db.commit()
        return None

    # Never clobber a higher-severity alert already on display.
    if existing and existing.get("severity") == "high":
        return None

    alert = {
        "type": "readiness_low",
        "severity": "medium",
        "message": (
            f"Your recent readiness check-ins are low (avg {round(avg)}/100). "
            "Ease your next quality session or add a recovery day before pushing on."
        ),
        "suggestion": "ease_next_session",
        "created_at": today.isoformat(),
    }
    training_plan.adaptation_alert = alert
    db.commit()
    return alert


def _check_fatigue_alert(
    plan_id: str,
    training_plan,
    db: Session,
    today,
) -> Optional[Dict[str, Any]]:
    """Check for high fatigue signals that suggest a recovery insertion."""
    recent_cutoff = today - timedelta(weeks=2)
    recent_runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.date >= recent_cutoff,
            RunLog.perceived_effort.isnot(None),
        )
        .all()
    )

    if len(recent_runs) < 3:
        return None

    efforts = [r.perceived_effort for r in recent_runs if r.perceived_effort]
    if not efforts:
        return None

    avg_recent_effort = sum(efforts) / len(efforts)

    if avg_recent_effort < 7.5:
        return None

    # Check for increasing trend in the last few runs
    if len(efforts) >= 4:
        mid = len(efforts) // 2
        first_half = sum(efforts[:mid]) / mid
        second_half = sum(efforts[mid:]) / (len(efforts) - mid)
        if second_half - first_half < 0.5:
            return None

    alert = {
        "type": "fatigue_high",
        "severity": "medium",
        "message": (
            f"Your recent effort is averaging {avg_recent_effort:.1f}/10 and trending up. "
            "Consider inserting a recovery week."
        ),
        "suggestion": "recovery_insertion",
        "created_at": today.isoformat(),
    }
    training_plan.adaptation_alert = alert
    db.commit()
    return alert


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
