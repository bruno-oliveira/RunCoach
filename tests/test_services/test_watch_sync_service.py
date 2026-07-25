"""Tests for keeping an already-pushed plan in step with the watch calendar.

Two behaviours are under test. The first is the one that was missing entirely:
when a plan changes, the days the watch is about to run have to change with it.
The second is the one that makes the first one safe — the reconciler deletes
events, and the calendar it deletes from belongs to the runner, not to us.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from app.application.watch_sync_service import resync_plan_to_watch
from app.core.training import watch_mirror
from app.core.training.watch_mirror import event_hash, events_in_window, owns_event
from app.models import TrainingPlan, User


class _FakeIntervals:
    """A stand-in Intervals.icu calendar that records every mutation.

    Behaves like the real thing in the ways the reconciler depends on: events
    persist between calls, ``fetch_events`` honours the date range, and a push
    leaves the created events on the calendar so the next reconcile sees them.
    """

    def __init__(self, boom: bool = False, auth_boom: bool = False):
        self.events: list[dict] = []
        self.pushes: list[list[dict]] = []
        self.deleted_ids: list = []
        self.boom = boom
        self.auth_boom = auth_boom
        self._next_id = 1

    def seed(self, external_id, start_date_local: str) -> dict:
        """Put an event on the calendar without going through a push."""
        event = {
            "id": self._next_id,
            "external_id": external_id,
            "start_date_local": start_date_local,
        }
        self._next_id += 1
        self.events.append(event)
        return event

    @property
    def external_ids(self) -> set:
        return {e["external_id"] for e in self.events}

    async def fetch_events(self, access_token, athlete_id, oldest, newest):
        return [
            e for e in self.events if oldest <= e["start_date_local"][:10] <= newest
        ]

    async def delete_events(self, access_token, athlete_id, event_ids):
        ids = set(event_ids)
        self.deleted_ids.extend(event_ids)
        self.events = [e for e in self.events if e["id"] not in ids]
        return len(ids)

    async def push_workouts(self, access_token, athlete_id, events, pre_delete=True):
        if self.boom:
            raise RuntimeError("intervals is down")
        if self.auth_boom:
            from app.infrastructure.integrations.intervals_service import (
                IntervalsAuthorizationError,
            )

            raise IntervalsAuthorizationError("token revoked")
        self.pushes.append(events)
        return [self.seed(e["external_id"], e["start_date_local"]) for e in events]


def _week(week: int, distance: float = 8.0, days=range(2, 8)) -> dict:
    """One plan week: a rest Monday and a real run on each of ``days``."""
    workouts = [{"day": 1, "type": "rest", "distance": 0}]
    workouts += [{"day": d, "type": "easy", "distance": distance} for d in days]
    return {"week": week, "daily_workouts": sorted(workouts, key=lambda w: w["day"])}


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
    """A plan starting today that the runner keeps mirrored to their watch."""
    plan = TrainingPlan(
        id="watch-plan",
        user_id=synced_user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=4,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=[_week(1), _week(2), _week(3), _week(4)],
        watch_synced_at=datetime.utcnow(),
        watch_sync_enabled=True,
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


def _set_plan_data(plan, db, mutate) -> None:
    """Rebuild ``plan_data`` through ``mutate`` and commit.

    Rebuilt rather than mutated in place: SQLAlchemy won't flush an in-place
    edit of a JSON column (which is what app.utils.persist_json works around).
    """
    data = deepcopy(plan.plan_data)
    mutate(data)
    plan.plan_data = data
    db.commit()


# ---------------------------------------------------------------------------
# Ownership — the guard every delete depends on
# ---------------------------------------------------------------------------


def test_owns_event_matches_only_this_plans_events():
    assert owns_event("plan-a", "runcoach-plan-a-1-2")
    assert not owns_event("plan-a", "runcoach-plan-b-1-2")
    # A prefix that merely starts the same must not match: the trailing hyphen
    # is what stops plan "abc" from claiming plan "abcdef"'s events.
    assert not owns_event("abc", "runcoach-abcdef-1-2")
    assert not owns_event("plan-a", "some-other-app-1-2")
    assert not owns_event("plan-a", None)
    assert not owns_event("plan-a", 12345)


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------


def test_window_reaches_further_than_intervals_forwards(pushed_plan):
    # Intervals only sends ~7 days to the device, so a longer window costs
    # nothing on the wrist and covers a runner who opens the app fortnightly.
    assert watch_mirror.WINDOW_DAYS >= 14


def test_window_covers_today_to_the_horizon(pushed_plan):
    today = date.today()
    events = events_in_window(pushed_plan, today=today)

    dates = sorted(e["start_date_local"][:10] for e in events)
    assert dates[0] >= today.isoformat()
    assert dates[-1] <= (today + timedelta(days=watch_mirror.WINDOW_DAYS)).isoformat()


def test_window_skips_rest_days(pushed_plan):
    events = events_in_window(pushed_plan, today=date.today())
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
        watch_sync_enabled=True,
    )
    test_db.add(plan)
    test_db.commit()

    today = date.today()
    events = events_in_window(plan, today=today)
    assert events, "the plan is mid-flight, so some days must still be ahead"
    assert all(e["start_date_local"][:10] >= today.isoformat() for e in events)


def test_event_hash_tracks_the_body_not_the_id():
    base = {
        "external_id": "runcoach-p-1-2",
        "name": "Easy",
        "description": "- 8km 5:30/km Pace",
        "moving_time": 2640,
        "start_date_local": "2026-08-01T00:00:00",
    }
    assert event_hash(base) == event_hash(dict(base))
    assert event_hash(base) != event_hash({**base, "description": "- 5km"})
    assert event_hash(base) != event_hash(
        {**base, "start_date_local": "2026-08-02T00:00:00"}
    )
    # The id is the key we store the hash under, so it must not feed the hash.
    assert event_hash(base) == event_hash({**base, "external_id": "runcoach-p-9-9"})


# ---------------------------------------------------------------------------
# The hazard: the calendar belongs to the runner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_never_deletes_events_it_does_not_own(
    use_test_session, test_db, synced_user, pushed_plan
):
    """A stranger's training week must survive a reconcile untouched.

    The runner's Intervals calendar holds their own workouts, their coach's, and
    events from every other app they've connected. "Delete everything in the
    window that isn't in the plan" would wipe all of it.
    """
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    intervals = _FakeIntervals()
    foreign = [
        intervals.seed("someone-elses-app-42", f"{tomorrow}T00:00:00"),
        intervals.seed("runcoach-a-different-plan-1-2", f"{tomorrow}T00:00:00"),
        intervals.seed(None, f"{tomorrow}T00:00:00"),  # a hand-made event
    ]

    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    surviving = {e["id"] for e in intervals.events}
    for event in foreign:
        assert event["id"] in surviving, f"{event['external_id']} was deleted"
    assert intervals.deleted_ids == []


@pytest.mark.asyncio
async def test_reconcile_leaves_foreign_events_alone_even_when_pruning_ours(
    use_test_session, test_db, synced_user, pushed_plan
):
    # Same guard, but on the path that *does* delete: a foreign event sitting on
    # the same date as one of our ghosts must not be swept up with it.
    tomorrow = date.today() + timedelta(days=1)
    stamp = f"{tomorrow.isoformat()}T00:00:00"
    intervals = _FakeIntervals()
    foreign = intervals.seed("someone-elses-app-42", stamp)
    # A ghost of ours: an event for a day that no longer exists in the plan.
    ghost = intervals.seed(f"runcoach-{pushed_plan.id}-99-3", stamp)

    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    surviving = {e["id"] for e in intervals.events}
    assert foreign["id"] in surviving
    assert ghost["id"] not in surviving


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_pushes_the_window_on_a_cold_calendar(
    use_test_session, synced_user, pushed_plan
):
    intervals = _FakeIntervals()
    result = await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert result > 0
    pushed = intervals.pushes[0]
    assert len(pushed) == result
    assert all(
        e["external_id"].startswith(f"runcoach-{pushed_plan.id}-") for e in pushed
    )


@pytest.mark.asyncio
async def test_reconcile_of_an_unchanged_plan_issues_no_writes(
    use_test_session, synced_user, pushed_plan
):
    """The idempotence guarantee: API volume tracks real change, not page loads."""
    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)
    assert intervals.pushes, "first reconcile should populate the calendar"

    intervals.pushes.clear()
    intervals.deleted_ids.clear()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert intervals.pushes == []
    assert intervals.deleted_ids == []


@pytest.mark.asyncio
async def test_turning_a_day_into_rest_removes_its_event(
    use_test_session, test_db, synced_user, pushed_plan
):
    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)
    doomed = f"runcoach-{pushed_plan.id}-1-3"
    assert doomed in intervals.external_ids

    def make_rest(data):
        for day in data[0]["daily_workouts"]:
            if day["day"] == 3:
                day["type"] = "rest"
                day["distance"] = 0

    _set_plan_data(pushed_plan, test_db, make_rest)
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert doomed not in intervals.external_ids


@pytest.mark.asyncio
async def test_moving_a_workout_leaves_exactly_one_event(
    use_test_session, test_db, synced_user, pushed_plan
):
    # A week with a Thursday (day 4) run and no Saturday (day 6) one, so the
    # move is unambiguous.
    _set_plan_data(
        pushed_plan,
        test_db,
        lambda data: data.__setitem__(0, _week(1, days=[2, 4])),
    )
    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    thursday = f"runcoach-{pushed_plan.id}-1-4"
    saturday = f"runcoach-{pushed_plan.id}-1-6"
    assert thursday in intervals.external_ids
    assert saturday not in intervals.external_ids

    # Move it: Thursday becomes rest, Saturday picks up the session.
    _set_plan_data(
        pushed_plan,
        test_db,
        lambda data: data.__setitem__(0, _week(1, days=[2, 6])),
    )
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert thursday not in intervals.external_ids
    assert saturday in intervals.external_ids
    assert len([e for e in intervals.events if e["external_id"] == saturday]) == 1


@pytest.mark.asyncio
async def test_a_changed_session_is_deleted_before_it_is_recreated(
    use_test_session, test_db, synced_user, pushed_plan
):
    # Intervals only re-triggers the watch export on create, never on an
    # in-place update — so a shortened session must round-trip delete+create or
    # the watch keeps beeping out the original.
    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)
    original = next(
        e
        for e in intervals.events
        if e["external_id"] == f"runcoach-{pushed_plan.id}-1-3"
    )

    def shorten(data):
        for day in data[0]["daily_workouts"]:
            if day["day"] == 3:
                day["distance"] = 3.0

    _set_plan_data(pushed_plan, test_db, shorten)
    intervals.pushes.clear()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert original["id"] in intervals.deleted_ids
    recreated = [
        e
        for e in intervals.events
        if e["external_id"] == f"runcoach-{pushed_plan.id}-1-3"
    ]
    assert len(recreated) == 1
    assert recreated[0]["id"] != original["id"]
    assert any("3km" in e["description"] for b in intervals.pushes for e in b)


@pytest.mark.asyncio
async def test_reconcile_recreates_an_event_the_runner_deleted_in_intervals(
    use_test_session, synced_user, pushed_plan
):
    # "Keep my watch in sync" means the plan is the source of truth: a session
    # that vanished from the calendar comes back, hash match notwithstanding.
    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)
    target = f"runcoach-{pushed_plan.id}-1-3"
    victim = next(e for e in intervals.events if e["external_id"] == target)
    intervals.events = [e for e in intervals.events if e["id"] != victim["id"]]

    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    assert target in intervals.external_ids


# ---------------------------------------------------------------------------
# Guards and failure handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_skips_plans_with_sync_disabled(
    use_test_session, test_db, synced_user, pushed_plan
):
    # A runner who never opted in should not find their calendar filling up.
    pushed_plan.watch_sync_enabled = False
    test_db.commit()

    intervals = _FakeIntervals()
    assert await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals) == 0
    assert intervals.pushes == []
    assert intervals.deleted_ids == []


@pytest.mark.asyncio
async def test_reconcile_skips_disconnected_users(
    use_test_session, test_db, synced_user, pushed_plan
):
    synced_user.intervals_access_token = None
    test_db.commit()

    intervals = _FakeIntervals()
    assert await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals) == 0
    assert intervals.pushes == []


@pytest.mark.asyncio
async def test_reconcile_skips_unknown_plan(use_test_session, synced_user):
    intervals = _FakeIntervals()
    assert await resync_plan_to_watch("no-such-plan", synced_user.id, intervals) == 0


@pytest.mark.asyncio
async def test_reconcile_swallows_provider_failures(
    use_test_session, test_db, synced_user, pushed_plan
):
    # The plan change is already committed and rendered — a stale watch must
    # never surface as a failed adaptation.
    assert (
        await resync_plan_to_watch(
            pushed_plan.id, synced_user.id, _FakeIntervals(boom=True)
        )
        == 0
    )
    test_db.refresh(pushed_plan)
    assert pushed_plan.watch_sync_error == "provider"


@pytest.mark.asyncio
async def test_a_revoked_token_is_recorded_as_an_auth_failure(
    use_test_session, test_db, synced_user, pushed_plan
):
    # So the plan page can say "reconnect" instead of leaving a 401 in the log.
    await resync_plan_to_watch(
        pushed_plan.id, synced_user.id, _FakeIntervals(auth_boom=True)
    )
    test_db.refresh(pushed_plan)
    assert pushed_plan.watch_sync_error == "auth"


@pytest.mark.asyncio
async def test_a_successful_reconcile_clears_a_previous_failure(
    use_test_session, test_db, synced_user, pushed_plan
):
    pushed_plan.watch_sync_error = "auth"
    test_db.commit()

    await resync_plan_to_watch(pushed_plan.id, synced_user.id, _FakeIntervals())

    test_db.refresh(pushed_plan)
    assert pushed_plan.watch_sync_error is None


@pytest.mark.asyncio
async def test_reconcile_reflects_the_adapted_distance(
    use_test_session, test_db, synced_user, pushed_plan
):
    # Shorten every run in week 1, the way "feeling tired" would, and confirm
    # the re-push carries the new session rather than the original.
    def ease(data):
        for day in data[0]["daily_workouts"]:
            if day["distance"]:
                day["distance"] = 3.0

    _set_plan_data(pushed_plan, test_db, ease)

    intervals = _FakeIntervals()
    await resync_plan_to_watch(pushed_plan.id, synced_user.id, intervals)

    week_one = [
        e
        for batch in intervals.pushes
        for e in batch
        if e["external_id"].startswith(f"runcoach-{pushed_plan.id}-1-")
    ]
    assert week_one
    assert all("3km" in e["description"] for e in week_one)
