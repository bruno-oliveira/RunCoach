"""Strava API integration service."""

import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.runner.fitness.feedback_service import FeedbackService
from app.core.training.vdot_calculator import VDOTCalculator
from app.infrastructure.config import settings
from app.infrastructure.integrations.activity_dedup import find_duplicate_run
from app.models.run_log import RunLog
from app.models.user import User
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Timeout for all Strava API calls (seconds). Without this a hung connection
# would block the server worker indefinitely.
STRAVA_TIMEOUT = httpx.Timeout(30.0)

# Safety cap on pagination. Strava returns at most 200 activities per page
# (per_page ≤ 200). 200 pages × 50 per page = 10 000 activities — more than
# enough for any real user while protecting against an infinite loop if the
# API ever returns a non-empty page erroneously.
MAX_SYNC_PAGES = 200

# Per-sync cap on detailed-activity fetches. Each inserted run costs one extra
# Strava call for per-km splits; cap it well under Strava's 100-requests /
# 15-minute read limit so a large first sync never exhausts the budget.
# Runs past the cap are still classified, from summary averages only.
MAX_DETAIL_FETCHES_PER_SYNC = 50

# Strava workout_type mapping: 0/None→easy, 1→race, 2→long, 3→interval (workout)
STRAVA_WORKOUT_TYPE_MAP = {
    0: "easy",
    1: "race",
    2: "long",
    3: "interval",
}

# Activity types considered as runs
RUN_ACTIVITY_TYPES = {"Run", "TrailRun", "VirtualRun"}


class StravaApplicationInactiveError(RuntimeError):
    """Raised when Strava has disabled the configured API application."""


def raise_for_strava_status(response: httpx.Response) -> None:
    """Raise a specific error when Strava reports an inactive application."""
    if response.status_code == httpx.codes.FORBIDDEN:
        try:
            errors = response.json().get("errors", [])
        except (TypeError, ValueError):
            errors = []
        if any(
            error.get("resource") == "Application"
            and error.get("field") == "Status"
            and error.get("code") == "Inactive"
            for error in errors
        ):
            raise StravaApplicationInactiveError(
                "The configured Strava API application is inactive"
            )
    response.raise_for_status()


def parse_strava_splits(detail: Optional[dict]) -> Optional[list[dict]]:
    """Compact Strava ``splits_metric`` into per-km dicts for inference/storage.

    Returns ``[{km, duration_s, pace_min_km, avg_hr}, ...]`` or None when the
    activity detail carries no usable per-km splits.
    """
    raw = (detail or {}).get("splits_metric") or []
    compact: list[dict] = []
    for split in raw:
        distance_m = split.get("distance")
        moving_time = split.get("moving_time") or split.get("elapsed_time")
        if not distance_m or not moving_time or distance_m <= 0:
            continue
        distance_km = distance_m / 1000.0
        compact.append(
            {
                "km": round(distance_km, 2),
                "duration_s": int(moving_time),
                "pace_min_km": round((moving_time / 60.0) / distance_km, 2),
                "avg_hr": int(split["average_heartrate"])
                if split.get("average_heartrate")
                else None,
            }
        )
    return compact or None


