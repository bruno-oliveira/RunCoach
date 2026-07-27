"""Tests for the home-page pace + HR-zone evolution aggregation."""

import uuid
from datetime import datetime, timezone

from app.contexts.runner.fitness.home_stats_service import HomeStatsService
from app.models import RunLog, User


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _in_month(months_ago: int, *, day: int = 15) -> datetime:
    """A fixed datetime ``months_ago`` calendar months back.

    The service buckets by *calendar month*, so fixtures have to pin a month
    rather than a day count. Offsets like "150 and 148 days ago" land in one
    bucket most of the year and in two whenever that pair happens to straddle a
    month boundary — which left this suite failing on a handful of dates a year,
    for a reason that looks nothing like the assertion that breaks.
    """
    now = _now()
    index = now.year * 12 + (now.month - 1) - months_ago
    return datetime(index // 12, index % 12 + 1, day)


def _make_user(db, **kwargs) -> User:
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", **kwargs)
    db.add(user)
    db.flush()
    return user


def _add_run(
    db,
    user_id,
    *,
    when,
    pace=None,
    hr=None,
    duration=50.0,
    effort_class="easy_effort",
):
    run = RunLog(
        id=_uid(),
        user_id=user_id,
        date=when,
        distance_km=10.0,
        duration_minutes=duration,
        avg_pace_min_km=pace,
        avg_heart_rate=hr,
        effort_class=effort_class,
    )
    db.add(run)
    return run


class TestPaceEvolution:
    def test_faster_easy_pace_reads_as_a_trend(self, test_db):
        user = _make_user(test_db, max_hr=190)
        # ~5 months ago: slower easy pace; recent: quicker. 2 runs/month.
        for _ in range(2):
            _add_run(test_db, user.id, when=_in_month(5), pace=6.0)
        for _ in range(2):
            _add_run(test_db, user.id, when=_in_month(0, day=1), pace=5.5)
        test_db.flush()

        stats = HomeStatsService.build(user, test_db)
        pace = stats["pace_evolution"]
        assert pace["has_data"] is True
        assert pace["effort_basis"] == "easy"
        assert len(pace["points"]) == 2
        assert pace["trend"]["direction"] == "faster"
        # 6:00 -> 5:30 == 30 s/km quicker.
        assert pace["trend"]["delta_sec_per_km"] == 30
        assert "quicker" in pace["trend"]["summary"]

    def test_falls_back_to_all_runs_when_easy_too_sparse(self, test_db):
        user = _make_user(test_db)
        # Only tempo/race runs, no easy_effort -> easy filter is empty.
        for when in (
            _in_month(4),
            _in_month(4),
            _in_month(0, day=1),
            _in_month(0, day=1),
        ):
            _add_run(test_db, user.id, when=when, pace=5.0, effort_class="tempo_effort")
        test_db.flush()

        pace = HomeStatsService.build(user, test_db)["pace_evolution"]
        assert pace["has_data"] is True
        assert pace["effort_basis"] == "all"

    def test_empty_when_under_two_months(self, test_db):
        user = _make_user(test_db)
        for _ in range(2):
            _add_run(test_db, user.id, when=_in_month(0, day=1), pace=5.5)
        test_db.flush()

        pace = HomeStatsService.build(user, test_db)["pace_evolution"]
        assert pace["has_data"] is False
        assert "empty_reason" in pace


class TestHrZoneEvolution:
    def test_distribution_and_takeaway(self, test_db):
        user = _make_user(test_db, max_hr=190)
        # Early month mostly hard (high HR); recent month mostly easy (low HR):
        # easy-zone share rises -> "aerobic base is deepening".
        for _ in range(2):
            _add_run(test_db, user.id, when=_in_month(5), pace=5.0, hr=178)
        for _ in range(2):
            _add_run(test_db, user.id, when=_in_month(0, day=1), pace=6.0, hr=125)
        test_db.flush()

        hr = HomeStatsService.build(user, test_db)["hr_zone_evolution"]
        assert hr["has_data"] is True
        assert len(hr["labels"]) == 2
        assert len(hr["series"]) == 5  # five zones
        # Each month's shares sum to ~100%.
        for i in range(len(hr["labels"])):
            assert abs(sum(s["data"][i] for s in hr["series"]) - 100.0) < 0.5
        assert "aerobic base" in (hr["takeaway"] or "")

    def test_empty_when_no_heart_rate(self, test_db):
        user = _make_user(test_db, max_hr=190)
        for when in (
            _in_month(4),
            _in_month(4),
            _in_month(0, day=1),
            _in_month(0, day=1),
        ):
            _add_run(test_db, user.id, when=when, pace=5.5, hr=None)
        test_db.flush()

        hr = HomeStatsService.build(user, test_db)["hr_zone_evolution"]
        assert hr["has_data"] is False
        assert "empty_reason" in hr
