"""Keep an already-pushed plan in step with the runner's watch calendar.

RunCoach's whole premise is that the plan adapts. Until now that adaptation
stopped at the browser: ``push_workout`` was called only from the manual
"send to watch" button, so shortening Thursday because you're wrecked left the
watch happily beeping out the original session. Nothing re-pushed, and nothing
was ever deleted, so a day that became rest kept its ghost on the calendar.

This module closes that gap for the days that actually matter. Intervals.icu
only forwards roughly the next week of planned workouts to the device, so
re-mirroring that forward window after every plan change is enough to keep the
wrist correct — anything further out will be re-pushed before it gets there.

Two deliberate constraints:

* **Only plans the runner has already sent.** ``TrainingPlan.watch_synced_at``
  is set the first time any workout from a plan is pushed. A runner who has
  never used the feature should not find their calendar quietly filling up.
* **Never block, never break the adaptation.** Callers run this as a background
  task with its own session. A third-party outage must cost the runner nothing
  more than a stale watch — the in-app plan change has already succeeded.

The full reconciliation (a rolling multi-week mirror that also deletes moved or
removed days outside this window) is the next step; this is the subset that
makes the adaptation reach the run.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.core.time_utils import local_today
from app.core.training.workout_steps.intervals_export import build_intervals_workout

logger = logging.getLogger(__name__)

# Intervals.icu uploads about the next week of planned workouts to the device.
# One extra day of slack absorbs timezone skew between the runner's local date
# and ours without pushing sessions that can't reach the watch yet anyway.
FORWARD_WINDOW_DAYS = 8


def plan_start_date(training_plan) -> Optional[date]:
    """The plan's start date as a plain ``date``, or None when unset."""
    start = training_plan.start_date
    if isinstance(start, datetime):
        return start.date()
    if isinstance(start, date):
        return start
    return None


def workout_date(training_plan, week: int, day: int) -> date:
    """Calendar date of the (week, day) workout.

    Falls back to today as the week-1 anchor when the plan has no start date, so
    a dateless plan still produces sensible relative days rather than failing.
    """
    base = plan_start_date(training_plan) or local_today()
    return base + timedelta(weeks=week - 1, days=day - 1)


def workout_start_date_local(training_plan, week: int, day: int) -> str:
    """ISO ``start_date_local`` for the (week, day) workout on the plan calendar."""
    return f"{workout_date(training_plan, week, day).isoformat()}T00:00:00"


def build_event(
    training_plan, week: int, day: int, day_data: dict[str, Any]
) -> dict[str, Any]:
    """Build the Intervals.icu calendar event for one planned workout.

    Raises:
        ValueError: The day has nothing sendable (a rest day, or a day with
            neither structured steps nor a distance) — callers decide whether
            that is an error or a skip.
    """
    workout = build_intervals_workout(day_data)
    return {
        "category": "WORKOUT",
        "type": "Run",
        "start_date_local": workout_start_date_local(training_plan, week, day),
        "name": workout["name"],
        "description": workout["description"],
        "moving_time": workout["moving_time"],
        "external_id": f"runcoach-{training_plan.id}-{week}-{day}",
    }


def events_in_forward_window(
    training_plan,
    today: Optional[date] = None,
    forward_days: int = FORWARD_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Sendable events for the plan days between today and the window edge.

    Days outside the window, rest days, and days with nothing structured to send
    are all left out — the first because Intervals wouldn't forward them yet, the
    rest because there is no workout to run.
    """
    anchor = today or local_today()
    horizon = anchor + timedelta(days=forward_days)
    events: list[dict[str, Any]] = []

    for week_data in training_plan.plan_data or []:
        week = week_data.get("week")
        if not isinstance(week, int):
            continue
        for day_data in week_data.get("daily_workouts", []):
            day = day_data.get("day")
            if not isinstance(day, int):
                continue
            when = workout_date(training_plan, week, day)
            if when < anchor or when > horizon:
                continue
            try:
                events.append(build_event(training_plan, week, day, day_data))
            except ValueError:
                continue
    return events


def mark_plan_pushed(training_plan, db) -> None:
    """Record that this plan now lives on the runner's watch calendar.

    Called on every successful push. Its presence is what later authorises an
    automatic re-push, so it must be set by the manual send paths too.
    """
    training_plan.watch_synced_at = datetime.utcnow()
    db.commit()


async def resync_plan_to_watch(plan_id: str, user_id: str, intervals_service) -> int:
    """Re-push a plan's forward window after the plan changed.

    Runs as a background task with its own DB session, so the adaptation the
    runner just made has already been committed and rendered. Returns the number
    of events pushed (0 when the plan isn't on a watch, isn't connected, or has
    nothing in the window).
    """
    from app.contexts.auth.repositories import SQLAlchemyUserRepository
    from app.contexts.plan.repositories import SQLAlchemyPlanRepository
    from app.dependencies import SessionLocal

    db = SessionLocal()
    try:
        training_plan = SQLAlchemyPlanRepository(db).get_by_id(plan_id)
        if training_plan is None or training_plan.watch_synced_at is None:
            return 0

        user = SQLAlchemyUserRepository(db).get_by_id(user_id)
        if (
            user is None
            or not user.intervals_athlete_id
            or not user.intervals_access_token
        ):
            return 0

        events = events_in_forward_window(training_plan)
        if not events:
            return 0

        await intervals_service.push_workouts(
            user.intervals_access_token, user.intervals_athlete_id, events
        )
        training_plan.watch_synced_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Re-pushed %s workout(s) to the watch for plan %s", len(events), plan_id
        )
        return len(events)
    except Exception:
        # A stale watch is bad; a failed adaptation is worse. The plan change is
        # already persisted, so swallow and log — the next change (or a manual
        # send) retries.
        logger.exception("Watch re-sync failed for plan %s", plan_id)
        return 0
    finally:
        db.close()
