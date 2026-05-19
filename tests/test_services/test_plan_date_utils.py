"""Tests for plan_date_utils.compute_current_week."""

from datetime import date

from app.services.plans.plan_date_utils import compute_current_week


def test_pre_start_returns_none_by_default():
    start = date(2026, 1, 5)
    assert compute_current_week(start, date(2026, 1, 4)) is None


def test_pre_start_returns_override_when_provided():
    start = date(2026, 1, 5)
    assert compute_current_week(start, date(2026, 1, 4), pre_start=0) == 0
    assert compute_current_week(start, date(2025, 12, 1), pre_start=1) == 1


def test_first_week_inclusive_of_start_date():
    start = date(2026, 1, 5)
    assert compute_current_week(start, start) == 1
    assert compute_current_week(start, date(2026, 1, 11)) == 1


def test_week_boundary_off_by_one():
    start = date(2026, 1, 5)
    # Day 7 (Sunday) is still week 1; day 8 (Monday) flips to week 2.
    assert compute_current_week(start, date(2026, 1, 11)) == 1
    assert compute_current_week(start, date(2026, 1, 12)) == 2


def test_total_weeks_clamps_max():
    start = date(2026, 1, 5)
    # 100 days in = week 15, clamped to 12.
    assert compute_current_week(start, date(2026, 4, 15), total_weeks=12) == 12


def test_total_weeks_does_not_inflate_within_range():
    start = date(2026, 1, 5)
    assert compute_current_week(start, date(2026, 1, 19), total_weeks=12) == 3


def test_clamp_min_floors_result():
    start = date(2026, 1, 5)
    # Without pre_start, pre-start returns None, so clamp_min doesn't apply.
    # With pre_start, clamp_min applies after the fact.
    assert compute_current_week(start, date(2026, 1, 5), clamp_min=1) == 1
    # Combined with pre_start=0, clamp_min raises pre-start case too? No —
    # pre_start short-circuits before clamp. Document this.
    assert (
        compute_current_week(start, date(2026, 1, 4), pre_start=0, clamp_min=1) == 0
    )


def test_combined_clamps_within_plan_range():
    start = date(2026, 1, 5)
    # 200 days in, total_weeks=12 → clamped to 12.
    assert (
        compute_current_week(
            start, date(2026, 7, 23), total_weeks=12, clamp_min=1
        )
        == 12
    )
