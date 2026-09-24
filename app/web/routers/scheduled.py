"""The ambient-sync trigger — the app's one unattended write path.

`POST /api/scheduled/sync` imports everyone's new activities, lets the adaptive
engine see them, and rolls every mirrored plan's watch window forward. It is
what turns RunCoach from something that notices you trained when you press a
button into something that notices on its own.

Driven by `.github/workflows/ambient-sync.yml`. Gated by the shared cron secret
(`app.dependencies.cron`), so it 404s entirely until `CRON_SECRET` is set.

**It must run before the outbound-nudge trigger, not after.** The `gone_quiet`
guard asks "has this runner logged anything lately"; ask that before importing
and you can email someone about a silence they already ended.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.application.ambient_sync_service import AmbientSyncService
from app.application.push_notification_service import get_push_notifier
from app.application.scheduled_push_service import ScheduledPushService
from app.dependencies import (
    get_db,
    get_intervals_service,
    require_cron_secret,
)
from app.infrastructure.integrations.intervals_service import IntervalsService

logger = logging.getLogger(__name__)

scheduled_router = APIRouter(
    tags=["scheduled"], dependencies=[Depends(require_cron_secret)]
)


@scheduled_router.post("/api/scheduled/sync")
async def run_ambient_sync(
    dry_run: bool = False,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> dict:
    """Import activities, adapt plans, roll watch windows.

    Safe to call more often than scheduled: imports overlap the stored cursor
    rather than re-reading everything, and the mirror's content hash means an
    unchanged plan issues no writes. ``limit`` chunks a sweep that has grown
    too slow for one request; ``dry_run`` calls no provider at all.
    """
    service = AmbientSyncService(db, intervals_service)
    summary = await service.run(dry_run=dry_run, limit=limit)
    return {"ok": True, "dry_run": dry_run, **summary}


@scheduled_router.post("/api/scheduled/hourly")
async def run_hourly_pushes(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
) -> dict:
    """Morning briefs and week reviews for whoever's local hour it is.

    Driven hourly by ``.github/workflows/hourly-push.yml``. Cheap when nobody
    is due: only runners with a push device are even considered, and the
    ledger makes a re-run within the same hour a no-op.
    """
    service = ScheduledPushService(db, intervals_service, get_push_notifier(db))
    summary = await service.run(dry_run=dry_run)
    return {"ok": True, "dry_run": dry_run, **summary}
