"""Endpoint tests for Strava router."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.infrastructure.integrations.strava_service import (
    StravaApplicationInactiveError,
)
from app.main import app
from app.models.user import User


@pytest.fixture
def strava_user(test_db: Session) -> User:
    """Create a user with Strava connected."""
    user = User(
        id="strava-user-1",
        email="strava@example.com",
        name="Strava Runner",
        strava_athlete_id="12345",
        strava_access_token="access-token",
        strava_refresh_token="refresh-token",
        strava_token_expires_at=int(time.time()) + 3600,
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plain_user(test_db: Session) -> User:
    """Create a user without Strava connected."""
    user = User(
        id="plain-user-1",
        email="plain@example.com",
        name="Plain Runner",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def _override_db(test_db: Session):
    """Override the DB dependency and clean up after the test."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _set_user(user: User):
    """Set the current user override."""

    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


@pytest.mark.usefixtures("_override_db")
class TestStravaConnect:
    def test_returns_authorize_url(self, plain_user):
        _set_user(plain_user)
        with TestClient(app) as client:
            response = client.get("/api/strava/connect")
        assert response.status_code == 200
        data = response.json()
        assert "authorize_url" in data
        assert "https://www.strava.com/oauth/authorize" in data["authorize_url"]

    def test_requires_auth(self):
        # No user override — should fail auth
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            response = client.get("/api/strava/connect")
        assert response.status_code == 401


@pytest.mark.usefixtures("_override_db")
class TestStravaStatus:
    def test_connected_user(self, strava_user):
        _set_user(strava_user)
        with TestClient(app) as client:
            response = client.get("/api/strava/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["athlete_id"] == "12345"

    def test_disconnected_user(self, plain_user):
        _set_user(plain_user)
        with TestClient(app) as client:
            response = client.get("/api/strava/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["athlete_id"] is None


@pytest.mark.usefixtures("_override_db")
class TestStravaSync:
    def test_sync_requires_strava_connection(self, plain_user):
        _set_user(plain_user)
        with TestClient(app) as client:
            response = client.post("/api/strava/sync")
        assert response.status_code == 400
        assert "not connected" in response.json()["detail"].lower()

    def test_sync_connected_user(self, strava_user):
        _set_user(strava_user)
        with patch(
            "app.infrastructure.integrations.strava_service.StravaService.sync_activities",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = {
                "synced": 5,
                "skipped": 2,
                "errors": [],
                "total": 7,
            }
            with TestClient(app) as client:
                response = client.post("/api/strava/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] == 5
        assert data["skipped"] == 2

    def test_sync_reports_inactive_strava_application(self, strava_user):
        _set_user(strava_user)
        with patch(
            "app.infrastructure.integrations.strava_service.StravaService.sync_activities",
            new_callable=AsyncMock,
            side_effect=StravaApplicationInactiveError,
        ):
            with TestClient(app) as client:
                response = client.post("/api/strava/sync")

        assert response.status_code == 503
        assert "Strava API access is inactive" in response.json()["detail"]