class StravaService:
    """Service for Strava OAuth and activity sync."""

    def get_authorization_url(self, state: str) -> str:
        """Build Strava OAuth authorization URL."""
        params = {
            "client_id": settings.strava_client_id,
            "redirect_uri": settings.strava_redirect_uri,
            "response_type": "code",
            "scope": "read,activity:read_all",
            "state": state,
        }
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access/refresh tokens.

        Returns:
            Dict with access_token, refresh_token, expires_at, and athlete info.
        """
        async with httpx.AsyncClient(timeout=STRAVA_TIMEOUT) as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": settings.strava_client_id,
                    "client_secret": settings.strava_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            raise_for_strava_status(response)
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired Strava access token.

        Returns:
            Dict with new access_token, refresh_token, and expires_at.
        """
        async with httpx.AsyncClient(timeout=STRAVA_TIMEOUT) as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": settings.strava_client_id,
                    "client_secret": settings.strava_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            raise_for_strava_status(response)
            return response.json()

    async def ensure_valid_token(self, user: User, db: Session) -> str:
        """Check token expiry and refresh if needed. Returns a valid access token."""
        if not user.strava_refresh_token:
            raise ValueError("User has no Strava refresh token")

        now = int(time.time())
        # Refresh if token expires within 5 minutes
        if user.strava_token_expires_at and user.strava_token_expires_at > now + 300:
            return user.strava_access_token

        logger.info(f"Refreshing Strava token for user {user.id}")
        token_data = await self.refresh_access_token(user.strava_refresh_token)

        user.strava_access_token = token_data["access_token"]
        user.strava_refresh_token = token_data["refresh_token"]
        user.strava_token_expires_at = token_data["expires_at"]
        try:
            db.commit()
        except Exception as commit_err:
            db.rollback()
            logger.error(
                f"Failed to persist refreshed Strava token for user {user.id}: {commit_err}"
            )
            # Re-raise so the caller knows the token state is unreliable.
            raise

        return user.strava_access_token

    async def fetch_activities(
        self,
        access_token: str,
        after: Optional[int] = None,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Fetch activities from Strava API."""
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if after is not None:
            params["after"] = after

        async with httpx.AsyncClient(timeout=STRAVA_TIMEOUT) as client:
            response = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            raise_for_strava_status(response)
            return response.json()

    async def fetch_activity_detail(
        self, access_token: str, activity_id: str
    ) -> Optional[dict[str, Any]]:
        """Fetch a single activity's detail (includes ``splits_metric``, laps).

        Returns the activity dict, or None on any error (rate limit, 404, etc.)
        so the caller can fall back to summary-only data without failing sync.
        """
        try:
            async with httpx.AsyncClient(timeout=STRAVA_TIMEOUT) as client:
                response = await client.get(
                    f"{STRAVA_API_BASE}/activities/{activity_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"include_all_efforts": "false"},
                )
                raise_for_strava_status(response)
                return response.json()
        except Exception as e:
            logger.warning(
                "Strava activity-detail fetch failed for %s: %s", activity_id, e
            )
            return None

    def map_activity_to_run_log(self, activity: dict[str, Any], user_id: str) -> RunLog:
        """Convert a Strava activity dict to a RunLog instance."""
        # Validate required fields up-front so any problem produces a clear
        # ValueError rather than an opaque KeyError or TypeError deep in the
        # mapping logic.
        distance_m = activity.get("distance")
        moving_time_s = activity.get("moving_time")
        start_date_local_str = activity.get("start_date_local")

        if distance_m is None:
            raise ValueError("Activity is missing required field 'distance'")
        if moving_time_s is None:
            raise ValueError("Activity is missing required field 'moving_time'")
        if not start_date_local_str:
            raise ValueError("Activity is missing required field 'start_date_local'")

        distance_km = distance_m / 1000.0
        duration_minutes = moving_time_s / 60.0
        avg_pace = duration_minutes / distance_km if distance_km > 0 else 0

        # Strava cadence is per leg; RunLog expects steps/min (both legs)
        avg_cadence = None
        if activity.get("average_cadence"):
            avg_cadence = round(activity["average_cadence"] * 2)

        workout_type_raw = activity.get("workout_type")
        workout_type = STRAVA_WORKOUT_TYPE_MAP.get(workout_type_raw, "easy")

        # Parse start date — local wall-clock time, stored TZ-naive
        start_date = TimestampAdapter.parse_strava_local(start_date_local_str)

        return RunLog(
            user_id=user_id,
            strava_activity_id=str(activity["id"]),
            date=start_date,
            distance_km=round(distance_km, 2),
            duration_minutes=round(duration_minutes, 2),
            avg_pace_min_km=round(avg_pace, 2) if avg_pace else None,
            avg_heart_rate=(
                int(activity["average_heartrate"])
                if activity.get("average_heartrate")
                else None
            ),
            max_heart_rate=(
                int(activity["max_heartrate"])
                if activity.get("max_heartrate")
                else None
            ),
            avg_cadence=avg_cadence,
            elevation_gain_m=(
                int(activity["total_elevation_gain"])
                if activity.get("total_elevation_gain")
                else None
            ),
            workout_type=workout_type,
            notes=activity.get("name"),
        )

    @staticmethod
    def _apply_vdot(run_log: RunLog) -> None:
        """Auto-calculate VDOT for runs with sufficient distance/duration."""
        if run_log.distance_km >= 2.0 and run_log.duration_minutes > 0:
            vdot = VDOTCalculator.calculate_vdot(
                run_log.distance_km,
                int(run_log.duration_minutes * 60),
                elevation_gain_m=run_log.elevation_gain_m,
            )
            if vdot:
                run_log.vdot = vdot

    @staticmethod
    def _classify_effort_and_type(run_log: RunLog, user: User, db: Session) -> None:
        """Best-effort effort-class and workout-type inference (non-fatal).

        Strava defaults workout_type to "easy"; these classifiers infer the
        real effort class and workout type from pace/HR/distance/splits. Each
        is wrapped independently so one failing never blocks the other or the
        sync itself.
        """
        try:
            from app.contexts.runner.fitness.effort_classifier import classify_effort

            effort_class = classify_effort(
                distance_km=run_log.distance_km,
                avg_pace_min_km=run_log.avg_pace_min_km,
                perceived_effort=run_log.perceived_effort,
                user_id=user.id,
                db=db,
                exclude_run_id=run_log.id,
            )
            if effort_class is not None:
                run_log.effort_class = effort_class
        except Exception as cls_err:
            logger.warning(
                f"Effort classification failed for Strava run {run_log.id}: {cls_err}"
            )
        try:
            from app.contexts.runner.fitness.workout_type_classifier import (
                classify_workout_type,
            )

            wt_result = classify_workout_type(
                distance_km=run_log.distance_km,
                duration_minutes=run_log.duration_minutes,
                avg_pace_min_km=run_log.avg_pace_min_km,
                avg_heart_rate=run_log.avg_heart_rate,
                max_heart_rate=run_log.max_heart_rate,
                elevation_gain_m=run_log.elevation_gain_m,
                perceived_effort=run_log.perceived_effort,
                splits=run_log.splits,
                vdot=run_log.vdot,
                user_id=user.id,
                db=db,
                exclude_run_id=run_log.id,
            )
            if wt_result is not None:
                (
                    run_log.inferred_workout_type,
                    run_log.inferred_type_confidence,
                ) = wt_result
        except Exception as cls_err:
            logger.warning(
                f"Workout-type inference failed for Strava run {run_log.id}: {cls_err}"
            )

    async def _ingest_activity(
        self,
        activity: dict[str, Any],
        user: User,
        db: Session,
        access_token: str,
        detail_fetches: int,
    ) -> tuple[str, int, Optional[str]]:
        """Ingest one Strava activity into a RunLog.

        Returns ``(outcome, detail_fetches, error)`` where outcome is one of
        ``"filtered"`` (not a run), ``"skipped"`` (duplicate), ``"synced"``,
        or ``"error"`` (mapping failed; ``error`` carries the message). The
        per-sync detail-fetch budget is threaded through and returned so the
        caller's cap stays accurate.
        """
        # Filter to run activity types only. Check both `type` (deprecated)
        # and `sport_type` (current) because Strava's v3 API may return
        # `type=null` for newer activities that only set `sport_type`, and
        # Garmin-synced activities in particular can arrive with no `type`.
        if (
            activity.get("type") not in RUN_ACTIVITY_TYPES
            and activity.get("sport_type") not in RUN_ACTIVITY_TYPES
        ):
            return "filtered", detail_fetches, None

        strava_id = str(activity["id"])

        # Deduplicate by strava_activity_id
        existing = (
            db.query(RunLog).filter(RunLog.strava_activity_id == strava_id).first()
        )
        if existing:
            return "skipped", detail_fetches, None

        try:
            run_log = self.map_activity_to_run_log(activity, user.id)
            duplicate = find_duplicate_run(
                db, user.id, run_log.date, run_log.distance_km
            )
            if duplicate is not None:
                # Already imported from Intervals.icu — the watch feeds both.
                # Keep the id on the row we have so the next sync short-circuits
                # on the cheap lookup above instead of re-deriving this.
                if duplicate.strava_activity_id is None:
                    duplicate.strava_activity_id = strava_id
                return "skipped", detail_fetches, None
            self._apply_vdot(run_log)
            # Pull per-km splits (one extra call per inserted run) to sharpen
            # the workout-type inference. Bounded per sync to respect Strava's
            # rate limit; on failure we fall back to summary averages.
            if detail_fetches < MAX_DETAIL_FETCHES_PER_SYNC:
                detail = await self.fetch_activity_detail(access_token, strava_id)
                detail_fetches += 1
                if detail:
                    run_log.splits = parse_strava_splits(detail)
            self._classify_effort_and_type(run_log, user, db)
            if not self._persist_with_savepoint(run_log, db):
                return "skipped", detail_fetches, None
            # Generate coaching feedback (non-fatal)
            try:
                FeedbackService.generate_and_store(run_log, db)
            except Exception as fb_err:
                logger.warning(
                    f"Feedback generation failed for Strava run {run_log.id}: {fb_err}"
                )
            return "synced", detail_fetches, None
        except Exception as e:
            logger.error(f"Error mapping Strava activity {strava_id}: {e}")
            return "error", detail_fetches, f"Activity {strava_id}: {str(e)}"

    @staticmethod
    def _persist_with_savepoint(run_log: RunLog, db: Session) -> bool:
        """Flush one run inside a SAVEPOINT.

        Wrapping each activity flush in a nested transaction means an
        IntegrityError (a concurrent-sync race past the dedup SELECT) only
        rolls back THIS activity, not every activity flushed earlier in the
        loop. Returns ``False`` when the run was a duplicate and got rolled
        back, ``True`` when it flushed cleanly.
        """
        db.add(run_log)
        sp = db.begin_nested()
        try:
            db.flush()
            sp.commit()
            return True
        except IntegrityError:
            sp.rollback()
            db.expunge(run_log)
            return False

    async def sync_activities(
        self, user: User, db: Session, after_timestamp: Optional[int] = None
    ) -> dict[str, Any]:
        """Sync Strava activities into RunLog entries.

        Args:
            user: User to sync activities for
            db: Database session
            after_timestamp: Unix epoch; only fetch activities after this time.
                             If None, fetches all historical activities.

        Returns:
            Dict with synced count, skipped count, errors list, total count,
            and last_synced_at timestamp.
        """
        access_token = await self.ensure_valid_token(user, db)

        # Capture sync start time BEFORE any API calls so the cursor always
        # advances, even if this sync takes a while. The router subtracts a
        # 24-hour buffer when passing `after_timestamp`, so runs whose
        # start_date fell before this timestamp are still fetched next time.
        sync_started_at = int(time.time())

        synced = 0
        skipped = 0
        errors: list[str] = []
        detail_fetches = 0
        page = 1

        while page <= MAX_SYNC_PAGES:
            activities = await self.fetch_activities(
                access_token, after=after_timestamp, page=page
            )
            if not activities:
                break

            for activity in activities:
                outcome, detail_fetches, error = await self._ingest_activity(
                    activity, user, db, access_token, detail_fetches
                )
                if outcome == "synced":
                    synced += 1
                elif outcome == "skipped":
                    skipped += 1
                elif outcome == "error" and error:
                    errors.append(error)
                # "filtered" (non-run activity) is ignored entirely.

            page += 1

        if page > MAX_SYNC_PAGES:
            logger.warning(
                f"Strava sync for user {user.id} hit the {MAX_SYNC_PAGES}-page cap. "
                "Some activities may not have been fetched."
            )

        user.strava_last_synced_at = sync_started_at
        db.commit()

        total = db.query(RunLog).filter(RunLog.user_id == user.id).count()

        logger.info(
            f"Strava sync for user {user.id}: {synced} synced, {skipped} skipped, "
            f"{len(errors)} errors, {total} total runs"
        )
        return {
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "total": total,
            "last_synced_at": sync_started_at,
        }

    async def revoke_token(self, access_token: str) -> bool:
        """Revoke an access token via Strava's deauthorize endpoint.

        Returns True if revocation succeeded, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=STRAVA_TIMEOUT) as client:
                response = await client.post(
                    STRAVA_DEAUTH_URL,
                    params={"access_token": access_token},
                )
                raise_for_strava_status(response)
                return True
        except Exception as e:
            logger.warning("Strava token revocation failed: %s", e)
            return False

    async def disconnect(self, user: User, db: Session) -> None:
        """Revoke access with Strava and clear all stored credentials."""
        if user.strava_access_token:
            try:
                token = await self.ensure_valid_token(user, db)
                await self.revoke_token(token)
            except Exception as e:
                logger.warning(
                    "Could not revoke Strava token for user %s: %s", user.id, e
                )
        user.strava_athlete_id = None
        user.strava_access_token = None
        user.strava_refresh_token = None
        user.strava_token_expires_at = None
        user.strava_last_synced_at = None
        db.commit()
