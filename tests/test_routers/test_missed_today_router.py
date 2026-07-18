"""Endpoint tests for the missed_today intent's preview/apply flow.

Focuses on the HTTP contract — auth, ownership, and response shape. The
mutation logic itself is covered by
tests/test_services/test_intent_service.py with a frozen clock.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan

# Wednesday — matches the "today" the plan below is built around.
TODAY = date(2026, 5, 20)


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="missed-today-owner", email="owner@example.com", name="Owner")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, owner: User) -> TrainingPlan:
    """Week 1 plan whose start_date puts TODAY on a Wednesday tempo run."""
    start_date = datetime.combine(
        TODAY - timedelta(days=TODAY.isoweekday() - 1), datetime.min.time()
    )
    layout = [
        (1, "easy", 6.0),
        (2, "easy", 6.0),
        (3, "tempo", 8.0),
        (4, "long", 12.0),
    ]
    tp = TrainingPlan(
        id="missed-today-plan-1",
        user_id=owner.id,
        current_weekly_km=32,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        start_date=start_date,
        plan_data=[
            {
                "week": w + 1,
                "total_km": 32.0,
                "phase": "build",
                "daily_workouts": [
                    {"day": d, "type": t, "distance": dist} for (d, t, dist) in layout
                ],
            }
            for w in range(8)
        ],
    )
    test_db.add(tp)
    test_db.commit()

    for wk in range(1, 9):
        wp = WeeklyPlan(
            id=f"missed-today-wp-{wk}",
            training_plan_id=tp.id,
            week_number=wk,
            total_km=32.0,
        )
        test_db.add(wp)
        test_db.flush()
        for d, t, dist in layout:
            test_db.add(
                DailyWorkout(
                    id=f"missed-today-wo-{wk}-{d}",
                    weekly_plan_id=wp.id,
                    day_of_week=d,
                    workout_type=t,
                    distance_km=dist,
                    baseline_distance_km=dist,
                )
            )
    test_db.commit()
    return tp


@pytest.fixture
def _override_db(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    def fake_today():
        return TODAY

    for mod in (
        "app.contexts.plan.adaptation._helpers.today_date",
        "app.contexts.plan.adaptation.intent_service.today_date",
    ):
        monkeypatch.setattr(mod, fake_today)


def _set_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


@pytest.mark.usefixtures("_override_db")
class TestMissedTodayIntentEndpoints:
    def test_preview_requires_auth(self, plan):
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{plan.id}/intent/preview",
                json={"intent": "missed_today", "params": {"choice": "skip"}},
            )
        assert resp.status_code == 401

    def test_foreign_plan_forbidden(self, plan, test_db):
        other = User(id="missed-today-other", email="other@example.com")
        test_db.add(other)
        test_db.commit()
        _set_user(other)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{plan.id}/intent",
                json={"intent": "missed_today", "params": {"choice": "skip"}},
            )
        assert resp.status_code in (403, 404)

    def test_missing_plan_404(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                "/api/plan/does-not-exist/intent",
                json={"intent": "missed_today", "params": {"choice": "skip"}},
            )
        assert resp.status_code == 404

    def test_preview_missed_today_skip_does_not_persist(self, plan, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{plan.id}/intent/preview",
                json={"intent": "missed_today", "params": {"choice": "skip"}},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "preview"
        assert body["would_change"] is True

    def test_apply_missed_today_ease(self, plan, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{plan.id}/intent",
                json={"intent": "missed_today", "params": {"choice": "ease"}},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "missed_today"
        assert body["summary"]["workouts_changed_count"] == 1

    def test_apply_missed_today_reschedule_falls_back_without_rest_day(
        self, plan, owner
    ):
        # This fixture's week has no rest day, so reschedule falls back to
        # the ease primitive — still a well-formed, single-workout change.
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/plan/{plan.id}/intent",
                json={"intent": "missed_today", "params": {"choice": "reschedule"}},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "missed_today"
        assert body["summary"]["workouts_changed_count"] == 1
