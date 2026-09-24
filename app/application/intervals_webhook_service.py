"""Live activity import — the run reaches the coach minutes after the watch.

The daily sweep made RunCoach notice training without a button press, but only
once a day: a runner who finished at 7am saw their plan re-pace mid-afternoon,
and the watch kept yesterday's version of tomorrow until then. Intervals.icu
can tell us the moment an activity lands, so this closes that gap:

    watch → Garmin → Intervals.icu ─webhook→ import → adapt → re-mirror → notify

Intervals posts ``{"secret": ..., "events": [{"athlete_id", "type", ...}]}``.
The secret is per *app* (set in its Manage App page), not per athlete, so it
proves the call came from Intervals — and the athlete id is only trusted after
that. The body's activity is deliberately **not** imported as-is: the handler
triggers the ordinary cursor-overlapping sync for that runner instead, so a
live import and the next morning's sweep share one importer, one dedupe, and
one enrichment path, and an event that arrives twice (``ACTIVITY_UPLOADED``
then ``ACTIVITY_ANALYZED`` a minute later) costs a no-op rather than a
duplicate run.

The endpoint must answer fast — Intervals re-fires with backoff on anything
but a 2xx — so the work happens in a background task with its own session.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.application.ambient_sync_service import AmbientSyncService, RunnerSync
from app.application.push_notification_service import get_push_notifier
from app.application.watch_sync_service import resync_plan_to_watch
from app.core.time_utils import use_timezone

logger = logging.getLogger(__name__)

# Events that can mean "there is a run we haven't seen, or one we have changed".
# ANALYZED also fires after the runner edits an activity (e.g. sets its RPE on
# Intervals afterwards), which the importer now backfills onto the stored run.
# SPORT_SETTINGS_UPDATED refreshes the HR anchors, which every sync re-reads.
SYNC_EVENTS = frozenset(
    {
        "ACTIVITY_UPLOADED",
        "ACTIVITY_ANALYZED",
        "ACTIVITY_UPDATED",
        "SPORT_SETTINGS_UPDATED",
    }
)

# One import at a time per runner. UPLOADED and ANALYZED can land close
# together; two concurrent passes would both see the run as new and both
# re-pace the plan. A single Fly machine serves the app, so a process-local
# lock is the whole story.
_athlete_locks: Dict[str, asyncio.Lock] = {}


class WebhookRejected(Exception):
    """The payload did not come from Intervals.icu (or is not a webhook)."""


@dataclass(frozen=True)
class WebhookBatch:
    """The distinct athletes a verified payload asks us to re-sync."""

    athlete_ids: List[str]
    ignored_events: int


def parse_webhook(payload: Any, secret: str) -> WebhookBatch:
    """Verify the shared secret and collect the athletes to re-sync.

    Raises:
        WebhookRejected: when the secret is missing or wrong, or the payload
            is not shaped like an Intervals.icu webhook.
    """
    if not secret:
        # Callers 404 before getting here; a blank secret must never verify.
        raise WebhookRejected("webhook secret is not configured")
    if not isinstance(payload, dict):
        raise WebhookRejected("payload is not an object")
    supplied = payload.get("secret")
    if not isinstance(supplied, str) or not hmac.compare_digest(
        supplied.encode(), secret.encode()
    ):
        raise WebhookRejected("bad secret")

    events = payload.get("events")
    if not isinstance(events, list):
        raise WebhookRejected("payload has no events")

    athlete_ids: List[str] = []
    ignored = 0
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in SYNC_EVENTS:
            ignored += 1
            continue
        athlete_id = event.get("athlete_id")
        if athlete_id is None or str(athlete_id).strip() == "":
            ignored += 1
            continue
        athlete_id = str(athlete_id)
        if athlete_id not in athlete_ids:
            athlete_ids.append(athlete_id)
    return WebhookBatch(athlete_ids=athlete_ids, ignored_events=ignored)


async def process_athlete(
    athlete_id: str,
    intervals_service: Any,
    *,
    notify: bool = True,
) -> Optional[RunnerSync]:
    """Import, adapt, re-mirror, and tell one runner — the background half.

    Returns what the import did (``None`` when the athlete is unknown to us or
    the pass failed), mostly for the tests; Intervals has long since had its 200.
    """
    lock = _athlete_locks.setdefault(athlete_id, asyncio.Lock())
    async with lock:
        return await _process_locked(athlete_id, intervals_service, notify)


async def _process_locked(
    athlete_id: str,
    intervals_service: Any,
    notify: bool,
) -> Optional[RunnerSync]:
    from app.dependencies import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.intervals_athlete_id == athlete_id).first()
        if user is None:
            # An athlete who disconnected (or never finished connecting) still
            # has our app authorised on Intervals' side until they revoke it.
            logger.info("Intervals webhook for unknown athlete %s", athlete_id)
            return None

        user_id = str(user.id)
        with use_timezone(user.timezone):
            result = await AmbientSyncService(db, intervals_service).sync_runner(user)
            db.commit()

            # The re-mirror opens its own session, which is why the commit above
            # comes first: it must read the plan the engine just re-paced.
            for plan_id in result.adapted_plan_ids:
                try:
                    await resync_plan_to_watch(plan_id, user_id, intervals_service)
                except Exception:
                    logger.exception("Live watch re-mirror failed for plan %s", plan_id)

            if notify and result.imported:
                try:
                    get_push_notifier(db).after_sync(user, result)
                    db.commit()
                except Exception:
                    logger.exception("Post-sync notification failed for %s", user_id)

        logger.info(
            "Intervals webhook for user %s: %s imported, %s plan(s) adapted",
            user_id,
            result.imported,
            len(result.adapted_plan_ids),
        )
        return result
    except Exception:
        logger.exception("Intervals webhook processing failed for %s", athlete_id)
        db.rollback()
        return None
    finally:
        db.close()
