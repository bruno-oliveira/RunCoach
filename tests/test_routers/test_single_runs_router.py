"""Endpoint tests for single runs: the API, the page, and data isolation."""

from datetime import datetime, time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contexts.runner.single_runs import claim_completed_single_runs
from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
from app.models import (
    DailyWorkout,
    RunLog,
    SingleRun,
    TrainingPlan,
    User,
    WeeklyPlan,
)

_PUSH_PATH = (
    "app.infrastructure.integrations.intervals_service.IntervalsService.push_workout"
)


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(
        id="srr-owner",
        email="srr-owner@example.com",
        intervals_athlete_id="i7",
        intervals_access_token="token",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def stranger(test_db: Session) -> User:
    user = User(id="srr-stranger", email="srr-stranger@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def api(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _as(user: User | None) -> None:
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_optional_user] = override


def _create(api, **body):
    return api.post("/api/single-runs", json={"run_type": "easy", **body})


def test_create_returns_the_generated_workout(api, owner):
    _as(owner)

    response = _create(api, run_type="tempo", distance_km=8)

    assert response.status_code == 201
    body = response.json()
    assert body["run_type"] == "tempo" and body["name"] == "Tempo Run"
    assert body["distance_km"] == pytest.approx(8.0, abs=0.5)
    assert body["steps"] and body["description"]
    assert body["on_watch"] is False and body["completed_run"] is None
    assert body["date"] == local_today().isoformat()


def test_create_and_send_puts_it_on_the_watch(api, owner):
    _as(owner)
    with patch(_PUSH_PATH, new_callable=AsyncMock, return_value={"id": 9}) as push:
        response = _create(api, distance_km=6, send_to_watch=True)

    assert response.status_code == 201
    assert response.json()["on_watch"] is True
    assert response.json()["watch_error"] is None
    assert push.await_args.args[2]["external_id"].startswith("runcoach-single-")


def test_a_failed_push_still_creates_the_run(api, owner, test_db):
    _as(owner)
    with patch(_PUSH_PATH, new_callable=AsyncMock, side_effect=RuntimeError("down")):
        response = _create(api, distance_km=6, send_to_watch=True)

    assert response.status_code == 201
    assert response.json()["watch_error"] == "provider"
    assert response.json()["on_watch"] is False
    assert test_db.query(SingleRun).count() == 1


def test_send_without_a_connection_says_so(api, stranger):
    _as(stranger)
    single_run_id = _create(api, distance_km=6).json()["id"]

    response = api.post(f"/api/single-runs/{single_run_id}/send-to-watch")

    assert response.status_code == 200
    assert response.json()["watch_error"] == "not_connected"


@pytest.mark.parametrize(
    "body",
    [
        {},  # no size at all
        {"distance_km": 6, "duration_minutes": 40},  # both
        {"run_type": "fartlek", "distance_km": 6},
        {"distance_km": -1},
    ],
)
def test_malformed_requests_are_rejected(api, owner, body):
    _as(owner)
    assert _create(api, **body).status_code == 422


def test_domain_limits_surface_as_a_friendly_400(api, owner):
    _as(owner)

    too_short = _create(api, run_type="interval", distance_km=2)
    by_time_unknown_paces = _create(api, duration_minutes=40)

    assert too_short.status_code == 400
    assert by_time_unknown_paces.status_code == 400
    assert "distance" in by_time_unknown_paces.json()["detail"]


def test_requires_authentication(api):
    assert api.get("/api/single-runs").status_code == 401
    assert _create(api, distance_km=6).status_code == 401


def test_list_shows_only_the_callers_runs_with_completion(
    api, owner, stranger, test_db
):
    _as(stranger)
    _create(api, distance_km=5)
    _as(owner)
    single_run_id = _create(api, distance_km=6).json()["id"]
    today = local_today()
    test_db.add(
        RunLog(
            user_id=owner.id,
            date=datetime.combine(today, time(8)),
            distance_km=6.1,
            duration_minutes=33.0,
            avg_pace_min_km=5.4,
        )
    )
    test_db.commit()
    claim_completed_single_runs(owner.id, test_db, today)
    test_db.commit()

    listed = api.get("/api/single-runs").json()["single_runs"]

    assert [item["id"] for item in listed] == [single_run_id]
    assert listed[0]["completed_run"]["distance_km"] == 6.1


def test_another_runners_single_run_is_a_404(api, owner, stranger, test_db):
    _as(owner)
    single_run_id = _create(api, distance_km=6).json()["id"]

    _as(stranger)
    assert api.delete(f"/api/single-runs/{single_run_id}").status_code == 404
    assert (
        api.post(f"/api/single-runs/{single_run_id}/send-to-watch").status_code == 404
    )
    assert test_db.query(SingleRun).count() == 1


def test_delete_removes_it(api, owner, test_db):
    _as(owner)
    single_run_id = _create(api, distance_km=6).json()["id"]

    assert api.delete(f"/api/single-runs/{single_run_id}").status_code == 204
    assert test_db.query(SingleRun).count() == 0


def test_completed_single_run_shows_up_in_analytics(api, owner, test_db):
    """The point of the feature: a plan-less run still reaches the dashboards."""
    _as(owner)
    _create(api, run_type="tempo", distance_km=8)
    today = local_today()
    test_db.add(
        RunLog(
            user_id=owner.id,
            date=datetime.combine(today, time(8)),
            distance_km=8.0,
            duration_minutes=40.0,
            avg_pace_min_km=5.0,
        )
    )
    test_db.commit()
    claim_completed_single_runs(owner.id, test_db, today)
    test_db.commit()

    response = api.get("/api/analytics/runs")

    assert response.status_code == 200
    runs = response.json()["runs"]
    assert len(runs) == 1
    # Tagged from the single run, so type-bucketed charts file it correctly.
    assert runs[0]["workout_type"] == "tempo"


def test_page_renders_for_a_runner_and_redirects_a_visitor(api, owner):
    _as(owner)
    _create(api, run_type="interval", distance_km=8)

    page = api.get("/run")
    assert page.status_code == 200
    assert "Intervals" in page.text and 'id="singleRunForm"' in page.text

    _as(None)
    assert api.get("/run", follow_redirects=False).status_code == 302


def test_page_hands_the_form_the_planned_runs_it_could_duplicate(api, owner, test_db):
    today = local_today()
    test_db.add_all(
        [
            TrainingPlan(
                id="srr-plan",
                user_id=owner.id,
                start_date=datetime.combine(today, time.min),
                weeks_duration=8,
                target_distance="10",
                current_weekly_km=30,
                plan_data=[],
            ),
            WeeklyPlan(id="srr-week", training_plan_id="srr-plan", week_number=1),
            DailyWorkout(
                id="srr-day",
                weekly_plan_id="srr-week",
                day_of_week=1,
                workout_type="easy",
                distance_km=8.0,
            ),
        ]
    )
    test_db.commit()
    _as(owner)

    page = api.get("/run")

    assert page.status_code == 200
    assert 'id="singleOverlap"' in page.text
    assert "/plan/srr-plan/day/srr-day" in page.text
