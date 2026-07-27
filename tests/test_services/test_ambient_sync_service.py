"""Tests for the sweep that runs when nobody is looking.

This is the app's only unattended write path: it imports activities, lets the
adaptive engine reshape plans, and rewrites calendars on a third-party service
— all with no human watching the result. So what's under test is mostly
containment: one broken runner must not cost the others their sync, an expired
token must be survivable rather than fatal, and a dry run must genuinely touch
nothing.
"""

from datetime import date, datetime, timedelta

import pytest

from app.application import ambient_sync_service as ambient_module
from app.application.ambient_sync_service import AmbientSyncService
from app.infrastructure.config import settings
from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
)
from app.models import RunLog, TrainingPlan, User
from app.utils import TimestampAdapter


class _FakeSync:
    """A provider whose sync_activities records its calls."""

    def __init__(self, synced: int = 0, raises: Exception | None = None):
        self.synced = synced
        self.raises = raises
        self.calls: list[tuple[str, int]] = []

    async def sync_activities(self, user, db, after_timestamp: int):
        self.calls.append((user.id, after_timestamp))
        if self.raises is not None:
            raise self.raises
        return {"synced": self.synced, "total": self.synced}


def _week(week: int) -> dict:
    workouts = [{"day": 1, "type": "rest", "distance": 0}]
    workouts += [{"day": d, "type": "easy", "distance": 8.0} for d in range(2, 8)]
    return {"week": week, "daily_workouts": workouts}


@pytest.fixture
def connected(test_db) -> User:
    user = User(
        id="ambient-user",
        email="ambient@example.com",
        intervals_athlete_id="i900",
        intervals_access_token="token-900",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db, connected) -> TrainingPlan:
    tp = TrainingPlan(
        id="ambient-plan",
        user_id=connected.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=6,
        start_date=datetime.combine(
            date.today() - timedelta(days=7), datetime.min.time()
        ),
        plan_data=[_week(w) for w in range(1, 7)],
    )
    test_db.add(tp)
    test_db.commit()
    return tp


@pytest.fixture
def no_watch_roll(monkeypatch):
    """Stub the watch reconciler; it has its own suite and its own session."""
    calls: list[tuple[str, str]] = []

    async def _fake(plan_id, user_id, intervals_service):
        calls.append((plan_id, user_id))
        return 2

    monkeypatch.setattr(ambient_module, "resync_plan_to_watch", _fake)
    return calls


# ---------------------------------------------------------------------------
# Importing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unconnected_runner_is_not_a_candidate(test_db, no_watch_roll):
    test_db.add(User(id="offline", email="offline@example.com"))
    test_db.commit()

    summary = await AmbientSyncService(test_db, _FakeSync()).run()

    assert summary["candidates"] == 0


@pytest.mark.asyncio
async def test_a_connected_runner_is_synced_without_being_asked(
    test_db, connected, no_watch_roll
):
    intervals = _FakeSync(synced=3)

    summary = await AmbientSyncService(test_db, intervals).run()

    assert summary["candidates"] == 1
    assert summary["runs_imported"] == 3
    assert summary["users_with_new_runs"] == 1
    assert [c[0] for c in intervals.calls] == ["ambient-user"]


@pytest.mark.asyncio
async def test_the_import_overlaps_the_stored_cursor_by_a_day(
    test_db, connected, no_watch_roll
):
    """An activity uploaded late would otherwise fall in the gap forever."""
    connected.intervals_last_synced_at = 1_700_000_000
    test_db.commit()
    intervals = _FakeSync(synced=1)

    await AmbientSyncService(test_db, intervals).run()

    assert intervals.calls[0][1] == 1_700_000_000 - 86400


@pytest.mark.asyncio
async def test_a_first_ever_sweep_reaches_back_the_initial_window(
    test_db, connected, no_watch_roll
):
    """A runner connected between sweeps has no cursor; reach back the same
    window the manual sync does rather than importing nothing."""
    intervals = _FakeSync(synced=0)

    await AmbientSyncService(test_db, intervals).run()

    expected = TimestampAdapter.days_ago_utc_epoch(settings.intervals_initial_sync_days)
    assert abs(intervals.calls[0][1] - expected) < 60


@pytest.mark.asyncio
async def test_nothing_new_means_no_adaptation_pass(
    test_db, connected, plan, no_watch_roll, monkeypatch
):
    """The engine walks every plan and every run, so firing it on a sweep that
    imported nothing is pure waste — daily, per runner, forever."""
    adaptations: list[str] = []

    def _record(user, db, service):
        adaptations.append(user.id)
        return []

    monkeypatch.setattr(ambient_module, "auto_map_and_adjust", _record)

    summary = await AmbientSyncService(test_db, _FakeSync(synced=0)).run()

    assert adaptations == []
    assert summary["plans_adapted"] == 0


