"""Watch wellness import: parsing, storage, the passive check-in, and scopes."""

from datetime import date, timedelta

import pytest

from app.application.wellness_sync_service import refresh_wellness
from app.contexts.runner.wellness.checkin_service import CheckInService
from app.contexts.runner.wellness.wellness_service import WEARABLE, WellnessService
from app.infrastructure.integrations.intervals_service import (
    LEGACY_SCOPES,
    IntervalsScopeMissing,
    parse_wellness_rows,
)
from app.models import ReadinessLog, User, WellnessDay

TODAY = date(2026, 9, 24)


@pytest.fixture
def runner(test_db) -> User:
    user = User(
        id="well-user",
        email="well@example.com",
        intervals_athlete_id="i77",
        intervals_access_token="tok",
    )
    test_db.add(user)
    test_db.commit()
    return user


def _rows(days: int, hrv: float = 60.0, rhr: int = 50, sleep_secs: int = 27000):
    return [
        {
            "id": (TODAY - timedelta(days=d)).isoformat(),
            "hrv": hrv,
            "restingHR": rhr,
            "sleepSecs": sleep_secs,
            "sleepScore": 80,
        }
        for d in range(days)
    ]


def test_parse_keeps_objective_markers_and_drops_junk():
    rows = parse_wellness_rows(
        [
            {"id": "2026-09-24", "hrv": 55.5, "restingHR": 48, "sleepSecs": 25200},
            {"id": "2026-09-23", "hrv": 0, "restingHR": 300, "sleepSecs": None},
            {"id": "bad-date", "hrv": 50},
            "not a dict",
        ]
    )
    assert rows == [
        {
            "date": date(2026, 9, 24),
            "hrv": 55.5,
            "resting_hr": 48,
            "sleep_hours": 7.0,
            "sleep_score": None,
        }
    ]


def test_upsert_never_blanks_a_value_it_already_holds(test_db, runner):
    service = WellnessService(test_db)
    service.upsert_days(runner.id, [{"date": TODAY, "hrv": 60.0, "resting_hr": 50}])
    service.upsert_days(runner.id, [{"date": TODAY, "hrv": None, "sleep_hours": 7.2}])
    row = service.day(runner.id, TODAY)
    assert (row.hrv, row.resting_hr, row.sleep_hours) == (60.0, 50, 7.2)


def test_wearable_log_stands_in_until_the_runner_checks_in(test_db, runner):
    service = WellnessService(test_db)
    service.upsert_days(runner.id, parse_wellness_rows(_rows(10)))
    log = service.ensure_wearable_log(runner.id, TODAY)
    assert log is not None and log.source == WEARABLE and log.score == 69.0

    # The runner's own word replaces the watch's...
    CheckInService(test_db).record(runner.id, energy=2, soreness=4, on_date=TODAY)
    stored = test_db.query(ReadinessLog).filter_by(user_id=runner.id).one()
    assert stored.source == "checkin"
    # ...and the watch never overwrites it afterwards.
    assert service.ensure_wearable_log(runner.id, TODAY) is None


class FakeIntervals:
    def __init__(self, rows=None, raises=None):
        self.rows = rows or []
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    async def fetch_wellness(self, token, athlete_id, oldest, newest):
        self.calls.append((oldest, newest))
        if self.raises:
            raise self.raises
        return parse_wellness_rows(self.rows)


@pytest.mark.asyncio
async def test_first_refresh_backfills_a_baseline_then_only_recent_days(
    test_db, runner
):
    intervals = FakeIntervals(_rows(10))
    await refresh_wellness(runner, test_db, intervals, today=TODAY)
    assert intervals.calls[0][0] == (TODAY - timedelta(days=29)).isoformat()
    await refresh_wellness(runner, test_db, intervals, today=TODAY)
    assert intervals.calls[1][0] == (TODAY - timedelta(days=3)).isoformat()
    assert test_db.query(WellnessDay).count() == 10


@pytest.mark.asyncio
async def test_a_pre_wellness_grant_is_pinned_so_we_stop_asking(test_db, runner):
    intervals = FakeIntervals(raises=IntervalsScopeMissing("403"))
    assert await refresh_wellness(runner, test_db, intervals, today=TODAY) == 0
    assert runner.intervals_scopes == LEGACY_SCOPES
    await refresh_wellness(runner, test_db, intervals, today=TODAY)
    assert len(intervals.calls) == 1


@pytest.mark.asyncio
async def test_provider_errors_never_escape(test_db, runner):
    intervals = FakeIntervals(raises=RuntimeError("boom"))
    assert await refresh_wellness(runner, test_db, intervals, today=TODAY) == 0
