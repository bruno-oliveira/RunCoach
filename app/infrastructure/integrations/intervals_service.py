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
from app.infrastructure.integrations.activity_dedup import find_duplicate_run
from app.infrastructure.integrations.run_enrichment import (
    apply_vdot,
    classify_effort_and_type,
)
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


# Coarse plausibility bounds for HR values read from Intervals.icu. Deliberately
# wider than the zone calculator's "reliable" bands — this only filters out
# obvious junk (nulls, zeros, sensor garbage); the calculator clamps LTHR
# relative to max HR when it builds the zones.
_MIN_PLAUSIBLE_HR = 90
_MAX_PLAUSIBLE_HR = 230
_MIN_PLAUSIBLE_RESTING_HR = 25
_MAX_PLAUSIBLE_RESTING_HR = 110


def _plausible(value: Any, low: int, high: int) -> "int | None":
    """Return ``value`` as an int when it is a number within ``[low, high]``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    ivalue = int(value)
    return ivalue if low <= ivalue <= high else None


def parse_athlete_hr_settings(athlete: dict[str, Any]) -> dict[str, "int | None"]:
    """Extract max HR / LTHR / resting HR from an Intervals.icu athlete object.

    Intervals stores per-sport HR settings in ``sportSettings`` (each entry
    lists the ``types`` it applies to); resting HR is an athlete-level value.
    We prefer the Run sport's settings, falling back to the first entry that
    carries HR values. Every field is plausibility-checked, so a missing or junk
    value simply comes back as ``None`` rather than poisoning the zones.
    """
    sport_settings = athlete.get("sportSettings")
    run_settings: dict[str, Any] = {}
    fallback_settings: dict[str, Any] = {}
    if isinstance(sport_settings, list):
        for entry in sport_settings:
            if not isinstance(entry, dict):
                continue
            types = entry.get("types") or []
            has_hr = entry.get("max_hr") is not None or entry.get("lthr") is not None
            if isinstance(types, list) and "Run" in types:
                run_settings = entry
                break
            if has_hr and not fallback_settings:
                fallback_settings = entry
    settings_entry = run_settings or fallback_settings

    resting = athlete.get("icu_resting_hr")
    if resting is None:
        resting = athlete.get("restingHR")

    return {
        "max_hr": _plausible(
            settings_entry.get("max_hr"), _MIN_PLAUSIBLE_HR, _MAX_PLAUSIBLE_HR
        ),
        "lthr": _plausible(
            settings_entry.get("lthr"), _MIN_PLAUSIBLE_HR, _MAX_PLAUSIBLE_HR
        ),
        "resting_hr": _plausible(
            resting, _MIN_PLAUSIBLE_RESTING_HR, _MAX_PLAUSIBLE_RESTING_HR
        ),
    }


def apply_hr_settings_to_user(user: User, hr_settings: dict[str, "int | None"]) -> bool:
    """Store synced Intervals HR anchors on the user's ``intervals_*`` columns.

    Writes only the ``intervals_*`` provenance columns — never the manual
    ``max_hr`` / ``threshold_hr`` / ``resting_hr`` a runner may have typed in —
    so a manual entry always wins in zone resolution. Returns True when any value
    changed (so the caller can decide whether a commit is worthwhile).
    """
    changed = False
    for source_key, column in (
        ("max_hr", "intervals_max_hr"),
        ("lthr", "intervals_lthr"),
        ("resting_hr", "intervals_resting_hr"),
    ):
        value = hr_settings.get(source_key)
        if value is not None and getattr(user, column) != value:
            setattr(user, column, value)
            changed = True
    return changed


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

    async def fetch_athlete_settings(
        self,
        access_token: str,
        athlete_id: str,
    ) -> dict[str, Any]:
        """Fetch the athlete's HR settings (max HR / LTHR / resting HR).

        Reads the Intervals.icu athlete object and pulls the Run sport's
        ``max_hr`` and ``lthr`` plus the athlete's resting HR, so RunCoach's HR
        zones can anchor on the exact values the runner already configured on
        their connected platform. Returns a dict with ``max_hr`` / ``lthr`` /
        ``resting_hr`` (any of which may be ``None`` when Intervals has no value).
        """
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            response = await client.get(
                f"{INTERVALS_API_BASE}/athlete/{athlete_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            raise_for_intervals_status(response)
            return parse_athlete_hr_settings(response.json())

    async def fetch_events(
        self,
        access_token: str,
        athlete_id: str,
        oldest: str,
        newest: str,
    ) -> list[dict[str, Any]]:
        """List the athlete's calendar events between two ISO dates.

        The reconciler's read half. Knowing what is *actually* on the calendar is
        what separates "we pushed this once" from "this is on the runner's
        watch" — and it is how we find our own stale events to clean up.
        """
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            response = await client.get(
                f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"oldest": oldest, "newest": newest},
            )
            raise_for_intervals_status(response)
            events = response.json()
            return events if isinstance(events, list) else []

    async def delete_events(
        self,
        access_token: str,
        athlete_id: str,
        event_ids: list[Any],
    ) -> int:
        """Delete calendar events by Intervals.icu id; returns how many went.

        This deletes whatever it is given. The calendar belongs to the runner —
        it holds their own workouts, their coach's, and events from every other
        app they have connected — so establishing that an id is RunCoach's is
        the *caller's* job. See ``watch_sync_service.owns_event``, which is the
        only thing standing between this method and a stranger's training week.

        A dead token fails the whole batch fast (nothing else would work
        either); any other per-event failure is logged and skipped, since a
        calendar we can't fully tidy is better than one we abandon halfway.
        """
        if not event_ids:
            return 0
        base = f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events"
        headers = {"Authorization": f"Bearer {access_token}"}
        deleted = 0
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            for event_id in event_ids:
                response = await client.delete(f"{base}/{event_id}", headers=headers)
                if response.status_code in (
                    httpx.codes.UNAUTHORIZED,
                    httpx.codes.FORBIDDEN,
                ):
                    raise IntervalsAuthorizationError(
                        "Intervals.icu authorization is invalid or missing "
                        "CALENDAR:WRITE"
                    )
                if response.status_code >= 400:
                    logger.warning(
                        "Intervals.icu delete of event %s failed with %s",
                        event_id,
                        response.status_code,
                    )
                    continue
                deleted += 1
        return deleted

    async def _delete_existing_events(
        self,
        client: httpx.AsyncClient,
        athlete_id: str,
        access_token: str,
        oldest: str,
        newest: str,
        external_ids: set[str],
    ) -> None:
        """Delete planned events matching ``external_ids`` in a date range.

        Intervals.icu only re-triggers the Garmin export when an event is
        *created*, not when an existing one is updated in place. So re-sending a
        workout must delete the old event first, otherwise the watch keeps the
        stale copy (or never receives pace targets set after the first send).

        One range query covers the whole batch, so pushing a week costs a single
        lookup rather than one per day. Best-effort: a lookup/delete failure must
        not block the create below — it degrades to the old update-in-place
        behaviour, never worse. A genuine auth failure surfaces on the create's
        ``raise_for_intervals_status``.
        """
        base = f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            existing = await client.get(
                base,
                headers=headers,
                params={"oldest": oldest, "newest": newest},
            )
            if existing.status_code >= 400:
                return
            for ev in existing.json():
                if isinstance(ev, dict) and ev.get("external_id") in external_ids:
                    await client.delete(f"{base}/{ev['id']}", headers=headers)
        except Exception as delete_error:
            logger.warning(
                "Intervals.icu pre-delete of %s failed (will still create): %s",
                sorted(external_ids),
                delete_error,
            )

    async def push_workouts(
        self,
        access_token: str,
        athlete_id: str,
        events: list[dict[str, Any]],
        pre_delete: bool = True,
    ) -> list[dict[str, Any]]:
        """Create planned workouts on the athlete's calendar in one request.

        Deletes any prior events carrying the same ``external_id``s across the
        batch's date span, then creates them fresh (bulk endpoint,
        ``upsert=true``). The delete is what makes re-sends actually reach the
        watch: Intervals.icu re-triggers the Garmin export on create but not on
        in-place update. Once the athlete has linked their watch platform and
        enabled planned-workout upload in Intervals.icu, the created events are
        forwarded automatically.

        Args:
            access_token: The athlete's Intervals.icu OAuth token (needs
                CALENDAR:WRITE — old tokens without it raise
                IntervalsAuthorizationError via a 403).
            athlete_id: The athlete's Intervals.icu id.
            events: Calendar event dicts (category/type/start_date_local/name/
                description/external_id/...).
            pre_delete: Look up and remove same-``external_id`` events first.
                Leave it on for one-off sends. The reconciler turns it off
                because it has already fetched the window and deleted precisely
                what changed — repeating that here would cost a second lookup
                per push and delete events it deliberately kept.

        Returns:
            The created event dicts from Intervals.icu, or [] when ``events`` is
            empty.
        """
        if not events:
            return []
        dates = sorted(
            d for d in (str(e.get("start_date_local", ""))[:10] for e in events) if d
        )
        external_ids = {
            str(e["external_id"]) for e in events if e.get("external_id") is not None
        }
        async with httpx.AsyncClient(timeout=INTERVALS_TIMEOUT) as client:
            if pre_delete and dates and external_ids:
                await self._delete_existing_events(
                    client, athlete_id, access_token, dates[0], dates[-1], external_ids
                )
            response = await client.post(
                f"{INTERVALS_API_BASE}/athlete/{athlete_id}/events/bulk",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"upsert": "true"},
                json=events,
            )
            raise_for_intervals_status(response)
            created = response.json()
            return created if isinstance(created, list) else []

    async def push_workout(
        self,
        access_token: str,
        athlete_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a single planned workout — see :meth:`push_workouts`."""
        created = await self.push_workouts(access_token, athlete_id, [event])
        return created[0] if created else {}

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
        # Refresh the runner's HR anchors from their Intervals.icu settings so
        # RunCoach's zones stay faithful to the connected platform. Best-effort:
        # a settings-fetch failure must never block the activity import.
        if user.intervals_athlete_id:
            try:
                hr_settings = await self.fetch_athlete_settings(
                    user.intervals_access_token, user.intervals_athlete_id
                )
                apply_hr_settings_to_user(user, hr_settings)
            except Exception as settings_error:
                logger.warning(
                    "Intervals.icu HR settings fetch failed for user %s: %s",
                    user.id,
                    settings_error,
                )

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
            # Activities Intervals.icu itself pulled from Strava used to be
            # skipped here, because RunCoach imported those from Strava
            # directly and would otherwise store them twice. That importer is
            # gone, so skipping them now just loses runs — and `find_duplicate_run`
            # below is what keeps the ones we already hold from arriving twice.
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
                duplicate = find_duplicate_run(
                    db, str(user.id), run_log.date, run_log.distance_km
                )
                if duplicate is not None:
                    # Already stored — most of this runner's history arrived
                    # through the retired Strava import, and a deep backfill
                    # reaches back into it. Keep the id on the row we have so
                    # the next sync short-circuits on the cheap lookup above.
                    if duplicate.intervals_activity_id is None:
                        duplicate.intervals_activity_id = activity_id
                    skipped += 1
                    continue
                apply_vdot(run_log)
                classify_effort_and_type(run_log, user, db)
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
