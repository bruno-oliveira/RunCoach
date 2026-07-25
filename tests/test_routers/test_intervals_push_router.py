"""Endpoint tests for the send-to-watch push endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import TrainingPlan, User

_PUSH_PATH = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.push_workout"
)
_PUSH_MANY_PATH = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.push_workouts"
)


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
                            "pace_str": "4:00/km",
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
def owner(test_db: Session) -> User:
    user = User(
        id="push-owner",
        email="push-owner@example.com",
        intervals_athlete_id="i789",
        intervals_access_token="push-token",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plain_user(test_db: Session) -> User:
    user = User(id="push-plain", email="push-plain@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, owner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="push-plan-1",
        user_id=owner.id,
        current_weekly_km=32,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        plan_data=_plan_data(),
    )
    test_db.add(tp)
    test_db.commit()
    return tp


@pytest.fixture
def push_client(test_db: Session):
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


def test_push_success_sends_structured_event(push_client, owner, plan):
    _set_user(owner)
    with patch(_PUSH_PATH, new_callable=AsyncMock, return_value={"id": 555}) as mock:
        response = push_client.post(
            "/api/intervals/push-workout",
            json={"plan_id": plan.id, "week": 1, "day": 3},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_id"] == 555

    # push_workout(access_token, athlete_id, event) — no self (AsyncMock on class).
    access_token, athlete_id, event = mock.await_args.args
    assert access_token == "push-token"
    assert athlete_id == "i789"
    assert event["category"] == "WORKOUT"
    assert event["type"] == "Run"
    assert event["external_id"] == "runcoach-push-plan-1-1-3"
    assert "4x" in event["description"]
    assert "- 1km 4:00/km Pace" in event["description"]


def test_push_requires_connection(push_client, plain_user, plan):
    # A connected plan exists, but the caller has no Intervals.icu link.
    _set_user(plain_user)
    response = push_client.post(
        "/api/intervals/push-workout",
        json={"plan_id": plan.id, "week": 1, "day": 3},
    )
    assert response.status_code == 400


def test_push_rest_day_rejected(push_client, owner, plan):
    _set_user(owner)
    with patch(_PUSH_PATH, new_callable=AsyncMock) as mock:
        response = push_client.post(
            "/api/intervals/push-workout",
            json={"plan_id": plan.id, "week": 1, "day": 1},
        )
    assert response.status_code == 400
    mock.assert_not_called()


def test_push_unknown_week_is_404(push_client, owner, plan):
    _set_user(owner)
    response = push_client.post(
        "/api/intervals/push-workout",
        json={"plan_id": plan.id, "week": 99, "day": 3},
    )
    assert response.status_code == 404


def test_push_unknown_day_is_404(push_client, owner, plan):
    _set_user(owner)
    response = push_client.post(
        "/api/intervals/push-workout",
        json={"plan_id": plan.id, "week": 1, "day": 5},
    )
    assert response.status_code == 404


def test_push_marks_plan_as_on_the_watch(push_client, test_db, owner, plan):
    # watch_synced_at is what later authorises an automatic re-push after an
    # adaptation, so a successful send has to set it.
    _set_user(owner)
    assert plan.watch_synced_at is None
    with patch(_PUSH_PATH, new_callable=AsyncMock, return_value={"id": 1}):
        push_client.post(
            "/api/intervals/push-workout",
            json={"plan_id": plan.id, "week": 1, "day": 3},
        )
    test_db.refresh(plan)
    assert plan.watch_synced_at is not None


def test_push_week_sends_every_sendable_day_in_one_call(push_client, owner, plan):
    _set_user(owner)
    with patch(
        _PUSH_MANY_PATH, new_callable=AsyncMock, return_value=[{"id": 1}]
    ) as mock:
        response = push_client.post(
            "/api/intervals/push-week",
            json={"plan_id": plan.id, "week": 1},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["sent"] == 1
    # The rest day is skipped rather than failing the batch.
    assert body["skipped"] == 1

    mock.assert_awaited_once()
    _, _, events = mock.await_args.args
    assert [e["external_id"] for e in events] == ["runcoach-push-plan-1-1-3"]


def test_push_week_all_rest_sends_nothing(push_client, test_db, owner):
    rest_only = TrainingPlan(
        id="push-plan-rest",
        user_id=owner.id,
        current_weekly_km=10,
        target_distance="10",
        weeks_duration=4,
        plan_data=[
            {"week": 1, "daily_workouts": [{"day": 1, "type": "rest", "distance": 0}]}
        ],
    )
    test_db.add(rest_only)
    test_db.commit()

    _set_user(owner)
    with patch(_PUSH_MANY_PATH, new_callable=AsyncMock) as mock:
        response = push_client.post(
            "/api/intervals/push-week",
            json={"plan_id": rest_only.id, "week": 1},
        )

    assert response.status_code == 200
    assert response.json()["sent"] == 0
    mock.assert_not_called()


def test_push_week_requires_connection(push_client, plain_user, plan):
    _set_user(plain_user)
    response = push_client.post(
        "/api/intervals/push-week",
        json={"plan_id": plan.id, "week": 1},
    )
    assert response.status_code == 400


def test_push_week_unknown_week_is_404(push_client, owner, plan):
    _set_user(owner)
    response = push_client.post(
        "/api/intervals/push-week",
        json={"plan_id": plan.id, "week": 99},
    )
    assert response.status_code == 404


def test_push_other_users_plan_forbidden(push_client, test_db, plan):
    other = User(
        id="push-other",
        email="push-other@example.com",
        intervals_athlete_id="i000",
        intervals_access_token="other-token",
    )
    test_db.add(other)
    test_db.commit()
    _set_user(other)
    response = push_client.post(
        "/api/intervals/push-workout",
        json={"plan_id": plan.id, "week": 1, "day": 3},
    )
    assert response.status_code == 403
