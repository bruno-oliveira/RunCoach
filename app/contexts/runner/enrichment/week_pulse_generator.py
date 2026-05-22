"""Week pulse — chatty inline feedback tying recent activity together."""

import logging
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan

logger = logging.getLogger(__name__)


def get_week_pulse(
    training_plan: TrainingPlan,
    current_week: int,
    db: Session,
) -> Optional[dict[str, Any]]:
    if not training_plan.start_date:
        return None

    start_date = (
        training_plan.start_date.date()
        if isinstance(training_plan.start_date, datetime)
        else training_plan.start_date
    )

    week_start = start_date + timedelta(weeks=current_week - 1)
    prev_week_start = start_date + timedelta(weeks=max(0, current_week - 2))
    today = _date.today()
    # RunLog.date is a DateTime, so use an exclusive upper bound at tomorrow's
    # midnight — otherwise a run with a non-zero time component on `today`
    # compares greater than the date-only bound and gets dropped.
    tomorrow = today + timedelta(days=1)

    current_week_runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == training_plan.id,
            RunLog.date >= week_start,
            RunLog.date < tomorrow,
        )
        .all()
    )

    prev_week_runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == training_plan.id,
            RunLog.date >= prev_week_start,
            RunLog.date < week_start,
        )
        .all()
    )

    if not current_week_runs and not prev_week_runs:
        return None

    current_km = sum(r.distance_km or 0 for r in current_week_runs)
    prev_km = sum(r.distance_km or 0 for r in prev_week_runs)
    current_efforts = [
        r.perceived_effort for r in current_week_runs if r.perceived_effort
    ]
    prev_efforts = [r.perceived_effort for r in prev_week_runs if r.perceived_effort]

    avg_effort_now = (
        sum(current_efforts) / len(current_efforts) if current_efforts else None
    )
    avg_effort_prev = sum(prev_efforts) / len(prev_efforts) if prev_efforts else None

    plan_data = training_plan.plan_data or []
    week_data = next((w for w in plan_data if w.get("week") == current_week), None)
    planned_km = week_data.get("total_km", 0) if week_data else 0

    messages = []
    details = []
    mood = "neutral"

    runs_this_week = len(current_week_runs)
    if runs_this_week > 0:
        details.append(
            f"{runs_this_week} run{'s' if runs_this_week != 1 else ''} logged this week ({current_km:.1f} km)"
        )

    if planned_km > 0 and current_km > 0:
        pct = current_km / planned_km * 100
        if pct >= 90:
            messages.append("You're on track this week — strong execution.")
            mood = "positive"
        elif pct >= 60:
            messages.append(f"About {pct:.0f}% of this week's volume done. Keep going!")
            mood = "positive"
        elif pct > 0:
            messages.append(
                f"{pct:.0f}% done so far. Still time to get the key sessions in."
            )
            mood = "neutral"

    if prev_km > 0 and current_km > 0:
        if current_km > prev_km * 0.8:
            details.append(f"Volume holding steady vs last week ({prev_km:.0f} km)")
        elif current_km < prev_km * 0.5 and runs_this_week >= 2:
            details.append(
                f"Lower volume than last week ({prev_km:.0f} km) — intentional rest?"
            )

    if avg_effort_now is not None:
        if avg_effort_now <= 5:
            details.append(f"Avg effort: {avg_effort_now:.1f}/10 — feeling fresh")
        elif avg_effort_now <= 7:
            details.append(f"Avg effort: {avg_effort_now:.1f}/10 — good working range")
        else:
            details.append(
                f"Avg effort: {avg_effort_now:.1f}/10 — running hard this week"
            )
            mood = "caution"

        if avg_effort_prev is not None:
            if avg_effort_now > avg_effort_prev + 1.5:
                messages.append(
                    "Effort is climbing compared to last week. Watch for fatigue."
                )
                mood = "caution"
            elif avg_effort_now < avg_effort_prev - 1.5:
                messages.append("Runs are feeling easier — your fitness is adapting!")
                mood = "positive"

    if not messages and runs_this_week == 0 and prev_km > 0:
        messages.append("No runs logged yet this week. Ready to get started?")
        mood = "neutral"

    if not messages:
        messages.append("Keep it up — consistency builds fitness.")

    return {
        "message": messages[0] if messages else None,
        "mood": mood,
        "details": details[:3],
        "runs_this_week": runs_this_week,
        "km_this_week": round(current_km, 1),
    }
