"""Tests for the request_timezone middleware.

Verifies that the browser timezone (X-Timezone header or rc_tz cookie) is
bound to the request context so server-side ``local_today()`` reflects the
user's wall clock, and that invalid input falls back to UTC.
"""

from datetime import timezone

from fastapi.testclient import TestClient

from app.core.time_utils import request_timezone
from app.main import app as production_app


def _make_client() -> TestClient:
    # Use the real app (with middleware); /health avoids DB dependencies.
    return TestClient(production_app)


def test_header_binds_timezone_during_request(monkeypatch):
    seen = {}

    client = _make_client()

    # Piggyback on the health endpoint: capture the contextvar mid-request
    # by wrapping the route handler via a tiny probe route.
    @production_app.get("/__tz_probe")
    async def _probe():  # pragma: no cover - exercised via TestClient
        tz = request_timezone()
        seen["tz"] = str(tz) if tz != timezone.utc else "UTC"
        return {"tz": seen["tz"]}

    try:
        r = client.get("/__tz_probe", headers={"X-Timezone": "Europe/Amsterdam"})
        assert r.status_code == 200
        assert r.json()["tz"] == "Europe/Amsterdam"

        r = client.get("/__tz_probe", cookies={"rc_tz": "Asia/Tokyo"})
        assert r.status_code == 200
        assert r.json()["tz"] == "Asia/Tokyo"

        # Header wins over cookie.
        r = client.get(
            "/__tz_probe",
            headers={"X-Timezone": "Europe/Lisbon"},
            cookies={"rc_tz": "Asia/Tokyo"},
        )
        assert r.json()["tz"] == "Europe/Lisbon"

        # Garbage falls back to UTC, request still succeeds.
        r = client.get("/__tz_probe", headers={"X-Timezone": "Not/AZone"})
        assert r.status_code == 200
        assert r.json()["tz"] == "UTC"

        # No header/cookie at all -> UTC.
        r = client.get("/__tz_probe")
        assert r.json()["tz"] == "UTC"
    finally:
        production_app.router.routes = [
            rt
            for rt in production_app.router.routes
            if getattr(rt, "path", None) != "/__tz_probe"
        ]


def test_context_resets_after_request():
    client = _make_client()
    client.get("/health", headers={"X-Timezone": "Europe/Amsterdam"})
    # Outside any request the contextvar must be back to its UTC default.
    assert request_timezone() == timezone.utc
