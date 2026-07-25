"""Endpoint tests for the watch-mirror subscription, status and setup gate.

These cover the promises the plan page makes to the runner: that the count it
shows was read back from Intervals.icu rather than counted from button presses,
that a dead token says "reconnect" instead of vanishing into the log, and that
turning the mirror off doesn't quietly clear their upcoming week.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
)
from app.main import app
from app.models import TrainingPlan, User

_FETCH = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.fetch_events"
)
_PUSH_MANY = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.push_workouts"
)
_DELETE = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.delete_events"
)


def _plan_data() -> list[dict]:
    return [
        {
            "week": 1,
            "daily_workouts": [
                {"day": 1, "type": "rest", "distance": 0},
                {"day": 2, "type": "easy", "distance": 8.0},
                {"day": 4, "type": "easy", "distance": 6.0},
            ],
        }
    ]


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(
        id="mirror-owner",
        email="mirror-owner@example.com",
        intervals_athlete_id="i555",
        intervals_access_token="mirror-token",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, owner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="mirror-plan",
        user_id=owner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=4,
        vdot=45.0,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=_plan_data(),
    )
    test_db.add(tp)
    test_db.commit()
    return tp


@pytest.fixture
def own_session(test_db: Session, monkeypatch):
    """Point the reconciler's own-session factory at the test session.

    ``resync_plan_to_watch`` deliberately opens its own session — it normally
    runs as a background task after the request that triggered it has finished —
    so overriding ``get_db`` alone leaves it reading a different database.
    """
    monkeypatch.setattr("app.dependencies.SessionLocal", lambda: test_db, raising=False)
    monkeypatch.setattr(test_db, "close", lambda: None, raising=False)
    return test_db


@pytest.fixture
def client(test_db: Session, owner: User):
    def override_get_db():
        yield test_db

    async def override_user():
        return owner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Turning the mirror on and off
# ---------------------------------------------------------------------------


def test_turning_sync_on_enables_it(client, test_db, plan):
    with (
        patch(_FETCH, new_callable=AsyncMock, return_value=[]),
        patch(_PUSH_MANY, new_callable=AsyncMock, return_value=[]),
    ):
        response = client.post(
            "/api/intervals/watch-sync",
            json={"plan_id": plan.id, "enabled": True},
        )

    assert response.status_code == 200
    assert response.json()["sync_enabled"] is True
    test_db.refresh(plan)
    assert plan.watch_sync_enabled is True


def test_turning_sync_off_leaves_the_calendar_alone(client, test_db, plan):
    plan.watch_sync_enabled = True
    test_db.commit()

    with patch(_DELETE, new_callable=AsyncMock) as delete_mock:
        response = client.post(
            "/api/intervals/watch-sync",
            json={"plan_id": plan.id, "enabled": False},
        )

    assert response.status_code == 200
    test_db.refresh(plan)
    assert plan.watch_sync_enabled is False
    # "Stop syncing" must not mean "wipe the week I already have on my watch".
    delete_mock.assert_not_called()


def test_enabling_sync_requires_a_connection(client, test_db, plan, owner):
    owner.intervals_access_token = None
    owner.intervals_athlete_id = None
    test_db.commit()

    response = client.post(
        "/api/intervals/watch-sync",
        json={"plan_id": plan.id, "enabled": True},
    )
    assert response.status_code == 400


def test_sync_toggle_rejects_another_users_plan(client, test_db, plan):
    stranger = User(
        id="mirror-stranger",
        email="mirror-stranger@example.com",
        intervals_athlete_id="i666",
        intervals_access_token="stranger-token",
    )
    test_db.add(stranger)
    test_db.commit()

    async def override():
        return stranger

    app.dependency_overrides[get_current_user] = override
    response = client.post(
        "/api/intervals/watch-sync",
        json={"plan_id": plan.id, "enabled": True},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Status read-back
# ---------------------------------------------------------------------------


def test_status_counts_only_our_events_on_the_calendar(client, test_db, plan):
    plan.watch_sync_enabled = True
    test_db.commit()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    remote = [
        {
            "id": 1,
            "external_id": f"runcoach-{plan.id}-1-2",
            "start_date_local": tomorrow,
        },
        {
            "id": 2,
            "external_id": f"runcoach-{plan.id}-1-4",
            "start_date_local": tomorrow,
        },
        # The runner's own event and another app's must not inflate the count.
        {"id": 3, "external_id": "someone-elses-app-9", "start_date_local": tomorrow},
        {"id": 4, "external_id": None, "start_date_local": tomorrow},
    ]

    with patch(_FETCH, new_callable=AsyncMock, return_value=remote):
        response = client.get(f"/api/intervals/watch-status?plan_id={plan.id}")

    assert response.status_code == 200
    assert response.json()["events_on_calendar"] == 2


def test_status_reports_no_count_when_the_read_back_fails(client, test_db, plan):
    plan.watch_sync_enabled = True
    test_db.commit()

    with patch(_FETCH, new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        response = client.get(f"/api/intervals/watch-status?plan_id={plan.id}")

    body = response.json()
    # None, not zero: "couldn't check" and "nothing there" are different claims.
    assert body["events_on_calendar"] is None


def test_status_surfaces_a_revoked_token_as_an_auth_error(client, test_db, plan):
    plan.watch_sync_enabled = True
    test_db.commit()

    with patch(
        _FETCH,
        new_callable=AsyncMock,
        side_effect=IntervalsAuthorizationError("revoked"),
    ):
        response = client.get(f"/api/intervals/watch-status?plan_id={plan.id}")

    assert response.status_code == 200
    assert response.json()["error"] == "auth"
    test_db.refresh(plan)
    # Persisted, so the page still says "reconnect" after a reload.
    assert plan.watch_sync_error == "auth"


def test_status_does_not_call_intervals_when_sync_is_off(client, plan):
    with patch(_FETCH, new_callable=AsyncMock) as fetch_mock:
        response = client.get(f"/api/intervals/watch-status?plan_id={plan.id}")

    assert response.status_code == 200
    assert response.json()["sync_enabled"] is False
    fetch_mock.assert_not_called()


def test_status_counts_sessions_behind_from_stored_hashes(client, test_db, plan):
    plan.watch_sync_enabled = True
    plan.watch_event_hashes = {}
    test_db.commit()

    with patch(_FETCH, new_callable=AsyncMock, return_value=[]):
        response = client.get(f"/api/intervals/watch-status?plan_id={plan.id}")

    # Two sendable days in the window, neither of them mirrored yet.
    assert response.json()["sessions_behind"] == 2


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


def test_resync_retries_and_reports_success(client, test_db, plan, own_session):
    plan.watch_sync_enabled = True
    test_db.commit()

    with (
        patch(_FETCH, new_callable=AsyncMock, return_value=[]),
        patch(_PUSH_MANY, new_callable=AsyncMock, return_value=[]),
    ):
        response = client.post("/api/intervals/watch-resync", json={"plan_id": plan.id})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["written"] == 2
    assert body["sessions_behind"] == 0


def test_resync_refuses_when_sync_is_off(client, plan):
    response = client.post("/api/intervals/watch-resync", json={"plan_id": plan.id})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Setup gate
# ---------------------------------------------------------------------------


def test_confirming_setup_records_it_on_the_user(client, test_db, owner):
    assert owner.watch_setup_confirmed_at is None
    response = client.post("/api/intervals/watch-setup-confirm")

    assert response.status_code == 200
    assert response.json()["confirmed"] is True
    test_db.refresh(owner)
    assert owner.watch_setup_confirmed_at is not None
