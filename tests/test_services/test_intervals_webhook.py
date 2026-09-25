"""Live import: the Intervals.icu webhook, verified and handed to the background."""

import pytest
from fastapi.testclient import TestClient

from app.application import intervals_webhook_service as webhook
from app.application.intervals_webhook_service import (
    WebhookRejected,
    parse_webhook,
)
from app.infrastructure.config import settings
from app.main import app

SECRET = "hook-secret"


def _payload(*events, secret=SECRET):
    return {"secret": secret, "events": list(events)}


def test_verified_payload_yields_distinct_athletes():
    batch = parse_webhook(
        _payload(
            {"athlete_id": "i1", "type": "ACTIVITY_UPLOADED"},
            {"athlete_id": "i1", "type": "ACTIVITY_ANALYZED"},
            {"athlete_id": "i2", "type": "ACTIVITY_UPLOADED"},
            {"athlete_id": "i3", "type": "CALENDAR_UPDATED"},
            {"type": "ACTIVITY_UPLOADED"},
        ),
        SECRET,
    )
    assert batch.athlete_ids == ["i1", "i2"]
    assert batch.ignored_events == 2


@pytest.mark.parametrize(
    "payload",
    [
        _payload(secret="wrong"),
        {"events": []},
        [],
        {"secret": SECRET},
        {"secret": 123, "events": []},
    ],
)
def test_bad_payloads_are_rejected(payload):
    with pytest.raises(WebhookRejected):
        parse_webhook(payload, SECRET)


def test_blank_configured_secret_never_verifies():
    with pytest.raises(WebhookRejected):
        parse_webhook({"secret": "", "events": []}, "")


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings, "intervals_webhook_secret", SECRET)


def test_endpoint_is_invisible_until_configured(monkeypatch):
    monkeypatch.setattr(settings, "intervals_webhook_secret", "")
    with TestClient(app) as client:
        resp = client.post("/api/intervals/webhook", json=_payload())
    assert resp.status_code == 404


def test_endpoint_rejects_a_wrong_secret(secret):
    with TestClient(app) as client:
        resp = client.post("/api/intervals/webhook", json=_payload(secret="nope"))
    assert resp.status_code == 403


def test_endpoint_answers_at_once_and_syncs_in_the_background(secret, monkeypatch):
    calls: list[str] = []

    async def fake_process(athlete_id, intervals_service, **kwargs):
        calls.append(athlete_id)

    monkeypatch.setattr("app.web.routers.intervals.process_athlete", fake_process)
    with TestClient(app) as client:
        resp = client.post(
            "/api/intervals/webhook",
            json=_payload({"athlete_id": "i9", "type": "ACTIVITY_UPLOADED"}),
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "accepted": 1}
    assert calls == ["i9"]


@pytest.mark.asyncio
async def test_unknown_athlete_is_a_quiet_no_op(test_db, monkeypatch):
    monkeypatch.setattr("app.dependencies.SessionLocal", lambda: test_db, raising=False)
    # Keep the test session open after the service's finally-close.
    monkeypatch.setattr(test_db, "close", lambda: None)
    assert await webhook.process_athlete("nobody", intervals_service=None) is None


@pytest.mark.asyncio
async def test_known_athlete_is_synced_committed_and_announced(test_db, monkeypatch):
    from app.application.ambient_sync_service import RunnerSync
    from app.models import User

    test_db.add(
        User(
            id="wh-user",
            email="wh@example.com",
            intervals_athlete_id="i42",
            intervals_access_token="tok",
        )
    )
    test_db.commit()
    monkeypatch.setattr("app.dependencies.SessionLocal", lambda: test_db)
    monkeypatch.setattr(test_db, "close", lambda: None)

    async def fake_sync(self, user):
        return RunnerSync(
            imported=1, adjustments=[{"plan_id": "p1", "auto_adjusted": True}]
        )

    mirrored: list[str] = []

    async def fake_resync(plan_id, user_id, svc):
        mirrored.append(plan_id)
        return 1

    announced: list[int] = []

    class FakeNotifier:
        def after_sync(self, user, result):
            announced.append(result.imported)

    monkeypatch.setattr(
        "app.application.ambient_sync_service.AmbientSyncService.sync_runner",
        fake_sync,
    )
    monkeypatch.setattr(webhook, "resync_plan_to_watch", fake_resync)
    monkeypatch.setattr(webhook, "get_push_notifier", lambda db: FakeNotifier())

    result = await webhook.process_athlete("i42", intervals_service=object())
    assert result is not None and result.imported == 1
    assert mirrored == ["p1"]
    assert announced == [1]
