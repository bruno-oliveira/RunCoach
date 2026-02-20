"""Endpoint tests for Strava router."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
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


def _make_client(test_db: Session, user: User) -> TestClient:
    """Create a test client with auth and db overrides."""

    async def override_get_current_user():
        return user

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app)


class TestStravaConnect:
    def test_returns_authorize_url(self, test_db, plain_user):
        client = _make_client(test_db, plain_user)
        response = client.get("/api/strava/connect")
        assert response.status_code == 200
        data = response.json()
        assert "authorize_url" in data
        assert "https://www.strava.com/oauth/authorize" in data["authorize_url"]

    def test_requires_auth(self, test_db):
        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield test_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        response = client.get("/api/strava/connect")
        assert response.status_code == 401


class TestStravaStatus:
    def test_connected_user(self, test_db, strava_user):
        client = _make_client(test_db, strava_user)
        response = client.get("/api/strava/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["athlete_id"] == "12345"

    def test_disconnected_user(self, test_db, plain_user):
        client = _make_client(test_db, plain_user)
        response = client.get("/api/strava/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["athlete_id"] is None


class TestStravaSync:
    def test_sync_requires_strava_connection(self, test_db, plain_user):
        client = _make_client(test_db, plain_user)
        response = client.post("/api/strava/sync")
        assert response.status_code == 400
        assert "not connected" in response.json()["detail"].lower()

    def test_sync_connected_user(self, test_db, strava_user):
        client = _make_client(test_db, strava_user)

        with patch(
            "app.services.strava_service.StravaService.sync_activities",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = {"synced": 5, "skipped": 2, "errors": []}
            response = client.post("/api/strava/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] == 5
        assert data["skipped"] == 2


class TestStravaDisconnect:
    def test_disconnect_clears_fields(self, test_db, strava_user):
        client = _make_client(test_db, strava_user)
        response = client.post("/api/strava/disconnect")
        assert response.status_code == 200

        test_db.refresh(strava_user)
        assert strava_user.strava_athlete_id is None
        assert strava_user.strava_access_token is None
        assert strava_user.strava_refresh_token is None
        assert strava_user.strava_token_expires_at is None
