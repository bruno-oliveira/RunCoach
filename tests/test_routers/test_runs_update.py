"""``PUT /api/runs/{id}`` — the one path that could clear a run's required fields.

Every field on ``RunLogUpdate`` is optional and the router writes whatever was
explicitly sent (``exclude_unset=True``), so an explicit ``null`` used to write
NULL into a column a run cannot do without: the row reported a null distance and
could no longer be placed on the plan calendar. Creating a run was already strict
(``RunLogCreate`` requires a positive distance and duration) and so is the
Intervals importer (it raises on an activity missing distance/duration/start), so
this endpoint was the last gap.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import RunLog, User


@pytest.fixture
def user(test_db: Session) -> User:
    u = User(
        id="run-update-user",
        email="run-update@example.com",
        name="Run Update",
        google_id="google-run-update",
    )
    test_db.add(u)
    test_db.commit()
    return u


@pytest.fixture
def run_log(test_db: Session, user: User) -> RunLog:
    run = RunLog(
        id="run-update-1",
        user_id=user.id,
        date=datetime(2026, 1, 1, 8, 0),
        distance_km=10.0,
        duration_minutes=50.0,
        avg_pace_min_km=5.0,
    )
    test_db.add(run)
    test_db.commit()
    return run


@pytest.fixture
def api(test_db: Session, user: User):
    def override_get_db():
        yield test_db

    async def override_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize("field", ["distance_km", "duration_minutes", "date"])
def test_clearing_a_required_field_is_refused(api, test_db, run_log, field):
    response = api.put(f"/api/runs/{run_log.id}", json={field: None})

    assert response.status_code == 400
    assert field in response.json()["detail"]

    test_db.rollback()
    stored = test_db.get(RunLog, run_log.id)
    assert getattr(stored, field) is not None


def test_omitting_a_field_leaves_it_alone(api, test_db, run_log):
    """A partial update is still a partial update — this is the happy path."""
    response = api.put(f"/api/runs/{run_log.id}", json={"notes": "Felt strong"})

    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "Felt strong"
    assert body["distance_km"] == 10.0
    assert body["duration_minutes"] == 50.0


def test_a_real_update_still_applies_and_repaces(api, run_log):
    response = api.put(
        f"/api/runs/{run_log.id}",
        json={"distance_km": 12.0, "duration_minutes": 60.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["distance_km"] == 12.0
    assert body["duration_minutes"] == 60.0
    assert body["avg_pace_min_km"] == 5.0


def test_clearing_a_field_does_not_touch_the_stored_row(api, test_db, run_log):
    """The refusal happens before any write, so nothing is half-applied."""
    api.put(
        f"/api/runs/{run_log.id}",
        json={"distance_km": None, "notes": "should not stick"},
    )

    test_db.rollback()
    stored = test_db.get(RunLog, run_log.id)
    assert stored.distance_km == 10.0
    assert stored.notes != "should not stick"
