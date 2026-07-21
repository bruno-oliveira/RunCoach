"""Intervals.icu OAuth and activity sync service."""

import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.runner.fitness.feedback_service import FeedbackService
from app.infrastructure.config import settings
from app.infrastructure.integrations.strava_service import StravaService
from app.models.run_log import RunLog
from app.models.user import User

logger = logging.getLogger(__name__)

INTERVALS_AUTH_URL = "https://intervals.icu/oauth/authorize"
INTERVALS_TOKEN_URL = "https://intervals.icu/api/oauth/token"
INTERVALS_API_BASE = "https://intervals.icu/api/v1"
INTERVALS_TIMEOUT = httpx.Timeout(30.0)
RUN_ACTIVITY_TYPES = {"Run", "TrailRun", "VirtualRun"}
ACTIVITY_FIELDS = ",".join(
    (
        "id",
        "start_date_local",
        "type",
        "name",
        "icu_distance",
        "distance",
        "moving_time",
        "elapsed_time",
        "average_heartrate",
        "max_heartrate",
        "average_cadence",
        "total_elevation_gain",
        "source",
    )
)


class IntervalsAuthorizationError(RuntimeError):
    """Raised when an Intervals.icu token is invalid or lacks activity scope."""


def raise_for_intervals_status(response: httpx.Response) -> None:
    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        raise IntervalsAuthorizationError(
            "Intervals.icu authorization is invalid or missing ACTIVITY:READ"
        )
    response.raise_for_status()


class IntervalsService:
    """Service for one-time OAuth connection and incremental activity imports."""

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": settings.intervals_client_id,
            "redirect_uri": settings.intervals_redirect_uri,
            # ACTIVITY:READ powers the activity import; CALENDAR:WRITE lets us
            # push planned workouts to the athlete's calendar (send to watch).
            "scope": "ACTIVITY:READ,CALENDAR:WRITE",
            "state": state,
        }
        return f"{INTERVALS_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            response = await client.post(
                INTERVALS_TOKEN_URL,
                data={
                    "client_id": settings.intervals_client_id,
                    "client_secret": settings.intervals_client_secret,
                    "code": code,
                },
            )
            raise_for_intervals_status(response)
            return response.json()

    async def fetch_activities(
        self,
        access_token: str,
        oldest: str,
        newest: str,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            response = await client.get(
                f"{INTERVALS_API_BASE}/athlete/0/activities",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "oldest": oldest,
                    "newest": newest,
                    "fields": ACTIVITY_FIELDS,
                },
            )
            raise_for_intervals_status(response)
            return response.json()

    async def push_workout(
        self,
        access_token: str,
        athlete_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Upsert a single planned workout onto the athlete's calendar.

        Uses the bulk-events endpoint with ``upsert=true`` so re-sending the
        same workout (matched by ``external_id``) updates it rather than
        creating a duplicate. Once the athlete has linked Garmin Connect and
        enabled planned-workout upload in Intervals.icu, the event is pushed to
        Garmin automatically.

        Args:
            access_token: The athlete's Intervals.icu OAuth token (needs
                CALENDAR:WRITE — old tokens without it raise
                IntervalsAuthorizationError via a 403).
            athlete_id: The athlete's Intervals.icu id.
            event: A single calendar event dict (category/type/start_date_local/
                name/description/external_id/...).

        Returns:
            The created/updated event dict from Intervals.icu.
        """
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            response = await client.post(
                f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events/bulk",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"upsert": "true"},
                json=[event],
            )
            raise_for_intervals_status(response)
            created = response.json()
            return created[0] if isinstance(created, list) and created else {}

    @staticmethod
    def map_activity_to_run_log(activity: dict[str, Any], user_id: str) -> RunLog:
        distance_m = activity.get("icu_distance")
        if distance_m is None:
            distance_m = activity.get("distance")
        moving_time_s = activity.get("moving_time")
        if moving_time_s is None:
            moving_time_s = activity.get("elapsed_time")
        start_date_local = activity.get("start_date_local")

        if distance_m is None:
            raise ValueError("Activity is missing distance")
        if moving_time_s is None:
            raise ValueError("Activity is missing duration")
        if not start_date_local:
            raise ValueError("Activity is missing start_date_local")

        distance_km = float(distance_m) / 1000.0
        duration_minutes = float(moving_time_s) / 60.0
        avg_cadence = activity.get("average_cadence")

        return RunLog(
            user_id=user_id,
            intervals_activity_id=str(activity["id"]),
            date=datetime.fromisoformat(str(start_date_local).replace("Z", "")),
            distance_km=round(distance_km, 2),
            duration_minutes=round(duration_minutes, 2),
            avg_pace_min_km=(
                round(duration_minutes / distance_km, 2) if distance_km > 0 else None
            ),
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
            avg_cadence=round(float(avg_cadence) * 2) if avg_cadence else None,
            elevation_gain_m=(
                round(float(activity["total_elevation_gain"]))
                if activity.get("total_elevation_gain") is not None
                else None
            ),
            workout_type=None,
            notes=activity.get("name"),
        )

    @staticmethod
    def _persist(run_log: RunLog, db: Session) -> bool:
        try:
            with db.begin_nested():
                db.add(run_log)
                db.flush()
            return True
        except IntegrityError:
            return False

    async def sync_activities(
        self,
        user: User,
        db: Session,
        after_timestamp: int,
    ) -> dict[str, Any]:
        if not user.intervals_access_token:
            raise IntervalsAuthorizationError("User has no Intervals.icu access token")

        sync_started_at = int(time.time())
        oldest = datetime.fromtimestamp(after_timestamp, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        newest = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        activities = await self.fetch_activities(
            user.intervals_access_token, oldest, newest
        )

        synced = 0
        skipped = 0
        errors: list[str] = []

        for activity in activities:
            if activity.get("source") == "STRAVA":
                continue
            if activity.get("type") not in RUN_ACTIVITY_TYPES:
                continue

            activity_id = str(activity.get("id", ""))
            if not activity_id:
                errors.append("Activity is missing id")
                continue
            existing = (
                db.query(RunLog)
                .filter(RunLog.intervals_activity_id == activity_id)
                .first()
            )
            if existing:
                skipped += 1
                continue

            try:
                run_log = self.map_activity_to_run_log(activity, str(user.id))
                StravaService._apply_vdot(run_log)
                StravaService._classify_effort_and_type(run_log, user, db)
                if not self._persist(run_log, db):
                    skipped += 1
                    continue
                try:
                    FeedbackService.generate_and_store(run_log, db)
                except Exception as feedback_error:
                    logger.warning(
                        "Feedback generation failed for Intervals activity %s: %s",
                        activity_id,
                        feedback_error,
                    )
                synced += 1
            except Exception as error:
                logger.error(
                    "Error importing Intervals activity %s: %s", activity_id, error
                )
                errors.append(f"Activity {activity_id}: {error}")

        user.intervals_last_synced_at = sync_started_at
        db.commit()
        total = db.query(RunLog).filter(RunLog.user_id == user.id).count()
        return {
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "total": total,
            "last_synced_at": sync_started_at,
        }

    async def disconnect(self, user: User, db: Session) -> None:
        user.intervals_athlete_id = None
        user.intervals_access_token = None
        user.intervals_last_synced_at = None
        db.commit()
