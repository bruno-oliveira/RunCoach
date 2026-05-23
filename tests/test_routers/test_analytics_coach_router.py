"""Endpoint tests for the analytics Coach hub routes.

Focuses on the HTTP contract — auth, ownership, and response shape. The
rich signal-reshape logic is covered by tests/test_services/
test_coach_summary_service.py with a frozen clock.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import TrainingPlan, User


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="coach-owner", email="owner@example.com", name="Owner")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, owner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="coach-plan-1",
        user_id=owner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        start_date=datetime.utcnow() - timedelta(weeks=2),
        plan_data=[
            {"week": 1, "total_km": 30.0, "phase": "build", "daily_workouts": []}
        ],
        adaptation_history=[
            {"date": "2026-05-10", "type": "adjust", "multiplier": 1.05, "reason": "r"},
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


_PATHS = ("coach-summary", "adaptation-history", "coach-patterns")


@pytest.mark.usefixtures("_override_db")
class TestCoachEndpoints:
    @pytest.mark.parametrize("path", _PATHS)
    def test_requires_auth(self, path, plan):
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/{path}/{plan.id}")
        assert resp.status_code == 401

    @pytest.mark.parametrize("path", _PATHS)
    def test_foreign_plan_forbidden(self, path, plan, test_db):
        other = User(id="coach-other", email="other@example.com")
        test_db.add(other)
        test_db.commit()
        _set_user(other)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/{path}/{plan.id}")
        assert resp.status_code == 403

    @pytest.mark.parametrize("path", _PATHS)
    def test_missing_plan_404(self, path, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/{path}/does-not-exist")
        assert resp.status_code == 404

    def test_coach_summary_shape(self, plan, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/coach-summary/{plan.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "available" in body
        # No runs logged → not enough data, but a well-formed 200 contract.
        assert body["available"] is False
        assert "reason" in body

    def test_adaptation_history_normalized(self, plan, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/adaptation-history/{plan.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["type"] == "adjust"
        assert event["label"] == "Plan adjusted"
        assert event["pct"] == 5

    def test_coach_patterns_shape(self, plan, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/coach-patterns/{plan.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert isinstance(body["patterns"], list)
        assert "week_pulse" in body
