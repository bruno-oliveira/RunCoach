"""Endpoint tests for /api/analytics/coach-note/{plan_id}.

Focuses on the HTTP contract — auth, ownership, the not-enough-data shape, and
that the injected narrator dependency resolves. The AI/rules source split and
fact-pack assembly are covered by tests/test_services/
test_coach_narrative_service.py.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_coach_narrator, get_current_user, get_db
from app.main import app
from app.models import TrainingPlan, User


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="note-owner", email="note-owner@example.com", name="Owner")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, owner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="note-plan-1",
        user_id=owner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        start_date=datetime.utcnow() - timedelta(weeks=2),
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


class _FakeNarrator:
    def __init__(self):
        self.calls = []

    def generate_note(self, context):
        self.calls.append(context)
        return "Fake coach note."


@pytest.mark.usefixtures("_override_db")
class TestCoachNoteEndpoint:
    def test_requires_auth(self, plan):
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/coach-note/{plan.id}")
        assert resp.status_code == 401

    def test_foreign_plan_forbidden(self, plan, test_db):
        other = User(id="note-other", email="no@example.com")
        test_db.add(other)
        test_db.commit()
        _set_user(other)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/coach-note/{plan.id}")
        assert resp.status_code == 403

    def test_missing_plan_404(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get("/api/analytics/coach-note/does-not-exist")
        assert resp.status_code == 404

    def test_insufficient_data_shape(self, plan, owner):
        # No runs → well-formed 200 with available False (gate short-circuits).
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.get(f"/api/analytics/coach-note/{plan.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert "reason" in body

    def test_narrator_dependency_is_injectable(self, plan, owner):
        # Overriding the narrator must resolve cleanly (no 500). With no runs the
        # gate returns before the narrator is reached, so it stays uncalled.
        fake = _FakeNarrator()
        _set_user(owner)
        app.dependency_overrides[get_coach_narrator] = lambda: fake
        try:
            with TestClient(app) as client:
                resp = client.get(f"/api/analytics/coach-note/{plan.id}")
            assert resp.status_code == 200
            assert resp.json()["available"] is False
            assert fake.calls == []
        finally:
            app.dependency_overrides.pop(get_coach_narrator, None)
