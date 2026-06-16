"""Tests for /api/strava/callback (OAuth callback)."""

import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.dependencies import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def callback_user(test_db: Session) -> User:
    """Create a user that will be found during callback."""
    user = User(
        id="cb-user-1",
        email="callback@example.com",
        name="Callback User",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def callback_client(test_db: Session) -> TestClient:
    """Test client with DB override only (callback doesn't use get_current_user)."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _make_state(user_id: str, nonce: str = "test-nonce") -> str:
    """Create a valid state JWT (with nonce) for the Strava callback."""
    auth = AuthService()
    return auth.create_access_token(
        {"sub": user_id, "purpose": "strava_oauth", "nonce": nonce},
        expires_delta=timedelta(minutes=5),
    )


class TestStravaCallback:
    def test_valid_state_and_code_stores_tokens(
        self, callback_client, callback_user, test_db
    ):
        state = _make_state(callback_user.id, nonce="nonce-abc")

        token_data = {
            "access_token": "strava-access-123",
            "refresh_token": "strava-refresh-456",
            "expires_at": int(time.time()) + 3600,
            "athlete": {"id": 99999},
        }

        callback_client.cookies.set("strava_oauth_state", "nonce-abc")
        with patch(
            "app.infrastructure.integrations.strava_service.StravaService.exchange_code_for_tokens",
            new_callable=AsyncMock,
            return_value=token_data,
        ):
            response = callback_client.get(
                "/api/strava/callback",
                params={"code": "strava-auth-code", "state": state},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "/my-plans" in response.headers["location"]

        test_db.refresh(callback_user)
        assert callback_user.strava_access_token == "strava-access-123"
        assert callback_user.strava_refresh_token == "strava-refresh-456"
        assert callback_user.strava_athlete_id == "99999"

    def test_invalid_state_returns_400(self, callback_client):
        response = callback_client.get(
            "/api/strava/callback",
            params={"code": "some-code", "state": "invalid-jwt-state"},
        )

        assert response.status_code == 400
        assert "Invalid or expired state" in response.json()["detail"]

    def test_missing_nonce_cookie_returns_400(self, callback_client, callback_user):
        """A valid state without the matching single-use cookie is rejected."""
        state = _make_state(callback_user.id, nonce="nonce-abc")
        callback_client.cookies.clear()

        response = callback_client.get(
            "/api/strava/callback",
            params={"code": "some-code", "state": state},
        )

        assert response.status_code == 400
        assert "Invalid or expired state" in response.json()["detail"]

    def test_expired_state_returns_400(self, callback_client, callback_user):
        auth = AuthService()
        expired_state = auth.create_access_token(
            {"sub": callback_user.id, "purpose": "strava_oauth"},
            expires_delta=timedelta(seconds=-1),
        )

        response = callback_client.get(
            "/api/strava/callback",
            params={"code": "some-code", "state": expired_state},
        )

        assert response.status_code == 400

    def test_strava_exchange_failure_returns_502(self, callback_client, callback_user):
        state = _make_state(callback_user.id, nonce="nonce-xyz")
        callback_client.cookies.set("strava_oauth_state", "nonce-xyz")

        with patch(
            "app.infrastructure.integrations.strava_service.StravaService.exchange_code_for_tokens",
            new_callable=AsyncMock,
            side_effect=Exception("Strava API error"),
        ):
            response = callback_client.get(
                "/api/strava/callback",
                params={"code": "bad-code", "state": state},
            )

        assert response.status_code == 502
        assert "Failed to exchange code" in response.json()["detail"]
