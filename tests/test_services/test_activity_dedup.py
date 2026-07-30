"""Tests for cross-source duplicate detection of imported activities."""

from datetime import datetime

import pytest

from app.infrastructure.integrations.activity_dedup import (
    find_duplicate_run,
    is_same_activity,
)
from app.models.run_log import RunLog
from app.models.user import User


def test_same_start_and_distance_is_the_same_activity():
    when = datetime(2026, 4, 4, 8, 12, 50)
    assert is_same_activity(when, 19.02, when, 19.02)


def test_providers_may_disagree_slightly_on_distance():
    when = datetime(2026, 4, 4, 8, 12, 50)
    assert is_same_activity(when, 19.02, when, 19.13)
    assert not is_same_activity(when, 19.02, when, 19.60)


def test_a_whole_hour_clock_offset_is_still_the_same_activity():
    """One provider can still be on the pre-DST offset for the same run."""
    assert is_same_activity(
        datetime(2025, 10, 28, 12, 50, 58),
        6.16,
        datetime(2025, 10, 28, 13, 50, 58),
        6.16,
    )


def test_two_runs_the_same_morning_are_not_a_duplicate():
    assert not is_same_activity(
        datetime(2026, 6, 3, 14, 31, 1),
        0.93,
        datetime(2026, 6, 3, 14, 44, 22),
        1.69,
    )


def test_identical_distance_hours_apart_is_not_a_duplicate():
    """A double day: the same loop twice, morning and evening."""
    assert not is_same_activity(
        datetime(2026, 6, 3, 8, 0, 0),
        5.0,
        datetime(2026, 6, 3, 18, 0, 0),
        5.0,
    )


@pytest.mark.parametrize(
    "date_b, distance_b",
    [(None, 5.0), (datetime(2026, 4, 4, 8, 0), None)],
)
def test_missing_fields_never_match(date_b, distance_b):
    assert not is_same_activity(datetime(2026, 4, 4, 8, 0), 5.0, date_b, distance_b)


@pytest.fixture
def user_with_run(test_db):
    user = User(id="dedup-user", email="dedup@example.com")
    test_db.add(user)
    test_db.add(
        RunLog(
            id="existing-run",
            user_id="dedup-user",
            date=datetime(2026, 4, 4, 8, 12, 50),
            distance_km=19.02,
            source="intervals",
        )
    )
    test_db.commit()
    return user


def test_find_duplicate_run_matches_the_other_providers_row(test_db, user_with_run):
    found = find_duplicate_run(
        test_db, "dedup-user", datetime(2026, 4, 4, 8, 12, 50), 19.02
    )
    assert found is not None
    assert found.id == "existing-run"


def test_find_duplicate_run_ignores_another_runners_activity(test_db, user_with_run):
    assert (
        find_duplicate_run(
            test_db, "someone-else", datetime(2026, 4, 4, 8, 12, 50), 19.02
        )
        is None
    )


def test_find_duplicate_run_returns_none_for_a_new_run(test_db, user_with_run):
    assert (
        find_duplicate_run(
            test_db, "dedup-user", datetime(2026, 4, 5, 8, 12, 50), 19.02
        )
        is None
    )
