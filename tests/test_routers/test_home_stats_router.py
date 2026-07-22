"""HTTP contract for GET /api/analytics/home-stats."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import RunLog, User


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", name="Runner", max_hr=190)
    test_db.add(user)
    # Two months of easy runs with HR so both series have data.
    for days_ago, pace, hr in (
        (150, 6.0, 150),
        (148, 6.0, 150),
        (10, 5.5, 140),
        (8, 5.5, 140),
    ):
        test_db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                date=_now() - timedelta(days=days_ago),
                distance_km=10.0,
                duration_minutes=55.0,
                avg_pace_min_km=pace,
                avg_heart_rate=hr,
                effort_class="easy_effort",
            )
        )
    test_db.commit()
    return user


@pytest.fixture
def _override_db(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _set_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


@pytest.mark.usefixtures("_override_db")
class TestHomeStatsEndpoint:
    def test_requires_auth(self):
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            assert client.get("/api/analytics/home-stats").status_code == 401

    def test_returns_both_series(self, owner):
        _set_user(owner)
        try:
            with TestClient(app) as client:
                resp = client.get("/api/analytics/home-stats")
            assert resp.status_code == 200
            body = resp.json()
            assert body["pace_evolution"]["has_data"] is True
            assert body["pace_evolution"]["trend"]["direction"] == "faster"
            assert body["hr_zone_evolution"]["has_data"] is True
            assert len(body["hr_zone_evolution"]["series"]) == 5
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_empty_states_are_well_formed_for_new_user(self, test_db):
        fresh = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        test_db.add(fresh)
        test_db.commit()
        _set_user(fresh)
        try:
            with TestClient(app) as client:
                resp = client.get("/api/analytics/home-stats")
            assert resp.status_code == 200
            body = resp.json()
            assert body["pace_evolution"]["has_data"] is False
            assert body["hr_zone_evolution"]["has_data"] is False
            assert "empty_reason" in body["pace_evolution"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)
