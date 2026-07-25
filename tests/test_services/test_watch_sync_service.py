"""Tests for keeping an already-pushed plan in step with the watch calendar.

The behaviour under test is the one that was missing entirely: when a plan
changes, the days the watch is about to run have to change with it.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from app.application import watch_sync_service
from app.application.watch_sync_service import (
    events_in_forward_window,
    resync_plan_to_watch,
)
from app.models import TrainingPlan, User


class _FakeIntervals:
    """Records what would be pushed instead of calling Intervals.icu."""

    def __init__(self, boom: bool = False):
        self.calls: list[tuple] = []
        self.boom = boom

    async def push_workouts(self, access_token, athlete_id, events):
        if self.boom:
            raise RuntimeError("intervals is down")
        self.calls.append((access_token, athlete_id, events))
        return [{"id": i} for i, _ in enumerate(events)]


def _week(week: int, distance: float = 8.0) -> dict:
    """One plan week: a rest Monday and a real run every other day."""
    workouts = [{"day": 1, "type": "rest", "distance": 0}]
    workouts += [{"day": d, "type": "easy", "distance": distance} for d in range(2, 8)]
    return {"week": week, "daily_workouts": workouts}


@pytest.fixture
def synced_user(test_db) -> User:
    user = User(
        id="watch-user",
        email="watch@example.com",
        intervals_athlete_id="i321",
        intervals_access_token="watch-token",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def pushed_plan(test_db, synced_user) -> TrainingPlan:
    """A plan starting today that the runner has already sent to their watch."""
    plan = TrainingPlan(
        id="watch-plan",
        user_id=synced_user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=4,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=[_week(1), _week(2), _week(3), _week(4)],
        watch_synced_at=datetime.utcnow(),
    )
    test_db.add(plan)
    test_db.commit()
    return plan


@pytest.fixture
def use_test_session(test_db, monkeypatch):
    """Point the service's own-session factory at the test session."""
    monkeypatch.setattr("app.dependencies.SessionLocal", lambda: test_db, raising=False)
    # The service closes its session; the fixture owns this one, so keep it open.
    monkeypatch.setattr(test_db, "close", lambda: None, raising=False)
    return test_db


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------


def test_window_covers_only_the_days_intervals_will_forward(pushed_plan):
    today = date.today()
    events = events_in_forward_window(pushed_plan, today=today, forward_days=8)

    dates = sorted(e["start_date_local"][:10] for e in events)
    assert dates[0] >= today.isoformat()
    assert dates[-1] <= (today + timedelta(days=8)).isoformat()


def test_window_skips_rest_days(pushed_plan):
    events = events_in_forward_window(pushed_plan, today=date.today())
    # Day 1 of each week is a rest day and has nothing to run.
    assert not any(e["external_id"].endswith("-1") for e in events)


def test_window_excludes_days_already_in_the_past(test_db, synced_user):
    plan = TrainingPlan(
        id="watch-plan-past",
        user_id=synced_user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=4,
        start_date=datetime.combine(
            date.today() - timedelta(days=21), datetime.min.time()
        ),
        plan_data=[_week(1), _week(2), _week(3), _week(4)],
        watch_synced_at=datetime.utcnow(),
    )
    test_db.add(plan)
    test_db.commit()

    today = date.today()
    events = events_in_forward_window(plan, today=today)
    assert events, "the plan is mid-flight, so some days must still be ahead"
    assert all(e["start_date_local"][:10] >= today.isoformat() for e in events)


# ---------------------------------------------------------------------------
# Re-sync guards and behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resync_pushes_the_forward_window(
    use_test_session, synced_user, pushed_plan
):
    intervals = _FakeIntervals()
    pushed = await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert pushed > 0
    access_token, athlete_id, events = intervals.calls[0]
    assert access_token == "watch-token"
    assert athlete_id == "i321"
    assert len(events) == pushed


@pytest.mark.asyncio
async def test_resync_skips_plans_never_sent_to_a_watch(
    use_test_session, test_db, synced_user, pushed_plan
):
    # A runner who never used send-to-watch should not find their Intervals
    # calendar quietly filling up because they adjusted a plan.
    pushed_plan.watch_synced_at = None
    test_db.commit()

    intervals = _FakeIntervals()
    assert await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals) == 0
    assert intervals.calls == []


@pytest.mark.asyncio
async def test_resync_skips_disconnected_users(
    use_test_session, test_db, synced_user, pushed_plan
):
    synced_user.intervals_access_token = None
    test_db.commit()

    intervals = _FakeIntervals()
    assert await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals) == 0
    assert intervals.calls == []


@pytest.mark.asyncio
async def test_resync_skips_unknown_plan(use_test_session, synced_user):
    intervals = _FakeIntervals()
    assert await resync_plan_to_watch("no-such-plan", synced_user.id, intervals) == 0


@pytest.mark.asyncio
async def test_resync_swallows_provider_failures(
    use_test_session, synced_user, pushed_plan
):
    # The plan change is already committed and rendered — a stale watch must
    # never surface as a failed adaptation.
    assert (
        await resync_plan_to_watch(
            pushed_plan.id, synced_user.id, _FakeIntervals(boom=True)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_resync_reflects_the_adapted_distance(
    use_test_session, test_db, synced_user, pushed_plan
):
    # Shorten every run in week 1, the way "feeling tired" would, and confirm the
    # re-push carries the new session rather than the original. Rebuilt rather
    # than mutated in place: SQLAlchemy won't flush an in-place edit of a JSON
    # column (which is what app.utils.persist_json exists to work around).
    eased = deepcopy(pushed_plan.plan_data)
    for day in eased[0]["daily_workouts"]:
        if day["distance"]:
            day["distance"] = 3.0
    pushed_plan.plan_data = eased
    test_db.commit()

    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    _, _, events = intervals.calls[0]
    week_one = [
        e for e in events if e["external_id"].startswith("runcoach-watch-plan-1-")
    ]
    assert week_one
    assert all("3km" in e["description"] for e in week_one)


def test_forward_window_default_matches_intervals_horizon():
    # Intervals.icu forwards about the next week; the constant should not drift
    # far from that without a reason.
    assert 7 <= watch_sync_service.FORWARD_WINDOW_DAYS <= 10
