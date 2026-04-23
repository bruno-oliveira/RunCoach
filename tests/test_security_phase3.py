"""Tests for Phase 3 security hardening: headers, request size, cookies, privacy, account deletion, Strava disconnect."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import TrainingPlan
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def security_user(test_db: Session) -> User:
    """Create a minimal authenticated user."""
    user = User(
        id="sec-user-1",
        email="sec@example.com",
        name="Security Test",
        google_id="google-sec-1",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def strava_user(test_db: Session) -> User:
    """Create a user with Strava fields populated."""
    user = User(
        id="strava-sec-1",
        email="strava-sec@example.com",
        name="Strava Security Test",
        google_id="google-strava-sec-1",
        strava_athlete_id="99999",
        strava_access_token="access-tok",
        strava_refresh_token="refresh-tok",
        strava_token_expires_at=int(time.time()) + 3600,
        strava_last_synced_at=int(time.time()),
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


def _clear_user():
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    """Verify security headers are added to every response."""

    def test_health_endpoint_has_security_headers(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
        assert response.headers["X-XSS-Protection"] == "0"

    def test_security_headers_on_html_page(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
        assert response.headers["X-XSS-Protection"] == "0"

    def test_hsts_not_set_in_debug_mode(self, client: TestClient):
        """In debug mode (DEBUG=True in .env), HSTS header must not be present."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers


# ---------------------------------------------------------------------------
# Request Size Limit
# ---------------------------------------------------------------------------


class TestRequestSizeLimit:
    """Verify the request size limit middleware rejects oversized requests."""

    def test_request_within_limit_succeeds(self, client: TestClient):
        """A normal-sized POST should pass the size check (fails auth, not size)."""
        response = client.post(
            "/api/auth/google",
            json={"id_token": "some-token"},
        )
        # 401 means the size check passed; the token is simply invalid
        assert response.status_code == 401

    def test_request_exceeding_limit_returns_413(self, client: TestClient):
        """A request with Content-Length > 1 MB should be rejected with 413."""
        oversized_body = "x" * 100  # small actual body
        response = client.post(
            "/api/auth/google",
            content=oversized_body,
            headers={
                "Content-Length": str(2_000_000),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_get_requests_not_affected(self, client: TestClient):
        """GET requests have no Content-Length and should not be blocked."""
        response = client.get("/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Cookie Secure Flag
# ---------------------------------------------------------------------------


class TestCookieSecureFlag:
    """Verify the _cookie_secure() logic and its effect on cookies."""

    def test_cookie_secure_returns_false_in_debug(self):
        """With debug=True (test default), _cookie_secure() should return False."""
        from app.middleware import _cookie_secure
        # settings.debug is True from .env
        assert _cookie_secure() is False

    def test_cookie_secure_returns_true_when_not_debug(self):
        """With debug=False and force_secure_cookies=True, should return True."""
        from app.middleware import _cookie_secure
        with patch("app.middleware.settings") as mock_settings:
            mock_settings.debug = False
            mock_settings.force_secure_cookies = True
            assert _cookie_secure() is True

    def test_anonymous_cookie_secure_flag_in_debug(self, client: TestClient):
        """In debug mode, the anonymous_user_id cookie should not have secure=True."""
        # Delete any existing anonymous cookie so the middleware generates a new one
        client.cookies.clear()
        response = client.get("/")
        assert response.status_code == 200
        # The Set-Cookie header should NOT contain "Secure" when debug=True
        set_cookie = response.headers.get("set-cookie", "")
        # There may be multiple Set-Cookie headers; find the anonymous one
        assert "anonymous_user_id" in set_cookie
        # In debug mode the cookie should not be marked Secure
        # (httponly yes, but Secure should be absent)
        cookie_parts = set_cookie.lower()
        # "secure" as a standalone attribute should not be present
        # We need to be careful: "httponly" contains no "secure"
        # Split on semicolons and check for a standalone "secure" token
        tokens = [t.strip() for t in cookie_parts.split(";")]
        assert "secure" not in tokens


# ---------------------------------------------------------------------------
# Privacy Page
# ---------------------------------------------------------------------------


class TestPrivacyPage:
    """Verify the /privacy route renders correctly."""

    def test_privacy_page_returns_200(self, client: TestClient):
        response = client.get("/privacy")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_privacy_page_contains_policy_content(self, client: TestClient):
        response = client.get("/privacy")
        assert response.status_code == 200
        body = response.text
        assert "Privacy Policy" in body
        assert "What We Collect" in body
        assert "Your Rights" in body
        assert "Data Retention" in body


# ---------------------------------------------------------------------------
# Account Deletion
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestAccountDeletion:
    """Verify DELETE /api/auth/account removes user and cascades."""

    def test_delete_account_requires_auth(self):
        _clear_user()
        with TestClient(app) as c:
            response = c.delete("/api/auth/account")
        assert response.status_code == 401

    def test_delete_account_removes_user(self, security_user, test_db):
        _set_user(security_user)
        with TestClient(app) as c:
            response = c.delete("/api/auth/account")
        assert response.status_code == 200
        assert response.json()["message"] == "Account deleted"

        # User should be gone from DB
        test_db.expire_all()
        deleted = test_db.query(User).filter(User.id == "sec-user-1").first()
        assert deleted is None

    def test_delete_account_cascades_plans(self, security_user, test_db):
        # Create a training plan linked to the user
        plan = TrainingPlan(
            id="plan-to-cascade",
            user_id=security_user.id,
            current_weekly_km=20.0,
            target_distance="10",
            weeks_duration=8,
        )
        test_db.add(plan)
        test_db.commit()

        _set_user(security_user)
        with TestClient(app) as c:
            response = c.delete("/api/auth/account")
        assert response.status_code == 200

        test_db.expire_all()
        assert test_db.query(User).filter(User.id == security_user.id).first() is None
        assert test_db.query(TrainingPlan).filter(TrainingPlan.id == "plan-to-cascade").first() is None


# ---------------------------------------------------------------------------
# Strava Disconnect
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestStravaDisconnect:
    """Verify POST /api/strava/disconnect clears Strava credentials."""

    def test_disconnect_requires_auth(self):
        _clear_user()
        with TestClient(app) as c:
            response = c.post("/api/strava/disconnect")
        assert response.status_code == 401

    def test_disconnect_clears_strava_fields(self, strava_user, test_db):
        _set_user(strava_user)
        with TestClient(app) as c:
            response = c.post("/api/strava/disconnect")
        assert response.status_code == 200
        assert response.json()["message"] == "Strava disconnected"

        test_db.expire_all()
        refreshed = test_db.query(User).filter(User.id == strava_user.id).first()
        assert refreshed.strava_athlete_id is None
        assert refreshed.strava_access_token is None
        assert refreshed.strava_refresh_token is None
        assert refreshed.strava_token_expires_at is None
        assert refreshed.strava_last_synced_at is None

    def test_disconnect_already_disconnected(self, security_user):
        """A user without Strava connected can still call disconnect successfully."""
        _set_user(security_user)
        with TestClient(app) as c:
            response = c.post("/api/strava/disconnect")
        assert response.status_code == 200
        assert response.json()["message"] == "Strava disconnected"
