"""Push endpoints, the installed-app launch route, and the check-in prefill."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_optional_user
from app.infrastructure.config import settings
from app.infrastructure.notifications.webpush import generate_vapid_private_key
from app.main import app
from app.models import PushSubscription, TrainingPlan, User

P256DH = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-1"


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="push-owner", email="push-owner@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def signed_in(test_db: Session, owner: User):
    def override_get_db():
        yield test_db

    async def as_owner():
        return owner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = as_owner
    app.dependency_overrides[get_optional_user] = as_owner
    yield owner
    app.dependency_overrides.clear()


@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", generate_vapid_private_key())


def _subscribe(client, endpoint=ENDPOINT, p256dh=P256DH, auth=AUTH):
    return client.post(
        "/api/push/subscribe",
        json={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
    )


def test_config_reports_unconfigured_push(signed_in, monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", "")
    with TestClient(app) as client:
        body = client.get("/api/push/config").json()
    assert body["configured"] is False
    assert body["public_key"] is None


def test_subscribe_stores_the_device_and_reports_it(signed_in, vapid, test_db):
    with TestClient(app) as client:
        config = client.get("/api/push/config").json()
        assert config["configured"] and len(config["public_key"]) > 80
        resp = _subscribe(client)
    assert resp.status_code == 200
    assert resp.json()["devices"] == 1
    stored = test_db.query(PushSubscription).one()
    assert stored.user_id == signed_in.id


def test_resubscribing_a_device_rehomes_it_instead_of_duplicating(
    signed_in, vapid, test_db
):
    other = User(id="someone-else", email="else@example.com")
    test_db.add(other)
    test_db.add(
        PushSubscription(user_id=other.id, endpoint=ENDPOINT, p256dh=P256DH, auth=AUTH)
    )
    test_db.commit()
    with TestClient(app) as client:
        _subscribe(client)
    rows = test_db.query(PushSubscription).all()
    assert len(rows) == 1 and rows[0].user_id == signed_in.id


@pytest.mark.parametrize(
    "endpoint,p256dh,auth",
    [
        ("https://169.254.169.254/latest", P256DH, AUTH),
        (ENDPOINT, "A" * 60, AUTH),
        (ENDPOINT, P256DH, "short-but-10"),
    ],
)
def test_subscribe_rejects_foreign_hosts_and_bad_keys(
    signed_in, vapid, endpoint, p256dh, auth
):
    with TestClient(app) as client:
        assert _subscribe(client, endpoint, p256dh, auth).status_code == 400


def test_unsubscribe_only_removes_your_own_device(signed_in, vapid, test_db):
    other = User(id="other-owner", email="other@example.com")
    test_db.add(other)
    test_db.add(
        PushSubscription(
            user_id=other.id,
            endpoint="https://fcm.googleapis.com/fcm/send/theirs",
            p256dh=P256DH,
            auth=AUTH,
        )
    )
    test_db.commit()
    with TestClient(app) as client:
        client.post(
            "/api/push/unsubscribe",
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/theirs"},
        )
    assert test_db.query(PushSubscription).count() == 1


def test_prefs_are_saved_sparsely(signed_in, vapid, test_db):
    with TestClient(app) as client:
        body = client.patch("/api/push/prefs", json={"morning_brief": False}).json()
    assert body["prefs"]["morning_brief"] is False
    assert body["prefs"]["after_run"] is True
    test_db.refresh(signed_in)
    assert signed_in.notification_prefs == {"morning_brief": False}


def test_today_sends_a_runner_to_the_plan_in_progress(signed_in, test_db):
    test_db.add(
        TrainingPlan(
            id="live-plan",
            user_id=signed_in.id,
            current_weekly_km=30,
            target_distance="10",
            weeks_duration=8,
            start_date=datetime.combine(
                date.today() - timedelta(days=10), datetime.min.time()
            ),
            plan_data=[],
        )
    )
    test_db.commit()
    with TestClient(app) as client:
        resp = client.get("/today", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/plan/live-plan#today-card"


def test_today_without_a_plan_goes_home(signed_in):
    with TestClient(app) as client:
        resp = client.get("/today", follow_redirects=False)
    assert resp.headers["location"] == "/"


def test_service_worker_is_served_from_the_root_uncached():
    with TestClient(app) as client:
        resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")
    assert resp.headers["cache-control"] == "no-cache"
    assert "showNotification" in resp.text


def test_manifest_launches_on_today():
    with TestClient(app) as client:
        manifest = client.get("/manifest.webmanifest").json()
    assert manifest["start_url"] == "/today"


def test_prefill_offers_reconnect_to_a_pre_wellness_connection(signed_in, test_db):
    signed_in.intervals_athlete_id = "i5"
    signed_in.intervals_access_token = "tok"
    signed_in.intervals_scopes = "ACTIVITY:READ,CALENDAR:WRITE"
    test_db.commit()
    with TestClient(app) as client:
        body = client.get("/api/readiness/prefill").json()
    assert body["available"] is False
    assert body["reconnect_for_wellness"] is True
