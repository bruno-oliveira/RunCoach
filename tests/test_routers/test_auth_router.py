"""Tests for /api/auth endpoints (Google login flow)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def auth_client(test_db: Session) -> TestClient:
    """Test client with DB override (no auth override — testing auth itself)."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestGoogleAuth:
    """Tests for POST /api/auth/google."""

    def test_valid_token_creates_user_and_sets_cookie(self, auth_client, test_db):
        google_data = {
            "sub": "google-123",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        }

        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_data,
        ):
            response = auth_client.post(
                "/api/auth/google",
                json={"id_token": "valid-google-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "authenticated"
        assert "access_token" not in data
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["name"] == "Test User"

        # Cookie should be set
        assert "access_token" in response.cookies

        # User should exist in DB
        user = test_db.query(User).filter(User.google_id == "google-123").first()
        assert user is not None
        assert user.email == "test@example.com"

    def test_invalid_token_returns_401(self, auth_client):
        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = auth_client.post(
                "/api/auth/google",
                json={"id_token": "invalid-token"},
            )

        assert response.status_code == 401
        assert "Invalid Google token" in response.json()["detail"]

    def test_anonymous_user_merge_on_login(self, auth_client, test_db):
        """When an anonymous user logs in with Google, their data should be merged."""
        # Create an anonymous user
        anon_user = User(id="anon-user-1")
        test_db.add(anon_user)
        test_db.commit()

        google_data = {
            "sub": "google-merge-123",
            "email": "merge@example.com",
            "name": "Merge User",
            "picture": None,
        }

        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_data,
        ):
            # Set anonymous_user_id cookie before request
            auth_client.cookies.set("anonymous_user_id", "anon-user-1")
            response = auth_client.post(
                "/api/auth/google",
                json={"id_token": "valid-google-token"},
            )

        assert response.status_code == 200
        # Google user should be created
        user = test_db.query(User).filter(User.google_id == "google-merge-123").first()
        assert user is not None

    def test_verified_email_links_existing_account(self, auth_client, test_db):
        """A verified Google email links to the existing account with that email."""
        existing = User(id="email-owner-1", email="owner@example.com")
        test_db.add(existing)
        test_db.commit()

        google_data = {
            "sub": "google-link-123",
            "email": "owner@example.com",
            "email_verified": True,
            "name": "Owner",
            "picture": None,
        }

        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_data,
        ):
            response = auth_client.post(
                "/api/auth/google",
                json={"id_token": "valid-google-token"},
            )

        assert response.status_code == 200
        test_db.refresh(existing)
        assert existing.google_id == "google-link-123"

    def test_unverified_email_collision_is_rejected(self, auth_client, test_db):
        """An unverified Google email must not take over an existing account."""
        existing = User(id="email-owner-2", email="victim@example.com")
        test_db.add(existing)
        test_db.commit()

        google_data = {
            "sub": "google-attacker-123",
            "email": "victim@example.com",
            "email_verified": False,
            "name": "Attacker",
            "picture": None,
        }

        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_data,
        ):
            response = auth_client.post(
                "/api/auth/google",
                json={"id_token": "valid-google-token"},
            )

        assert response.status_code == 403
        test_db.refresh(existing)
        assert existing.google_id is None
        # No new account was minted for the attacker's identity either.
        attacker = (
            test_db.query(User)
            .filter(User.google_id == "google-attacker-123")
            .first()
        )
        assert attacker is None


class TestGetMe:
    """Tests for GET /api/auth/me."""

    def test_unauthenticated_returns_401(self, auth_client):
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 401


class TestLogout:
    """Tests for POST /api/auth/logout."""

    def test_logout_clears_cookies(self, auth_client):
        response = auth_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"


class TestUserSettings:
    """Tests for PATCH /api/auth/me/settings."""

    def test_update_resting_hr_round_trip(self, auth_client, test_db):
        user = User(
            google_id="settings-user",
            email="settings@example.com",
            name="Settings User",
        )
        test_db.add(user)
        test_db.commit()

        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override
        try:
            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"resting_hr": 52},
            )
            assert res.status_code == 200
            assert res.json()["resting_hr"] == 52
            test_db.refresh(user)
            assert user.resting_hr == 52

            # 0 clears the override back to the data-derived estimate.
            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"resting_hr": 0},
            )
            assert res.status_code == 200
            assert res.json()["resting_hr"] is None
            test_db.refresh(user)
            assert user.resting_hr is None
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_update_threshold_hr_round_trip(self, auth_client, test_db):
        user = User(
            google_id="threshold-user",
            email="threshold@example.com",
            name="Threshold User",
        )
        test_db.add(user)
        test_db.commit()

        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override
        try:
            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"threshold_hr": 172},
            )
            assert res.status_code == 200
            assert res.json()["threshold_hr"] == 172
            test_db.refresh(user)
            assert user.threshold_hr == 172

            # 0 clears the override back to the data-derived estimate.
            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"threshold_hr": 0},
            )
            assert res.status_code == 200
            assert res.json()["threshold_hr"] is None
            test_db.refresh(user)
            assert user.threshold_hr is None
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_settings_requires_auth(self, auth_client):
        res = auth_client.patch(
            "/api/auth/me/settings",
            json={"resting_hr": 55},
        )
        assert res.status_code == 401
