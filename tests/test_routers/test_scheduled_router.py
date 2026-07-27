"""Tests for the ambient-sync trigger.

The endpoint imports activities, reshapes plans, and rewrites third-party
calendars with nobody watching, so the gate matters more than the payload: it
must be invisible until deliberately switched on, and closed to anyone without
the secret. The sweep itself is covered in
``tests/test_services/test_ambient_sync_service.py``.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.config import settings
from app.models import User

CRON_SECRET = "test-cron-secret"

_SYNC = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.sync_activities"
)


@pytest.fixture
def cron_enabled(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", CRON_SECRET)
    return CRON_SECRET


@pytest.fixture
def connected(test_db) -> User:
    user = User(
        id="sched-user",
        email="sched@example.com",
        intervals_athlete_id="i700",
        intervals_access_token="token-700",
    )
    test_db.add(user)
    test_db.commit()
    return user


def test_the_trigger_is_invisible_until_a_cron_secret_is_configured(
    client, monkeypatch
):
    """404, not 401 — an unattended write path shouldn't announce itself to
    someone probing for it."""
    monkeypatch.setattr(settings, "cron_secret", "")
    res = client.post("/api/scheduled/sync", headers={"X-Cron-Secret": "anything"})
    assert res.status_code == 404


def test_the_trigger_rejects_a_missing_secret(client, cron_enabled):
    assert client.post("/api/scheduled/sync").status_code == 403


def test_the_trigger_rejects_a_wrong_secret(client, cron_enabled):
    res = client.post("/api/scheduled/sync", headers={"X-Cron-Secret": "nope"})
    assert res.status_code == 403


def test_a_dry_run_reports_candidates_without_calling_the_provider(
    client, cron_enabled, connected
):
    with patch(_SYNC, new_callable=AsyncMock) as sync_mock:
        res = client.post(
            "/api/scheduled/sync?dry_run=true", headers={"X-Cron-Secret": CRON_SECRET}
        )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["dry_run"] is True
    assert body["candidates"] == 1
    sync_mock.assert_not_awaited()


def test_a_real_run_imports_for_every_connected_runner(client, cron_enabled, connected):
    with patch(
        _SYNC, new_callable=AsyncMock, return_value={"synced": 0, "total": 0}
    ) as sync_mock:
        res = client.post("/api/scheduled/sync", headers={"X-Cron-Secret": CRON_SECRET})

    assert res.status_code == 200
    assert res.json()["candidates"] == 1
    sync_mock.assert_awaited_once()


def test_the_sweep_survives_a_provider_that_is_down(client, cron_enabled, connected):
    """A failed import is a counted failure, not a 500 that makes the workflow
    look like a deployment problem."""
    with patch(_SYNC, new_callable=AsyncMock, side_effect=RuntimeError("down")):
        res = client.post("/api/scheduled/sync", headers={"X-Cron-Secret": CRON_SECRET})

    assert res.status_code == 200
    assert res.json()["failed"] == 1
