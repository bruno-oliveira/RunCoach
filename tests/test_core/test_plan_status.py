"""`PlanStatus` is the view model that replaced TrainingPlan's display fields.

These pin the labels the runner reads ("Week 4 of 8", "Completed", "Starts
Aug 3"), the completion rule that decides which plan is "current", and the
nullable-column edge cases that used to raise `TypeError` mid-page.
"""

from datetime import date, datetime, timedelta

from app.contexts.plan.plan_status import (
    PlanStatus,
    current_active_plan,
    in_progress_plan,
    plan_status,
    plan_statuses,
)
from app.models import TrainingPlan

TODAY = date(2026, 3, 10)


def _plan(plan_id: str = "p1", **kwargs) -> TrainingPlan:
    defaults = dict(user_id="u1", current_weekly_km=30, target_distance="10")
    defaults.update(kwargs)
    return TrainingPlan(id=plan_id, **defaults)


def test_a_plan_starting_in_the_future_has_not_started():
    plan = _plan(start_date=datetime(2026, 3, 20), weeks_duration=8)

    status = plan_status(plan, TODAY)

    assert status.label == "Starts Mar 20"
    assert status.completed is False


def test_a_plan_mid_block_reports_its_week():
    # Started 3 weeks before TODAY → week 4.
    plan = _plan(start_date=TODAY - timedelta(weeks=3), weeks_duration=8)

    status = plan_status(plan, TODAY)

    assert status.label == "Week 4 of 8"
    assert status.completed is False


def test_a_plan_past_its_last_week_is_completed():
    plan = _plan(start_date=TODAY - timedelta(weeks=9), weeks_duration=8)

    status = plan_status(plan, TODAY)

    assert status.label == "Completed"
    assert status.completed is True


def test_a_plan_with_no_start_date_is_undated_not_completed():
    """No start date means no label — and certainly not "Completed"."""
    status = plan_status(_plan(start_date=None, weeks_duration=8), TODAY)

    assert status.label is None
    assert status.completed is False


def test_a_plan_with_no_duration_is_never_claimed_complete():
    """`weeks_duration` is nullable; comparing it directly used to raise."""
    plan = _plan(start_date=TODAY - timedelta(weeks=9), weeks_duration=None)

    status = plan_status(plan, TODAY)

    assert status.completed is False
    # …and the runner is not shown the literal "None".
    assert status.label == "Week 10"


def test_the_distance_and_tier_come_from_the_plan():
    status = plan_status(_plan(current_weekly_km=10, target_distance="21.1"), TODAY)

    assert status.distance_display == "Half Marathon"
    assert status.experience_level


def test_statuses_are_keyed_by_plan_id():
    plans = [
        _plan("a", start_date=TODAY - timedelta(weeks=1), weeks_duration=8),
        _plan("b", start_date=TODAY - timedelta(weeks=9), weeks_duration=8),
    ]

    statuses = plan_statuses(plans, TODAY)

    assert set(statuses) == {"a", "b"}
    assert isinstance(statuses["a"], PlanStatus)
    assert statuses["b"].completed is True


class TestCurrentActivePlan:
    def test_prefers_the_first_unfinished_plan(self):
        # Newest first, as the repository returns them.
        plans = [
            _plan("done", start_date=TODAY - timedelta(weeks=9), weeks_duration=8),
            _plan("running", start_date=TODAY - timedelta(weeks=1), weeks_duration=8),
        ]
        statuses = plan_statuses(plans, TODAY)

        assert current_active_plan(plans, statuses).id == "running"

    def test_falls_back_to_the_newest_when_every_plan_is_done(self):
        plans = [
            _plan("newer", start_date=TODAY - timedelta(weeks=9), weeks_duration=8),
            _plan("older", start_date=TODAY - timedelta(weeks=20), weeks_duration=8),
        ]
        statuses = plan_statuses(plans, TODAY)

        assert current_active_plan(plans, statuses).id == "newer"

    def test_returns_none_without_plans(self):
        assert current_active_plan([], {}) is None


# -- in_progress_plan: the plan with a "today" ------------------------------


def test_in_progress_skips_a_newer_plan_that_has_not_started():
    # The runner built their next plan (no start date yet) mid-block: the
    # nudge and the morning brief must keep talking about the running one.
    running = _plan("running", start_date=TODAY - timedelta(weeks=2), weeks_duration=8)
    unstarted = _plan("next", weeks_duration=10)
    future = _plan("later", start_date=TODAY + timedelta(days=5), weeks_duration=10)

    assert in_progress_plan([unstarted, future, running], TODAY) is running


def test_in_progress_ignores_finished_plans():
    done = _plan("done", start_date=TODAY - timedelta(weeks=9), weeks_duration=8)
    assert in_progress_plan([done], TODAY) is None


def test_in_progress_hands_over_on_the_monday_after_the_last_week():
    start = TODAY - timedelta(weeks=8)
    finished = _plan("race", start_date=start, weeks_duration=8)
    block = _plan("block", start_date=TODAY, weeks_duration=5)

    assert in_progress_plan([block, finished], TODAY) is block
    assert in_progress_plan([finished], TODAY - timedelta(days=1)) is finished