@pytest.mark.asyncio
async def test_new_runs_reach_the_adaptive_engine(
    test_db, connected, plan, no_watch_roll
):
    """The whole point of N4: the coach notices without a button press."""
    test_db.add(
        RunLog(
            user_id=connected.id,
            training_plan_id=plan.id,
            date=datetime.combine(date.today(), datetime.min.time()),
            distance_km=8.0,
            duration_minutes=45,
        )
    )
    test_db.commit()

    summary = await AmbientSyncService(test_db, _FakeSync(synced=1)).run()

    assert summary["plans_adapted"] == 1


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_connection_with_no_usable_token_is_counted_not_skipped(
    test_db, connected, no_watch_roll
):
    """Revoked grant, or a token that stopped decrypting after a key rotation.
    The UI still shows these runners as connected, so a silent skip means the
    sync is a daily no-op nobody ever notices."""
    connected.intervals_access_token = None
    test_db.commit()
    intervals = _FakeSync(synced=3)

    summary = await AmbientSyncService(test_db, intervals).run()

    assert intervals.calls == []
    assert summary["reconnect_needed"] == 1
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_an_expired_token_is_counted_not_fatal(test_db, connected, no_watch_roll):
    """Reconnecting needs the runner, so unattended there is nothing to do but
    survive it and make the count visible."""
    intervals = _FakeSync(raises=IntervalsAuthorizationError("revoked"))

    summary = await AmbientSyncService(test_db, intervals).run()

    assert summary["reconnect_needed"] == 1
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_one_broken_runner_does_not_cost_the_others_their_sync(
    test_db, connected, no_watch_roll
):
    test_db.add(
        User(
            id="ambient-user-2",
            email="two@example.com",
            intervals_athlete_id="i901",
            intervals_access_token="token-901",
        )
    )
    test_db.commit()

    class _OneBadApple(_FakeSync):
        async def sync_activities(self, user, db, after_timestamp):
            if user.id == "ambient-user":
                raise RuntimeError("malformed activity payload")
            return await super().sync_activities(user, db, after_timestamp)

    intervals = _OneBadApple(synced=2)
    summary = await AmbientSyncService(test_db, intervals).run()

    assert summary["candidates"] == 2
    assert summary["failed"] == 1
    assert summary["runs_imported"] == 2


@pytest.mark.asyncio
async def test_a_strava_failure_leaves_the_intervals_half_alone(
    test_db, connected, no_watch_roll
):
    connected.strava_athlete_id = "s55"
    test_db.commit()

    intervals = _FakeSync(synced=4)
    strava = _FakeSync(raises=RuntimeError("strava app deactivated"))

    summary = await AmbientSyncService(test_db, intervals, strava).run()

    assert summary["runs_imported"] == 4
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_a_watch_roll_failure_does_not_abort_the_remaining_plans(
    test_db, connected, plan, monkeypatch
):
    plan.watch_sync_enabled = True
    second = TrainingPlan(
        id="ambient-plan-2",
        user_id=connected.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=6,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=[_week(1)],
        watch_sync_enabled=True,
    )
    test_db.add(second)
    test_db.commit()

    rolled: list[str] = []

    async def _flaky(plan_id, user_id, intervals_service):
        if plan_id == "ambient-plan":
            raise RuntimeError("intervals is down")
        rolled.append(plan_id)
        return 1

    monkeypatch.setattr(ambient_module, "resync_plan_to_watch", _flaky)

    summary = await AmbientSyncService(test_db, _FakeSync()).run()

    assert rolled == ["ambient-plan-2"]
    assert summary["failed"] == 1
    assert summary["watch_plans_rolled"] == 1


# ---------------------------------------------------------------------------
# Rolling the watch window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_mirrored_plan_is_rolled_even_when_unchanged(
    test_db, connected, plan, no_watch_roll
):
    """The 21-day window is measured from *today*, so a day passing is itself
    a change — it pulls a new day into the far edge."""
    plan.watch_sync_enabled = True
    test_db.commit()

    summary = await AmbientSyncService(test_db, _FakeSync(synced=0)).run()

    assert no_watch_roll == [("ambient-plan", "ambient-user")]
    assert summary["watch_plans_rolled"] == 1
    assert summary["watch_events_written"] == 2


@pytest.mark.asyncio
async def test_a_plan_that_was_never_mirrored_is_left_alone(
    test_db, connected, plan, no_watch_roll
):
    summary = await AmbientSyncService(test_db, _FakeSync()).run()

    assert no_watch_roll == []
    assert summary["watch_plans_rolled"] == 0


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_dry_run_calls_no_provider_at_all(
    test_db, connected, plan, no_watch_roll
):
    plan.watch_sync_enabled = True
    test_db.commit()
    intervals = _FakeSync(synced=5)

    summary = await AmbientSyncService(test_db, intervals).run(dry_run=True)

    assert intervals.calls == []
    assert no_watch_roll == []
    assert summary["candidates"] == 1
    assert summary["watch_plans_rolled"] == 1
    assert summary["runs_imported"] == 0


@pytest.mark.asyncio
async def test_limit_chunks_a_sweep_that_has_grown_too_slow(
    test_db, connected, no_watch_roll
):
    for n in range(3):
        test_db.add(
            User(
                id=f"ambient-extra-{n}",
                email=f"extra{n}@example.com",
                intervals_athlete_id=f"i-extra-{n}",
                intervals_access_token="t",
            )
        )
    test_db.commit()

    intervals = _FakeSync(synced=1)
    summary = await AmbientSyncService(test_db, intervals).run(limit=2)

    assert summary["candidates"] == 2
    assert len(intervals.calls) == 2
