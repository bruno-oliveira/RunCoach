"""Unit tests for StravaService."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.integrations.strava_service import (
    StravaService,
    parse_strava_splits,
)
from app.models.run_log import RunLog
from app.models.user import User


@pytest.fixture
def strava_service():
    return StravaService()


@pytest.fixture(autouse=True)
def _stub_activity_detail():
    """Keep sync hermetic: never hit Strava's activity-detail endpoint unless a
    test explicitly opts in by re-patching fetch_activity_detail."""
    with patch.object(
        StravaService,
        "fetch_activity_detail",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture
def mock_user():
    user = User(
        id="user-123",
        email="test@example.com",
        strava_athlete_id="12345",
        strava_access_token="access-token",
        strava_refresh_token="refresh-token",
        strava_token_expires_at=int(time.time()) + 3600,
    )
    return user


@pytest.fixture
def sample_strava_activity():
    return {
        "id": 9876543210,
        "name": "Morning Run",
        "type": "Run",
        "distance": 10000.0,  # 10km in meters
        "moving_time": 3000,  # 50 minutes in seconds
        "start_date_local": "2026-02-15T07:30:00",
        "average_heartrate": 155.0,
        "max_heartrate": 175.0,
        "average_cadence": 85.0,  # per leg
        "total_elevation_gain": 120.0,
        "workout_type": 0,
    }


class TestGetAuthorizationUrl:
    def test_returns_valid_url(self, strava_service):
        url = strava_service.get_authorization_url("test-state")
        assert "https://www.strava.com/oauth/authorize" in url
        assert "client_id=" in url
        assert "redirect_uri=" in url
        assert "scope=read%2Cactivity%3Aread_all" in url
        assert "state=test-state" in url
        assert "response_type=code" in url


class TestMapActivityToRunLog:
    def test_basic_mapping(self, strava_service, sample_strava_activity):
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert isinstance(run_log, RunLog)
        assert run_log.user_id == "user-123"
        assert run_log.strava_activity_id == "9876543210"
        assert run_log.distance_km == 10.0
        assert run_log.duration_minutes == 50.0
        assert run_log.avg_heart_rate == 155
        assert run_log.max_heart_rate == 175
        assert run_log.elevation_gain_m == 120
        assert run_log.notes == "Morning Run"

    def test_cadence_doubled(self, strava_service, sample_strava_activity):
        """Strava reports cadence per leg; we store steps/min (both legs)."""
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.avg_cadence == 170  # 85 * 2

    def test_no_cadence(self, strava_service, sample_strava_activity):
        sample_strava_activity["average_cadence"] = None
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.avg_cadence is None

    def test_pace_calculation(self, strava_service, sample_strava_activity):
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        # 50 min / 10 km = 5.0 min/km
        assert run_log.avg_pace_min_km == 5.0

    def test_workout_type_mapping_easy(self, strava_service, sample_strava_activity):
        sample_strava_activity["workout_type"] = 0
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.workout_type == "easy"

    def test_workout_type_mapping_race(self, strava_service, sample_strava_activity):
        sample_strava_activity["workout_type"] = 1
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.workout_type == "race"

    def test_workout_type_mapping_long(self, strava_service, sample_strava_activity):
        sample_strava_activity["workout_type"] = 2
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.workout_type == "long"

    def test_workout_type_mapping_workout(self, strava_service, sample_strava_activity):
        sample_strava_activity["workout_type"] = 3
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.workout_type == "interval"

    def test_workout_type_none_defaults_easy(
        self, strava_service, sample_strava_activity
    ):
        sample_strava_activity["workout_type"] = None
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.workout_type == "easy"

    def test_no_heart_rate(self, strava_service, sample_strava_activity):
        del sample_strava_activity["average_heartrate"]
        del sample_strava_activity["max_heartrate"]
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.avg_heart_rate is None
        assert run_log.max_heart_rate is None

    def test_date_parsing(self, strava_service, sample_strava_activity):
        run_log = strava_service.map_activity_to_run_log(
            sample_strava_activity, "user-123"
        )
        assert run_log.date.year == 2026
        assert run_log.date.month == 2
        assert run_log.date.day == 15


class TestSyncActivities:
    @pytest.mark.asyncio
    async def test_sync_creates_run_logs(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        test_db.add(mock_user)
        test_db.commit()

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sample_strava_activity], []]

            result = await strava_service.sync_activities(mock_user, test_db)

        assert result["synced"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == []

        logs = test_db.query(RunLog).filter(RunLog.user_id == "user-123").all()
        assert len(logs) == 1
        assert logs[0].strava_activity_id == "9876543210"

    @pytest.mark.asyncio
    async def test_sync_deduplicates(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        test_db.add(mock_user)
        # Pre-create a run log with the same strava_activity_id
        existing = RunLog(
            user_id="user-123",
            strava_activity_id="9876543210",
            distance_km=10.0,
            duration_minutes=50.0,
            avg_pace_min_km=5.0,
        )
        test_db.add(existing)
        test_db.commit()

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sample_strava_activity], []]

            result = await strava_service.sync_activities(mock_user, test_db)

        assert result["synced"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_sync_filters_non_run_activities(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        test_db.add(mock_user)
        test_db.commit()

        cycling_activity = {**sample_strava_activity, "id": 111, "type": "Ride"}
        swim_activity = {**sample_strava_activity, "id": 222, "type": "Swim"}
        trail_run = {**sample_strava_activity, "id": 333, "type": "TrailRun"}

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [
                [cycling_activity, swim_activity, trail_run, sample_strava_activity],
                [],
            ]

            result = await strava_service.sync_activities(mock_user, test_db)

        # Only trail_run and the sample Run should be synced
        assert result["synced"] == 2
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_sync_sport_type_only_run(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        """Activities with type=None but sport_type='Run' should be synced."""
        test_db.add(mock_user)
        test_db.commit()

        sport_type_run = {
            **sample_strava_activity,
            "id": 444,
            "type": None,
            "sport_type": "Run",
        }
        sport_type_ride = {
            **sample_strava_activity,
            "id": 555,
            "type": None,
            "sport_type": "Ride",
        }

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sport_type_run, sport_type_ride], []]

            result = await strava_service.sync_activities(mock_user, test_db)

        # Only the Run sport_type should be synced, Ride should be skipped
        assert result["synced"] == 1
        assert result["skipped"] == 0

        logs = test_db.query(RunLog).filter(RunLog.user_id == "user-123").all()
        assert len(logs) == 1
        assert logs[0].strava_activity_id == "444"

    @pytest.mark.asyncio
    async def test_sync_sets_inferred_workout_type(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        """A synced run gets an inferred type even without splits (HR + VDOT)."""
        test_db.add(mock_user)
        test_db.commit()

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sample_strava_activity], []]

            await strava_service.sync_activities(mock_user, test_db)

        run = test_db.query(RunLog).filter(RunLog.user_id == "user-123").first()
        assert run.inferred_workout_type in {
            "easy",
            "recovery",
            "long",
            "tempo",
            "interval",
        }
        assert run.inferred_type_confidence is not None

    @pytest.mark.asyncio
    async def test_sync_stores_parsed_splits(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        """When activity detail is available, per-km splits are parsed + stored."""
        test_db.add(mock_user)
        test_db.commit()

        detail = {
            "splits_metric": [
                {"distance": 1000.0, "moving_time": 300, "average_heartrate": 150.0},
                {"distance": 1000.0, "moving_time": 280, "average_heartrate": 160.0},
            ]
        }
        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
            patch.object(
                strava_service,
                "fetch_activity_detail",
                new_callable=AsyncMock,
                return_value=detail,
            ),
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sample_strava_activity], []]

            await strava_service.sync_activities(mock_user, test_db)

        run = test_db.query(RunLog).filter(RunLog.user_id == "user-123").first()
        assert run.splits is not None
        assert len(run.splits) == 2
        assert run.splits[0]["pace_min_km"] == 5.0  # 300s over 1km

    @pytest.mark.asyncio
    async def test_sync_survives_detail_fetch_failure(
        self, strava_service, mock_user, sample_strava_activity, test_db
    ):
        """A failed detail fetch (None) leaves splits empty but still syncs."""
        test_db.add(mock_user)
        test_db.commit()

        with (
            patch.object(
                strava_service, "ensure_valid_token", new_callable=AsyncMock
            ) as mock_token,
            patch.object(
                strava_service, "fetch_activities", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_token.return_value = "valid-token"
            mock_fetch.side_effect = [[sample_strava_activity], []]

            result = await strava_service.sync_activities(mock_user, test_db)

        assert result["synced"] == 1
        run = test_db.query(RunLog).filter(RunLog.user_id == "user-123").first()
        assert run.splits is None


class TestParseStravaSplits:
    def test_parses_splits_metric(self):
        detail = {
            "splits_metric": [
                {"distance": 1000.0, "moving_time": 300, "average_heartrate": 150.0},
                {"distance": 1000.0, "moving_time": 270, "average_heartrate": None},
            ]
        }
        assert parse_strava_splits(detail) == [
            {"km": 1.0, "duration_s": 300, "pace_min_km": 5.0, "avg_hr": 150},
            {"km": 1.0, "duration_s": 270, "pace_min_km": 4.5, "avg_hr": None},
        ]

    def test_no_splits_returns_none(self):
        assert parse_strava_splits({}) is None
        assert parse_strava_splits(None) is None
        assert parse_strava_splits({"splits_metric": []}) is None

    def test_skips_unusable_splits(self):
        detail = {"splits_metric": [{"distance": 0, "moving_time": 10}]}
        assert parse_strava_splits(detail) is None


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_returns_existing_token_if_valid(
        self, strava_service, mock_user, test_db
    ):
        test_db.add(mock_user)
        test_db.commit()

        token = await strava_service.ensure_valid_token(mock_user, test_db)
        assert token == "access-token"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self, strava_service, mock_user, test_db):
        mock_user.strava_token_expires_at = int(time.time()) - 100  # expired
        test_db.add(mock_user)
        test_db.commit()

        with patch.object(
            strava_service, "refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_at": int(time.time()) + 3600,
            }

            token = await strava_service.ensure_valid_token(mock_user, test_db)

        assert token == "new-access-token"
        assert mock_user.strava_access_token == "new-access-token"
        assert mock_user.strava_refresh_token == "new-refresh-token"

    @pytest.mark.asyncio
    async def test_raises_without_refresh_token(self, strava_service, test_db):
        user = User(id="user-no-strava", email="no@strava.com")
        test_db.add(user)
        test_db.commit()

        with pytest.raises(ValueError, match="no Strava refresh token"):
            await strava_service.ensure_valid_token(user, test_db)


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_clears_strava_fields(self, strava_service, mock_user, test_db):
        test_db.add(mock_user)
        test_db.commit()

        await strava_service.disconnect(mock_user, test_db)

        assert mock_user.strava_athlete_id is None
        assert mock_user.strava_access_token is None
        assert mock_user.strava_refresh_token is None
        assert mock_user.strava_token_expires_at is None
