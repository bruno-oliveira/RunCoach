"""Strava API integration service."""

import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.run_log import RunLog
from app.models.user import User
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Strava workout_type mapping: 0/None→easy, 1→tempo (race), 2→long, 3→interval (workout)
STRAVA_WORKOUT_TYPE_MAP = {
    0: "easy",
    1: "tempo",
    2: "long",
    3: "interval",
}

# Activity types considered as runs
RUN_ACTIVITY_TYPES = {"Run", "TrailRun", "VirtualRun"}


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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": settings.strava_client_id,
                    "client_secret": settings.strava_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired Strava access token.

        Returns:
            Dict with new access_token, refresh_token, and expires_at.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": settings.strava_client_id,
                    "client_secret": settings.strava_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
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
        db.commit()

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

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def map_activity_to_run_log(
        self, activity: dict[str, Any], user_id: str
    ) -> RunLog:
        """Convert a Strava activity dict to a RunLog instance."""
        distance_km = activity["distance"] / 1000.0
        duration_minutes = activity["moving_time"] / 60.0
        avg_pace = duration_minutes / distance_km if distance_km > 0 else 0

        # Strava cadence is per leg; RunLog expects steps/min (both legs)
        avg_cadence = None
        if activity.get("average_cadence"):
            avg_cadence = int(activity["average_cadence"] * 2)

        workout_type_raw = activity.get("workout_type")
        workout_type = STRAVA_WORKOUT_TYPE_MAP.get(workout_type_raw, "easy")

        # Parse start date — local wall-clock time, stored TZ-naive
        start_date = TimestampAdapter.parse_strava_local(activity["start_date_local"])

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
        page = 1

        while True:
            activities = await self.fetch_activities(
                access_token, after=after_timestamp, page=page
            )
            if not activities:
                break

            for activity in activities:
                # Filter to run activity types only
                if activity.get("type") not in RUN_ACTIVITY_TYPES:
                    continue

                strava_id = str(activity["id"])

                # Deduplicate by strava_activity_id
                existing = (
                    db.query(RunLog)
                    .filter(RunLog.strava_activity_id == strava_id)
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                try:
                    run_log = self.map_activity_to_run_log(activity, user.id)
                    db.add(run_log)
                    db.flush()
                    synced += 1
                except Exception as e:
                    logger.error(
                        f"Error mapping Strava activity {strava_id}: {e}"
                    )
                    errors.append(f"Activity {strava_id}: {str(e)}")

            page += 1

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

    def disconnect(self, user: User, db: Session) -> None:
        """Clear all Strava fields on the user."""
        user.strava_athlete_id = None
        user.strava_access_token = None
        user.strava_refresh_token = None
        user.strava_token_expires_at = None
        user.strava_last_synced_at = None
        db.commit()
