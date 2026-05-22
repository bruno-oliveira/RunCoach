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
        # New signups opt into auto-adjust by default (P2 §5.1 default-on).
        assert data["user"]["auto_adjust_enabled"] is True

        # Cookie should be set
        assert "access_token" in response.cookies

        # User should exist in DB
        user = test_db.query(User).filter(User.google_id == "google-123").first()
        assert user is not None
        assert user.email == "test@example.com"
        assert user.auto_adjust_enabled is True

    def test_existing_user_login_preserves_auto_adjust_choice(
        self, auth_client, test_db
    ):
        """Returning users keep their stored preference — the new-user default does not overwrite it."""
        existing = User(
            google_id="google-existing",
            email="existing@example.com",
            name="Existing",
            auto_adjust_enabled=False,
        )
        test_db.add(existing)
        test_db.commit()

        google_data = {
            "sub": "google-existing",
            "email": "existing@example.com",
            "name": "Existing",
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
        assert existing.auto_adjust_enabled is False
        assert response.json()["user"]["auto_adjust_enabled"] is False

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

    def test_toggle_auto_adjust_round_trip(self, auth_client, test_db):
        user = User(
            google_id="settings-user",
            email="settings@example.com",
            name="Settings User",
            auto_adjust_enabled=False,
        )
        test_db.add(user)
        test_db.commit()

        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override
        try:
            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"auto_adjust_enabled": True},
            )
            assert res.status_code == 200
            assert res.json()["auto_adjust_enabled"] is True
            test_db.refresh(user)
            assert user.auto_adjust_enabled is True

            res = auth_client.patch(
                "/api/auth/me/settings",
                json={"auto_adjust_enabled": False},
            )
            assert res.status_code == 200
            assert res.json()["auto_adjust_enabled"] is False
            test_db.refresh(user)
            assert user.auto_adjust_enabled is False
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_settings_requires_auth(self, auth_client):
        res = auth_client.patch(
            "/api/auth/me/settings",
            json={"auto_adjust_enabled": True},
        )
        assert res.status_code == 401
