"""Pull the watch's overnight markers from Intervals.icu and let readiness use them.

Called from three places, each for a different reason:

* **Every activity sync** (manual, webhook, daily sweep) — cheap, and keeps the
  baseline filled in for runners who never open the check-in card.
* **The morning brief** — right before composing "today", so last night's HRV
  is in the verdict rather than yesterday's.
* **The check-in card's prefill** — so the form opens with the watch's sleep and
  a line on how recovered it thinks you are.

Wellness has no webhook, and a runner's watch posts last night at whatever
hour they wake, so "fetch on the way to using it" is the only timing that is
always right. Best-effort everywhere: a wellness failure never costs an
activity import, a brief, or a check-in.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.contexts.runner.wellness.wellness_service import WellnessService
from app.core.coaching.wellness import BASELINE_WINDOW_DAYS
from app.core.time_utils import local_today
from app.infrastructure.integrations.intervals_service import (
    LEGACY_SCOPES,
    IntervalsAuthorizationError,
    IntervalsScopeMissing,
    has_wellness_scope,
)
from app.models import User

logger = logging.getLogger(__name__)

# After the first backfill, re-read a few days: devices revise last night's
# sleep through the morning, and a missed day should heal on the next sync.
_REFRESH_DAYS = 3


async def refresh_wellness(
    user: User,
    db: Session,
    intervals_service: Any,
    *,
    today: Optional[date] = None,
) -> int:
    """Import recent wellness for ``user`` and refresh today's watch check-in.

    Returns the number of days written. Flushes but does not commit; callers
    commit alongside whatever else they did.
    """
    if not (user.intervals_athlete_id and user.intervals_access_token):
        return 0
    if not has_wellness_scope(user):
        return 0

    today = today or local_today()
    wellness = WellnessService(db)
    user_id = str(user.id)
    span = _REFRESH_DAYS if wellness.has_any(user_id) else BASELINE_WINDOW_DAYS + 1
    try:
        rows = await intervals_service.fetch_wellness(
            user.intervals_access_token,
            user.intervals_athlete_id,
            (today - timedelta(days=span)).isoformat(),
            today.isoformat(),
        )
    except IntervalsScopeMissing:
        # A connection from before we asked for wellness. Pin it so we stop
        # asking every sync; the settings panel offers the reconnect.
        if user.intervals_scopes is None:
            user.intervals_scopes = LEGACY_SCOPES
        logger.info("Intervals grant for user %s lacks wellness", user_id)
        return 0
    except IntervalsAuthorizationError:
        return 0
    except Exception:
        logger.warning("Wellness fetch failed for user %s", user_id, exc_info=True)
        return 0

    written = wellness.upsert_days(user_id, rows)
    try:
        wellness.ensure_wearable_log(user_id, today)
    except Exception:
        logger.warning("Wearable readiness failed for %s", user_id, exc_info=True)
    return written
