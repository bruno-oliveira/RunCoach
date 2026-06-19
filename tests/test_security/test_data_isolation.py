"""Cross-user data-isolation and CSRF regression tests.

These lock in the two guarantees the security pass cared about:

* One user can never read or mutate another user's runs or plans (IDOR).
* State-changing requests — including the HTML ``<form>`` routes outside
  ``/api/`` — are rejected when they originate from a foreign origin (CSRF).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import RunLog, TrainingPlan, User


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="iso-owner", email="owner@iso.example", name="Owner")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def attacker(test_db: Session) -> User:
    user = User(id="iso-attacker", email="attacker@iso.example", name="Attacker")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def owner_run(test_db: Session, owner: User) -> RunLog:
    run = RunLog(
        id="iso-run-1",
        user_id=owner.id,
        distance_km=10.0,
        duration_minutes=50.0,
        avg_pace_min_km=5.0,
    )
    test_db.add(run)
    test_db.commit()
    return run


@pytest.fixture
def owner_plan(test_db: Session, owner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="iso-plan-1",
        user_id=owner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        start_date=datetime(2026, 1, 1),
        plan_data=[
            {"week": 1, "total_km": 30.0, "phase": "build", "daily_workouts": []}
        ],
    )
    test_db.add(tp)
    test_db.commit()
    return tp


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
class TestRunIsolation:
    """A user must not reach another user's run logs by guessing the ID."""

    def test_foreign_run_get_is_404(self, owner_run, attacker):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.get(f"/api/runs/{owner_run.id}")
        assert resp.status_code == 404

    def test_foreign_run_update_is_404(self, owner_run, attacker, test_db):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.put(f"/api/runs/{owner_run.id}", json={"distance_km": 999.0})
        assert resp.status_code == 404
        # The owner's run is untouched.
        test_db.refresh(owner_run)
        assert owner_run.distance_km == 10.0

    def test_foreign_run_delete_is_404(self, owner_run, attacker, test_db):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.delete(f"/api/runs/{owner_run.id}")
        assert resp.status_code == 404
        assert test_db.get(RunLog, owner_run.id) is not None

    def test_owner_can_read_own_run(self, owner_run, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/runs/{owner_run.id}")
        assert resp.status_code == 200


@pytest.mark.usefixtures("_override_db")
class TestPlanIsolation:
    """A user must not mutate another user's plan by guessing the ID."""

    def test_foreign_plan_delete_is_403(self, owner_plan, attacker, test_db):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.delete(f"/api/plan/{owner_plan.id}")
        assert resp.status_code == 403
        assert test_db.get(TrainingPlan, owner_plan.id) is not None

    def test_foreign_plan_set_start_date_is_403(self, owner_plan, attacker):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{owner_plan.id}/start",
                json={"start_date": "2026-02-01"},
            )
        assert resp.status_code == 403

    def test_foreign_plan_share_toggle_is_403(self, owner_plan, attacker):
        _set_user(attacker)
        with TestClient(app) as client:
            resp = client.post(f"/api/plan/{owner_plan.id}/share")
        assert resp.status_code == 403


@pytest.mark.usefixtures("_override_db")
class TestCsrfOnFormRoutes:
    """CSRF Origin check must also cover the non-/api HTML form routes."""

    def test_cross_origin_generate_plan_blocked(self):
        with TestClient(app) as client:
            resp = client.post(
                "/generate-plan",
                data={"current_km": "20", "target_distance": "5", "weeks": "8"},
                headers={"Origin": "https://evil.example"},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cross-origin request blocked"

    def test_cross_origin_customize_plan_blocked(self):
        with TestClient(app) as client:
            resp = client.post(
                "/customize-plan",
                data={
                    "plan_id": "whatever",
                    "week_number": "1",
                    "adjustment_type": "mileage",
                    "adjustment_value": "10",
                },
                headers={"Origin": "https://evil.example"},
            )
        assert resp.status_code == 403

    def test_same_origin_generate_plan_not_csrf_blocked(self):
        # Same-origin form posts must still pass the CSRF gate (they may fail
        # later for other reasons, but never with a cross-origin 403).
        with TestClient(app, base_url="http://testserver") as client:
            resp = client.post(
                "/generate-plan",
                data={"current_km": "20", "target_distance": "5", "weeks": "8"},
                headers={"Origin": "http://testserver"},
            )
        assert resp.status_code != 403
