"""The sweep that makes the coach notice you trained without being asked.

Until now `auto_map_and_adjust` — the adaptive engine's only trigger — ran
inside the manual `/api/intervals/sync` and `/api/strava/sync` handlers. So the
plan re-paced itself only when the runner pressed a button, and the watch
window (21 days from *today*) only rolled forward when something else happened
to change the plan. A runner who trained all week and didn't open the app got
neither.

This runs on a schedule instead, in two phases:

1. **Import and adapt.** Pull new activities for every connected runner and
   hand them to the same `auto_map_and_adjust` the manual sync uses.
2. **Roll the watch window.** Reconcile every mirrored plan, which both picks
   up whatever phase 1 changed and pulls the far edge of the window forward a
   day. N1's content hash makes an unchanged plan cost zero API *writes* — but
   note it still costs one read per plan per day, which is the number to watch
   if Intervals ever publishes a rate limit.

Two phases rather than one loop because `resync_plan_to_watch` opens its own
session (it is normally a background task); committing phase 1 first means it
reads the adaptation that phase 1 just made rather than racing it.

**Do not touch `last_activity` here.** It means "the human showed up", and both
session expiry and the 24-month retention sweep key off it. A background job
that refreshed it would keep every connected account alive forever and quietly
disable `cleanup_inactive_accounts`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.application.watch_sync_service import resync_plan_to_watch
from app.contexts.plan.adaptation import AdaptationService
from app.infrastructure.config import Settings
from app.infrastructure.config import settings as default_settings
from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
)
from app.infrastructure.integrations.strava_post_sync_service import (
    auto_map_and_adjust,
)
from app.models import TrainingPlan, User
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

# Overlap the previous cursor by a day, exactly as the manual sync does: an
# activity edited or uploaded late would otherwise fall in the gap forever.
_CURSOR_OVERLAP_SECONDS = 86400


@dataclass
class AmbientRunSummary:
    """What one sweep did, for the endpoint (and the workflow log) to report."""

    candidates: int = 0
    runs_imported: int = 0
    users_with_new_runs: int = 0
    plans_adapted: int = 0
    watch_plans_rolled: int = 0
    watch_events_written: int = 0
    reconnect_needed: int = 0
    failed: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "candidates": self.candidates,
            "runs_imported": self.runs_imported,
            "users_with_new_runs": self.users_with_new_runs,
            "plans_adapted": self.plans_adapted,
            "watch_plans_rolled": self.watch_plans_rolled,
            "watch_events_written": self.watch_events_written,
            "reconnect_needed": self.reconnect_needed,
            "failed": self.failed,
        }


class AmbientSyncService:
    """Imports activities and mirrors plans for everyone, on a schedule."""

    def __init__(
        self,
        db: Session,
        intervals_service: Any,
        strava_service: Any = None,
        config: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.intervals_service = intervals_service
        self.strava_service = strava_service
        self.settings = config or default_settings

    async def run(
        self, *, dry_run: bool = False, limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Sweep every connected runner, then every mirrored plan.

        ``dry_run`` counts what would be touched and calls no provider at all —
        enough to check the schedule is wired up without spending API quota.
        """
        summary = AmbientRunSummary()
        users = self._connected_users(limit)
        summary.candidates = len(users)

        if dry_run:
            summary.watch_plans_rolled = len(self._mirrored_plans(limit))
            logger.info("Ambient sync dry run: %s", summary.as_dict())
            return summary.as_dict()

        for user in users:
            try:
                await self._import_and_adapt(user, summary)
            except Exception:
                # One revoked token or malformed activity must not cost every
                # other runner their sync.
                logger.exception("Ambient sync failed for user %s", user.id)
                summary.failed += 1
        self.db.commit()

        for plan in self._mirrored_plans(limit):
            try:
                summary.watch_events_written += await resync_plan_to_watch(
                    str(plan.id), str(plan.user_id), self.intervals_service
                )
                summary.watch_plans_rolled += 1
            except Exception:
                logger.exception("Watch window roll failed for plan %s", plan.id)
                summary.failed += 1

        logger.info("Ambient sync: %s", summary.as_dict())
        return summary.as_dict()

    # ---- phase 1: import and adapt ---------------------------------------

    async def _import_and_adapt(self, user: User, summary: AmbientRunSummary) -> None:
        imported = 0
        imported += await self._sync_intervals(user, summary)
        imported += await self._sync_strava(user)

        summary.runs_imported += imported
        if imported == 0:
            return

        summary.users_with_new_runs += 1
        # Exactly what the manual sync does on the way back — same engine, same
        # re-pacing, just nobody had to press anything.
        summary.plans_adapted += len(
            auto_map_and_adjust(user, self.db, AdaptationService()) or []
        )

    async def _sync_intervals(self, user: User, summary: AmbientRunSummary) -> int:
        if not user.intervals_athlete_id:
            return 0
        if not user.intervals_access_token:
            # Connected by athlete id but holding no usable token — a revoked
            # grant, or a row whose token no longer decrypts after a key
            # rotation. The UI still shows them as connected, so counting this
            # is the only way anyone finds out the sync has been a no-op.
            logger.warning(
                "Intervals.icu token missing for user %s — skipping", user.id
            )
            summary.reconnect_needed += 1
            return 0
        after = (
            user.intervals_last_synced_at - _CURSOR_OVERLAP_SECONDS
            if user.intervals_last_synced_at
            else TimestampAdapter.days_ago_utc_epoch(
                self.settings.intervals_initial_sync_days
            )
        )
        try:
            result = await self.intervals_service.sync_activities(
                user, self.db, after_timestamp=after
            )
        except IntervalsAuthorizationError:
            # Nothing to do unattended — reconnecting needs the runner. The plan
            # page already says so via ``watch_sync_error``; here we only count
            # it so a wave of expiries is visible in the run summary.
            logger.warning(
                "Intervals.icu authorization expired for user %s — skipping", user.id
            )
            summary.reconnect_needed += 1
            return 0
        return int(result.get("synced", 0) or 0)

    async def _sync_strava(self, user: User) -> int:
        if self.strava_service is None or not user.strava_athlete_id:
            return 0
        after = (
            user.strava_last_synced_at - _CURSOR_OVERLAP_SECONDS
            if user.strava_last_synced_at
            else TimestampAdapter.days_ago_utc_epoch(
                self.settings.strava_initial_sync_days
            )
        )
        try:
            result = await self.strava_service.sync_activities(
                user, self.db, after_timestamp=after
            )
        except Exception:
            # Strava's failure modes include an app-level deactivation that
            # affects everyone at once; log it per user and let the Intervals
            # half of the sweep carry on regardless.
            logger.warning("Strava sync failed for user %s", user.id, exc_info=True)
            return 0
        return int(result.get("synced", 0) or 0)

    # ---- candidates -------------------------------------------------------

    def _connected_users(self, limit: Optional[int]) -> List[User]:
        """Runners with somewhere to import from."""
        query = self.db.query(User).filter(
            (User.intervals_athlete_id.isnot(None))
            | (User.strava_athlete_id.isnot(None))
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def _mirrored_plans(self, limit: Optional[int]) -> List[TrainingPlan]:
        """Plans the runner asked us to keep on their watch.

        Every one of them is re-reconciled, not just the ones that changed:
        the window is measured from *today*, so a day passing is itself a
        change — it pulls a new day into the far edge.
        """
        query = self.db.query(TrainingPlan).filter(
            TrainingPlan.watch_sync_enabled.is_(True)
        )
        if limit:
            query = query.limit(limit)
        return query.all()
