"""Mirror a plan onto the runner's watch calendar and keep it there.

RunCoach's whole premise is that the plan adapts. For a long time that
adaptation stopped at the browser: workouts were pushed only by the manual
"send to watch" button, so shortening Thursday because you're wrecked left the
watch happily beeping out the original session.

This module makes the calendar a *mirror* of the plan rather than a log of what
was once exported. Every plan mutation re-runs :func:`resync_plan_to_watch`,
which reads the window back from Intervals.icu and reconciles it:

* a day the calendar is missing is created,
* a day whose session changed is deleted and re-created — Intervals only
  re-triggers the watch export on create, never on an in-place update, so the
  delete is load-bearing, not tidiness,
* a day that left the plan (became rest, or moved to another weekday) has its
  event deleted. This is the ghost fix: previously nothing was ever removed.

The decisions live in :mod:`app.core.training.watch_mirror`, which is pure; this
module is the I/O around them. Three constraints shape it:

* **The calendar belongs to the runner.** It holds their own workouts, their
  coach's, and events from every other app they have connected. Only events
  whose ``external_id`` marks them as this plan's may be deleted — see
  ``owns_event``. "Delete everything in the window that isn't in the plan" reads
  naturally from the rules above and would wipe a stranger's training week.
* **Only plans the runner opted in to.** ``TrainingPlan.watch_sync_enabled`` is
  the authorisation, set on the first send. Someone who has never used the
  feature should not find their calendar quietly filling up.
* **Never block, never break the adaptation.** Callers run this as a background
  task with its own session. A third-party outage must cost the runner nothing
  more than a stale watch — the in-app plan change has already succeeded. The
  failure is recorded on the plan so the page can say so, rather than leaving a
  401 in the log and a watch that silently stopped updating.

**Where the content hashes live.** ``TrainingPlan.watch_event_hashes`` maps
``external_id`` to a hash of the body we last pushed, rather than hanging a hash
column off ``DailyWorkout``. The reconciler builds its events from ``plan_data``
(not from the ORM rows), and its central question — "what did we last put on the
calendar under this id, and what belongs there now?" — is naturally keyed by
``external_id``. Keeping the map on the plan also lets the page render
per-session watch state without joining through ``weekly_plans``.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.core.time_utils import local_today
from app.core.training.watch_mirror import (
    WINDOW_DAYS,
    diff_window,
    event_hash,
    events_in_window,
)

logger = logging.getLogger(__name__)

# Recorded on the plan when a mirror fails, so the page can tell the runner
# which kind of broken this is instead of showing a stale success.
ERROR_AUTH = "auth"
ERROR_PROVIDER = "provider"


def record_pushed_events(training_plan, events: list[dict[str, Any]], db) -> None:
    """Record a manual send: opt the plan in and remember what went up.

    Called by the one-off "send to watch" paths. Enabling sync here is the
    subscription's front door — the runner asked for this session on their
    watch, so from now on we keep it true rather than letting it drift the first
    time the plan adapts. Storing the hashes means the next reconcile sees these
    days as already correct and issues no writes for them.
    """
    hashes = dict(training_plan.watch_event_hashes or {})
    for event in events:
        external_id = event.get("external_id")
        if external_id is not None:
            hashes[str(external_id)] = event_hash(event)
    training_plan.watch_event_hashes = hashes
    training_plan.watch_synced_at = datetime.utcnow()
    training_plan.watch_sync_enabled = True
    training_plan.watch_sync_error = None
    db.commit()


async def resync_plan_to_watch(plan_id: str, user_id: str, intervals_service) -> int:
    """Reconcile a plan's window onto the watch calendar after it changed.

    Runs as a background task with its own DB session, so the adaptation the
    runner just made has already been committed and rendered.

    Returns:
        The number of events written. Zero when the plan isn't mirrored, the
        runner isn't connected, nothing changed, or the provider failed — the
        background callers use it only for logging, and the runner-visible state
        is persisted on the plan.
    """
    from app.contexts.auth.repositories import SQLAlchemyUserRepository
    from app.contexts.plan.repositories import SQLAlchemyPlanRepository
    from app.dependencies import SessionLocal
    from app.infrastructure.integrations.intervals_service import (
        IntervalsAuthorizationError,
    )

    db = SessionLocal()
    training_plan = None
    try:
        training_plan = SQLAlchemyPlanRepository(db).get_by_id(plan_id)
        if training_plan is None or not training_plan.watch_sync_enabled:
            return 0

        user = SQLAlchemyUserRepository(db).get_by_id(user_id)
        if (
            user is None
            or not user.intervals_athlete_id
            or not user.intervals_access_token
        ):
            return 0

        today = local_today()
        desired = events_in_window(training_plan, today=today)
        remote = await intervals_service.fetch_events(
            user.intervals_access_token,
            user.intervals_athlete_id,
            today.isoformat(),
            (today + timedelta(days=WINDOW_DAYS)).isoformat(),
        )
        diff = diff_window(
            plan_id, desired, remote, training_plan.watch_event_hashes or {}
        )

        if diff.to_delete_ids:
            await intervals_service.delete_events(
                user.intervals_access_token,
                user.intervals_athlete_id,
                diff.to_delete_ids,
            )
        if diff.to_create:
            # The window has already been read and the stale events removed, so
            # push_workouts must not repeat that lookup.
            await intervals_service.push_workouts(
                user.intervals_access_token,
                user.intervals_athlete_id,
                diff.to_create,
                pre_delete=False,
            )

        training_plan.watch_event_hashes = diff.next_hashes
        training_plan.watch_synced_at = datetime.utcnow()
        training_plan.watch_sync_error = None
        db.commit()
        if diff.to_create or diff.to_delete_ids:
            logger.info(
                "Watch reconcile for plan %s: +%s -%s (%s unchanged)",
                plan_id,
                len(diff.to_create),
                len(diff.to_delete_ids),
                diff.unchanged,
            )
        return len(diff.to_create)
    except IntervalsAuthorizationError:
        _record_failure(db, training_plan, ERROR_AUTH)
        logger.warning("Watch re-sync unauthorized for plan %s", plan_id)
        return 0
    except Exception:
        # A stale watch is bad; a failed adaptation is worse. The plan change is
        # already persisted, so swallow and log — the next change (or the
        # runner's Retry) tries again.
        _record_failure(db, training_plan, ERROR_PROVIDER)
        logger.exception("Watch re-sync failed for plan %s", plan_id)
        return 0
    finally:
        db.close()


def _record_failure(db, training_plan, kind: str) -> None:
    """Note why the mirror failed, so the plan page can say something true."""
    if training_plan is None:
        return
    try:
        db.rollback()
        training_plan.watch_sync_error = kind
        db.commit()
    except Exception:
        logger.exception("Could not record watch sync failure")
