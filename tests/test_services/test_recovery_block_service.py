"""When the recovery block is offered, and what starting it persists.

The offer is narrow on purpose — only after a finished race plan, only while
the race is recent, never once the runner has moved on to another plan, never
twice — so these pin each of those gates, plus the start endpoint and the plan
page that surfaces it.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contexts.plan.plan_lifecycle_service import delete_plan
from app.contexts.plan.plan_type_registry import display_label
from app.contexts.plan.recovery_block_service import (
    block_start_date,
    recovery_offer,
    start_recovery_block,
)
from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
from app.exceptions import ConflictException
from app.main import app
from app.models import TrainingPlan, User, WeeklyPlan

TODAY = date(2026, 9, 30)  # a Wednesday


def _week(number: int, total_km: float) -> dict:
    return {
        "week": number,
        "total_km": total_km,
        "daily_workouts": [
            {"day": 3, "type": "easy", "distance": total_km / 2},
            {"day": 6, "type": "long", "distance": total_km / 2},
        ],
    }


def _race_plan(
    plan_id="race-1",
    *,
    ended_days_ago=2,
    today=TODAY,
    weeks=2,
    distance="42.2",
    **kwargs,
) -> TrainingPlan:
    start = today - timedelta(days=ended_days_ago) - timedelta(weeks=weeks)
    defaults = dict(
        id=plan_id,
        user_id="runner-1",
        current_weekly_km=40,
        target_distance=distance,
        weeks_duration=weeks,
        max_runs_per_week=4,
        vdot=45.0,
        start_date=datetime.combine(start, datetime.min.time()),
        plan_data=[_week(1, 60.0), _week(2, 30.0)],
    )
    defaults.update(kwargs)
    return TrainingPlan(**defaults)


# -- The offer --------------------------------------------------------------


def test_a_finished_marathon_offers_a_five_week_block():
    plan = _race_plan()

    offer = recovery_offer(plan, [plan], TODAY)

    assert offer is not None
    assert offer.weeks == 5
    assert offer.race_name == "Marathon"
    assert offer.first_week_km == 21  # 35% of the 60 km peak
    assert offer.last_week_km == 42  # 70% of it
    assert offer.easy_days == 26


def test_no_offer_while_the_plan_is_still_running():
    plan = _race_plan(ended_days_ago=-3)
    assert recovery_offer(plan, [plan], TODAY) is None


def test_no_offer_once_the_race_is_long_past():
    plan = _race_plan(ended_days_ago=60)
    assert recovery_offer(plan, [plan], TODAY) is None


def test_no_offer_when_another_plan_is_on_the_go():
    plan = _race_plan()
    next_race = _race_plan("race-2", ended_days_ago=-60, weeks=10)
    assert recovery_offer(plan, [plan, next_race], TODAY) is None


def test_no_offer_for_a_plan_without_a_race():
    plan = _race_plan(distance=None)
    assert recovery_offer(plan, [plan], TODAY) is None


def test_no_offer_after_a_recovery_block():
    plan = _race_plan(plan_type="recovery")
    assert recovery_offer(plan, [plan], TODAY) is None


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 28), date(2026, 9, 28)),  # Monday → today
        (date(2026, 9, 30), date(2026, 9, 28)),  # Wednesday → this Monday
        (date(2026, 10, 1), date(2026, 10, 5)),  # Thursday → next Monday
    ],
)
def test_block_starts_on_a_monday_with_every_session_still_ahead(today, expected):
    assert block_start_date(date(2026, 9, 28), today) == expected


def test_block_never_starts_before_the_race_plan_ended():
    # Plan ended on a Tuesday (non-Monday start) after this week's Monday.
    assert block_start_date(date(2026, 9, 29), date(2026, 9, 30)) == date(2026, 10, 5)


# -- Starting it ------------------------------------------------------------


@pytest.fixture
def runner(test_db: Session) -> User:
    user = User(id="runner-1", email="runner@example.com")
    test_db.add(user)
    test_db.commit()
    return user


def test_starting_persists_a_linked_block(test_db, runner):
    plan = _race_plan(watch_sync_enabled=True)
    test_db.add(plan)
    test_db.commit()

    block = start_recovery_block(plan, [plan], test_db, TODAY)

    assert block.plan_type == "recovery"
    assert block.follows_plan_id == plan.id
    assert block.weeks_duration == 5
    assert block.start_date == datetime(2026, 9, 28)
    assert block.watch_sync_enabled is True
    assert display_label(block) == "Recovery"
    weeks = test_db.query(WeeklyPlan).filter_by(training_plan_id=block.id).all()
    assert len(weeks) == 5
    assert all(len(w.daily_workouts) == 7 for w in weeks)


def test_starting_twice_returns_the_same_block(test_db, runner):
    plan = _race_plan()
    test_db.add(plan)
    test_db.commit()

    first = start_recovery_block(plan, [plan], test_db, TODAY)
    second = start_recovery_block(plan, [plan, first], test_db, TODAY)

    assert second.id == first.id
    assert test_db.query(TrainingPlan).filter_by(plan_type="recovery").count() == 1


def test_starting_without_an_offer_is_a_conflict(test_db, runner):
    plan = _race_plan(ended_days_ago=-3)
    test_db.add(plan)
    test_db.commit()

    with pytest.raises(ConflictException):
        start_recovery_block(plan, [plan], test_db, TODAY)


def test_deleting_the_race_plan_leaves_the_block_standing(test_db, runner):
    plan = _race_plan()
    test_db.add(plan)
    test_db.commit()
    block = start_recovery_block(plan, [plan], test_db, TODAY)

    delete_plan(plan, test_db)

    test_db.refresh(block)
    assert block.follows_plan_id is None


# -- Endpoint and page ------------------------------------------------------


@pytest.fixture
def signed_in(test_db: Session, runner: User):
    def override_get_db():
        yield test_db

    async def override_user():
        return runner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_optional_user] = override_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _finished_plan(test_db) -> TrainingPlan:
    plan = _race_plan(today=local_today())
    test_db.add(plan)
    test_db.commit()
    return plan


def test_plan_page_offers_the_block_and_the_endpoint_starts_it(test_db, signed_in):
    plan = _finished_plan(test_db)

    page = signed_in.get(f"/plan/{plan.id}")
    assert page.status_code == 200
    assert "Your recovery block is ready" in page.text

    resp = signed_in.post(f"/api/plan/{plan.id}/recovery-block", json={})
    assert resp.status_code == 200
    block_id = resp.json()["plan_id"]

    # The finished plan now links to the block instead of offering another.
    page = signed_in.get(f"/plan/{plan.id}")
    assert "Your recovery block is ready" not in page.text
    assert f"/plan/{block_id}" in page.text

    # And the block renders as a plan of its own.
    block_page = signed_in.get(f"/plan/{block_id}")
    assert block_page.status_code == 200
    assert "Easy running only while your race settles" in block_page.text


def test_home_hero_points_at_the_offer(test_db, signed_in):
    plan = _finished_plan(test_db)

    home = signed_in.get("/")

    assert home.status_code == 200
    assert f"/plan/{plan.id}#recovery-offer" in home.text


def test_endpoint_refuses_a_plan_still_running(test_db, signed_in):
    plan = _race_plan(today=local_today(), ended_days_ago=-3)
    test_db.add(plan)
    test_db.commit()

    resp = signed_in.post(f"/api/plan/{plan.id}/recovery-block", json={})

    assert resp.status_code == 409


def test_endpoint_refuses_someone_elses_plan(test_db, signed_in):
    other = User(id="someone-else", email="else@example.com")
    test_db.add(other)
    plan = _race_plan(today=local_today(), user_id=other.id)
    test_db.add(plan)
    test_db.commit()

    resp = signed_in.post(f"/api/plan/{plan.id}/recovery-block", json={})

    assert resp.status_code in (403, 404)
    assert test_db.query(TrainingPlan).filter_by(plan_type="recovery").count() == 0


# -- Downstream: the engine and the watch treat it like any plan -------------


def test_block_mirrors_to_the_watch_as_easy_structured_runs(test_db, runner):
    from app.core.training.watch_mirror import events_in_window

    plan = _race_plan()
    test_db.add(plan)
    test_db.commit()
    block = start_recovery_block(plan, [plan], test_db, TODAY)

    events = events_in_window(block, today=date(2026, 9, 28))

    assert events, "the first week's runs should reach the watch"
    assert all(e["category"] == "WORKOUT" for e in events)


def test_logged_runs_adapt_the_block_without_error(test_db, runner):
    from app.contexts.plan.adaptation import AdaptationService
    from app.infrastructure.integrations.post_sync_service import auto_map_and_adjust
    from app.models import RunLog

    today = local_today()
    plan = _race_plan(today=today)
    test_db.add(plan)
    test_db.commit()
    block = start_recovery_block(plan, [plan], test_db, today)
    block_start = block.start_date
    test_db.add(
        RunLog(
            user_id=runner.id,
            date=block_start + timedelta(days=2),
            distance_km=9.0,
            duration_minutes=55,
            avg_pace_min_km=6.1,
            workout_type="easy",
        )
    )
    test_db.commit()

    results = auto_map_and_adjust(runner, test_db, AdaptationService())

    # The finished race plan is left alone; only the block is adapted.
    assert [r["plan_id"] for r in results] == [block.id]
