"""A run marked as a race re-paces the plan — boldly, but within bounds."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.contexts.plan.adaptation import backtest as bt
from app.contexts.plan.adaptation.vdot_recalibrator import recalibrate_zones_only
from app.dependencies import get_current_user, get_db
from app.infrastructure.integrations.post_sync_service import recalibrate_from_race
from app.main import app
from app.models import RunLog


@pytest.fixture
def live_plan(test_db):
    user, plan = bt._make_plan(
        test_db,
        current_km=35.0,
        target_distance=21.1,
        weeks=12,
        vdot=45.0,
        with_hr_zones=False,
    )
    plan.start_date = datetime.combine(
        datetime.now().date() - timedelta(weeks=3), datetime.min.time()
    )
    test_db.commit()
    return user, plan


def test_a_race_moves_the_plan_but_never_more_than_one_step(test_db, live_plan):
    user, plan = live_plan
    result = recalibrate_zones_only(plan, user.id, test_db, race_vdot=60.0)
    assert result is not None
    assert result["source"] == "race"
    assert plan.vdot == 49.0


def test_a_race_close_to_current_fitness_changes_nothing(test_db, live_plan):
    user, plan = live_plan
    assert recalibrate_zones_only(plan, user.id, test_db, race_vdot=45.5) is None
    assert plan.vdot == 45.0


def test_an_implausible_race_vdot_is_ignored(test_db, live_plan):
    user, plan = live_plan
    assert recalibrate_zones_only(plan, user.id, test_db, race_vdot=140.0) is None


def test_race_recalibration_is_recorded_like_any_other_change(test_db, live_plan):
    user, plan = live_plan
    recalibrate_from_race(plan, user.id, test_db, race_vdot=42.0)
    assert plan.last_change_plan["reason"].startswith("Race result in")
    assert plan.adaptation_history[-1]["source"] == "race"


def test_endpoint_tags_recalibrates_and_can_untag(test_db, live_plan):
    user, plan = live_plan
    run = RunLog(
        user_id=user.id,
        training_plan_id=plan.id,
        date=datetime.now() - timedelta(days=1),
        distance_km=10.0,
        duration_minutes=40.0,
    )
    test_db.add(run)
    test_db.commit()

    def override_db():
        yield test_db

    async def as_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = as_user
    try:
        with TestClient(app) as client:
            marked = client.post(f"/api/runs/{run.id}/race", json={"is_race": True})
            assert marked.status_code == 200
            body = marked.json()
            assert body["is_race"] is True and body["run_vdot"] > 50
            assert body["recalibration"]["new_vdot"] == 49.0

            unmarked = client.post(f"/api/runs/{run.id}/race", json={"is_race": False})
            assert unmarked.json()["is_race"] is False
    finally:
        app.dependency_overrides.clear()
    test_db.refresh(run)
    assert run.workout_type is None
