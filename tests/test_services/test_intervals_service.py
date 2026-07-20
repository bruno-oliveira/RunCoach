"""Unit tests for IntervalsService."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
    IntervalsService,
    raise_for_intervals_status,
)
from app.models.run_log import RunLog
from app.models.user import User


@pytest.fixture
def intervals_service():
    return IntervalsService()


@pytest.fixture
def intervals_user():
    return User(
        id="intervals-user",
        email="intervals@example.com",
        intervals_athlete_id="i123",
        intervals_access_token="access-token",
    )


@pytest.fixture
def intervals_activity():
    return {
        "id": "i987654",
        "start_date_local": "2026-07-18T07:30:00",
        "type": "Run",
        "name": "Morning Run",
        "icu_distance": 10000.0,
        "moving_time": 3000,
        "average_heartrate": 155.0,
        "max_heartrate": 175.0,
        "average_cadence": 85.0,
        "total_elevation_gain": 120.0,
        "source": "GARMIN_CONNECT",
    }


def test_authorization_url(intervals_service):
    with (
        patch("app.infrastructure.config.settings.intervals_client_id", "client-1"),
        patch(
            "app.infrastructure.config.settings.intervals_redirect_uri",
            "https://runcoach.example/api/intervals/callback",
        ),
    ):
        url = intervals_service.get_authorization_url("state-1")

    assert url.startswith("https://intervals.icu/oauth/authorize?")
    assert "client_id=client-1" in url
    assert "scope=ACTIVITY%3AREAD" in url
    assert "state=state-1" in url


def test_maps_activity_to_existing_run_model(intervals_service, intervals_activity):
    run = intervals_service.map_activity_to_run_log(
        intervals_activity, "intervals-user"
    )

    assert run.intervals_activity_id == "i987654"
    assert run.distance_km == 10.0
    assert run.duration_minutes == 50.0
    assert run.avg_pace_min_km == 5.0
    assert run.avg_heart_rate == 155
    assert run.avg_cadence == 170
    assert run.elevation_gain_m == 120
    assert run.workout_type is None


def test_authorization_errors_are_specific():
    response = httpx.Response(
        401,
        request=httpx.Request("GET", "https://intervals.icu/api/v1/athlete/0"),
    )

    with pytest.raises(IntervalsAuthorizationError):
        raise_for_intervals_status(response)


@pytest.mark.asyncio
async def test_sync_creates_and_deduplicates_run(
    intervals_service, intervals_user, intervals_activity, test_db
):
    test_db.add(intervals_user)
    test_db.commit()

    with patch.object(
        intervals_service,
        "fetch_activities",
        new_callable=AsyncMock,
        return_value=[intervals_activity],
    ):
        first = await intervals_service.sync_activities(
            intervals_user, test_db, after_timestamp=int(time.time()) - 86400
        )
        second = await intervals_service.sync_activities(
            intervals_user, test_db, after_timestamp=int(time.time()) - 86400
        )

    assert first["synced"] == 1
    assert second["synced"] == 0
    assert second["skipped"] == 1
    runs = test_db.query(RunLog).filter(RunLog.user_id == intervals_user.id).all()
    assert len(runs) == 1
    assert runs[0].intervals_activity_id == "i987654"
    assert intervals_user.intervals_last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_ignores_strava_stubs_and_non_runs(
    intervals_service, intervals_user, intervals_activity, test_db
):
    test_db.add(intervals_user)
    test_db.commit()
    activities = [
        {**intervals_activity, "id": "strava", "source": "STRAVA"},
        {**intervals_activity, "id": "ride", "type": "Ride"},
    ]

    with patch.object(
        intervals_service,
        "fetch_activities",
        new_callable=AsyncMock,
        return_value=activities,
    ):
        result = await intervals_service.sync_activities(
            intervals_user, test_db, after_timestamp=int(time.time()) - 86400
        )

    assert result["synced"] == 0
    assert test_db.query(RunLog).count() == 0
