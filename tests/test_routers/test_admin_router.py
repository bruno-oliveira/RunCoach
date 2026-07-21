"""Endpoint tests for the admin console (operator-only)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import TrainingPlan, User

ADMIN_EMAIL = "admin-test@example.com"


def _plan_data() -> list[dict]:
    return [
        {
            "week": 1,
            "daily_workouts": [
                {"day": 1, "type": "rest", "distance": 0},
                {
                    "day": 3,
                    "type": "interval",
                    "key_workout_name": "Cruise Intervals",
                    "distance": 9.0,
                    "steps": [
                        {"kind": "warmup", "distance_m": 2000, "pace_zone": "E"},
                        {
                            "kind": "run",
                            "distance_m": 1000,
                            "pace_zone": "I",
                            "repeat": 4,
                        },
                        {"kind": "recovery", "duration_s": 90, "repeat": 3},
                        {"kind": "cooldown", "distance_m": 1500, "pace_zone": "E"},
                    ],
                },
            ],
        }
    ]


@pytest.fixture
def admin_user(test_db: Session) -> User:
    user = User(id="admin-user", email=ADMIN_EMAIL)
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def normal_user(test_db: Session) -> User:
    user = User(id="admin-normal", email="not-admin@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def admin_plan(test_db: Session, admin_user: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="admin-plan-1",
        user_id=admin_user.id,
        current_weekly_km=32,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        plan_data=_plan_data(),
    )
    test_db.add(tp)
    test_db.commit()
    return tp


@pytest.fixture(autouse=True)
def _set_admin_email():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.settings.admin_email", ADMIN_EMAIL)
        yield


@pytest.fixture
def admin_client(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _set_user(user: User) -> None:
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


def test_console_forbidden_for_non_admin(admin_client, normal_user):
    _set_user(normal_user)
    assert admin_client.get("/admin").status_code == 403


def test_console_renders_for_admin(admin_client, admin_user, admin_plan):
    _set_user(admin_user)
    resp = admin_client.get("/admin")
    assert resp.status_code == 200
    assert "Admin console" in resp.text
    assert admin_plan.id in resp.text  # plan appears in the picker


def test_preview_forbidden_for_non_admin(admin_client, normal_user, admin_plan):
    _set_user(normal_user)
    resp = admin_client.post(
        "/api/admin/intervals/preview",
        json={"plan_id": admin_plan.id, "week": 1, "day": 3},
    )
    assert resp.status_code == 403


def test_preview_returns_workout_text(admin_client, admin_user, admin_plan):
    _set_user(admin_user)
    resp = admin_client.post(
        "/api/admin/intervals/preview",
        json={"plan_id": admin_plan.id, "week": 1, "day": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "4x" in data["description"]
    assert "- 1km Z5 Pace" in data["description"]
    assert data["moving_time"] > 0


def test_preview_rest_day_rejected(admin_client, admin_user, admin_plan):
    _set_user(admin_user)
    resp = admin_client.post(
        "/api/admin/intervals/preview",
        json={"plan_id": admin_plan.id, "week": 1, "day": 1},
    )
    assert resp.status_code == 400
