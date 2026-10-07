"""Signing in, and staying signed in, from the app installed to a home screen.

An installed app could not sign in at all (Google's popup answers a window the
app never sees), and a session that did exist ended after fifteen minutes
because nothing renewed it. These pin the server half of both fixes, and the
few names the scripts and the server have to agree on.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.main import app
from app.models.user import User
from app.web.middleware import _CSRF_EXEMPT
from app.web.routers.auth import GOOGLE_CSRF_COOKIE

JS_ROOT = Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "js"
LANDING = "/api/auth/google/redirect"
GOOGLE = {"Origin": "https://accounts.google.com"}


@pytest.fixture
def auth_client(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, follow_redirects=False) as client:
        yield client
    app.dependency_overrides.clear()


def _post_from_google(client, *, cookie, form_token, credential="id.token.value"):
    client.cookies.clear()
    if cookie is not None:
        client.cookies.set(GOOGLE_CSRF_COOKIE, cookie)
    return client.post(
        LANDING,
        data={"credential": credential, "g_csrf_token": form_token},
        headers=GOOGLE,
    )


class TestRedirectLanding:
    def test_a_verified_post_from_google_gets_the_relay_page(self, auth_client):
        resp = _post_from_google(auth_client, cookie="abc123", form_token="abc123")

        assert resp.status_code == 200
        assert 'id="auth-relay" data-credential="id.token.value"' in resp.text
        assert "/static/js/auth.js" in resp.text
        assert resp.headers["cache-control"] == "no-store"

    def test_it_opens_no_session_itself(self, auth_client):
        resp = _post_from_google(auth_client, cookie="abc123", form_token="abc123")
        assert "access_token" not in resp.cookies
        assert "refresh_token" not in resp.cookies

    @pytest.mark.parametrize(
        ("cookie", "form_token"),
        [("abc123", "other"), (None, "abc123"), ("abc123", ""), ("", "")],
    )
    def test_a_post_that_fails_the_double_submit_check_carries_no_credential(
        self, auth_client, cookie, form_token
    ):
        resp = _post_from_google(auth_client, cookie=cookie, form_token=form_token)

        assert resp.status_code == 400
        assert "data-credential" not in resp.text
        assert "id.token.value" not in resp.text
        # An installed app has no back button: the way home is on the page.
        assert re.search(r'<a href="/" data-relay-back>', resp.text)

    def test_a_missing_credential_is_rejected(self, auth_client):
        resp = _post_from_google(
            auth_client, cookie="abc123", form_token="abc123", credential=""
        )
        assert resp.status_code == 400

    def test_the_credential_cannot_break_out_of_its_attribute(self, auth_client):
        hostile = '"><script>alert(1)</script>'
        resp = _post_from_google(
            auth_client, cookie="abc123", form_token="abc123", credential=hostile
        )
        assert "<script>alert(1)</script>" not in resp.text

    def test_reopening_the_landing_url_goes_home(self, auth_client):
        resp = auth_client.get(LANDING)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"


class TestRefreshBringsARunnerBack:
    def _sign_in(self, client) -> None:
        google_data = {
            "sub": "google-installed-1",
            "email": "installed@example.com",
            "name": "Installed Runner",
            "email_verified": True,
        }
        with patch(
            "app.contexts.auth.auth_service.AuthService.verify_google_token",
            new_callable=AsyncMock,
            return_value=google_data,
        ):
            assert (
                client.post("/api/auth/google", json={"id_token": "t"}).status_code
                == 200
            )

    def test_refresh_after_days_away_yields_a_session_that_works(
        self, auth_client, test_db
    ):
        self._sign_in(auth_client)
        user = test_db.query(User).filter(User.google_id == "google-installed-1").one()
        user.last_activity = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(days=3)
        test_db.commit()
        assert auth_client.get("/api/auth/me").status_code == 401

        assert auth_client.post("/api/auth/refresh").status_code == 200

        assert auth_client.get("/api/auth/me").status_code == 200


class TestScriptsAndServerAgree:
    """Names shared across files that nothing else would catch drifting."""

    def _js(self, name: str) -> str:
        return (JS_ROOT / name).read_text()

    def test_the_login_uri_is_the_exempt_landing_route(self):
        assert f"REDIRECT_LOGIN_PATH = '{LANDING}'" in self._js("auth.js")
        assert LANDING in _CSRF_EXEMPT

    def test_installed_apps_sign_in_by_redirect(self):
        auth = self._js("auth.js")
        assert "options.ux_mode = 'redirect'" in auth
        assert "/api/auth/refresh" in auth

    def test_sign_in_affordances_never_rely_on_one_tap(self):
        # One Tap stays hidden after a dismissal and under Safari's tracking
        # protection; a phone browser then had no way to sign in at all.
        nav, auth = self._js("nav.js"), self._js("auth.js")
        assert "RunCoachAuth.openSignInSheet()" in nav
        assert "openSignInSheet: openSignInSheet" in auth
        for source in (nav, auth):
            assert "accounts.id.prompt(" not in source

    def test_worker_and_page_share_the_snapshot_stamp(self):
        stamp = "'data-rc-snapshot'"
        assert f"SNAPSHOT_ATTR = {stamp}" in self._js("sw.js")
        assert f"SNAPSHOT_ATTR = {stamp}" in self._js("pwa.js")

    def test_the_page_can_find_the_workers_page_cache(self):
        (cache,) = re.findall(r"PAGE_CACHE = '([^']+)'", self._js("sw.js"))
        (prefix,) = re.findall(r"PAGE_CACHE_PREFIX = '([^']+)'", self._js("pwa.js"))
        assert cache.startswith(prefix)
