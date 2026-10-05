"""The Coach page's judgement: what each pattern reads as, and which one leads."""

import pytest

from app.core.coaching.intensity_split import IntensitySplit
from app.core.coaching.training_read import (
    CHANGE,
    EARLY_DAYS,
    GOAL_BEHIND,
    GOAL_DRIFTING,
    GOAL_ON_TRACK,
    GOAL_TOO_EARLY,
    GOOD,
    NO_RUNS,
    READY,
    WATCH,
    GoalTime,
    GoalWindow,
    RecentTraining,
    Week,
    read_training,
)

BALANCED = IntensitySplit(easy_km=80.0, hard_km=20.0, runs=16)
ALL_EASY = IntensitySplit(easy_km=100.0, hard_km=0.0, runs=16)
TOO_HARD = IntensitySplit(easy_km=50.0, hard_km=50.0, runs=16)


def _recent(**overrides) -> RecentTraining:
    """A runner with nothing to change: steady, balanced, with a long run."""
    defaults = {
        "weeks": [Week(km=30.0, runs=4)] * 6,
        "days_since_last_run": 1,
        "run_lengths_km": [6.0, 6.0, 8.0, 12.0] * 4,
        "split": BALANCED,
        "fitness_trend": "stable",
    }
    return RecentTraining(**{**defaults, **overrides})


def _goal(**overrides) -> GoalWindow:
    """Three plan weeks run exactly as written."""
    defaults = {
        "weeks": 3,
        "planned_sessions": 12,
        "done_sessions": 12,
        "planned_km": 120.0,
        "actual_km": 120.0,
        "planned_long_km": 18.0,
        "longest_km": 18.0,
    }
    return GoalWindow(**{**defaults, **overrides})


def _keys(findings) -> set[str]:
    return {finding.key for finding in findings}


def _read(recent=None, **kwargs):
    return read_training(recent or _recent(), has_goal=False, **kwargs)


# -- States ------------------------------------------------------------------


def test_a_runner_with_no_runs_gets_no_findings():
    read = _read(_recent(days_since_last_run=None, run_lengths_km=[], split=None))

    assert read.state == NO_RUNS and read.headline == "no_runs"
    assert read.recent_findings == () and read.focus is None


def test_too_few_runs_is_not_read_as_a_pattern():
    read = _read(_recent(run_lengths_km=[5.0, 5.0], split=None))

    assert read.state == EARLY_DAYS and read.headline == "early_days"
    assert read.recent_findings == ()


def test_a_layoff_is_named_even_with_too_few_runs_to_read():
    read = _read(_recent(run_lengths_km=[5.0], split=None, days_since_last_run=21))

    assert read.state == EARLY_DAYS
    assert read.focus is not None and read.focus.key == "gone_quiet"
    assert read.focus.figures == (21,)


def test_steady_balanced_training_has_nothing_to_change():
    read = _read()

    assert read.state == READY and read.headline == "steady"
    assert read.focus is None
    assert _keys(read.recent_findings) == {
        "steady",
        "balanced",
        "load_steady",
        "long_ok",
    }
    assert all(finding.status == GOOD for finding in read.recent_findings)


# -- Recent running ----------------------------------------------------------


def test_all_easy_running_has_room_for_a_harder_session():
    read = _read(_recent(split=ALL_EASY))

    assert read.focus is not None and read.focus.key == "all_easy"
    assert read.focus.status == WATCH and read.headline == "tune"


def test_too_much_hard_running_must_change():
    read = _read(_recent(split=TOO_HARD))

    assert read.focus is not None and read.focus.key == "too_hard"
    assert read.focus.figures == (50,)
    assert read.headline == "attention"


def test_a_volume_jump_is_flagged_against_the_weeks_before_it():
    weeks = [Week(km=30.0, runs=4)] * 3 + [Week(km=42.0, runs=5)]

    read = _read(_recent(weeks=weeks))

    assert read.focus is not None and read.focus.key == "load_jump"
    assert read.focus.figures == (42.0, 30.0)


def test_a_small_week_growing_by_a_few_km_is_not_a_jump():
    weeks = [Week(km=7.0, runs=2)] * 3 + [Week(km=10.0, runs=3)]

    read = _read(_recent(weeks=weeks, run_lengths_km=[3.0, 3.0, 4.0, 6.0]))

    assert "load_jump" not in _keys(read.recent_findings)


def test_a_volume_drop_is_worth_a_look_without_a_plan():
    weeks = [Week(km=30.0, runs=4)] * 3 + [Week(km=12.0, runs=2)]

    assert "load_drop" in _keys(_read(_recent(weeks=weeks)).recent_findings)


def test_fewer_than_four_weeks_says_nothing_about_load():
    read = _read(_recent(weeks=[Week(km=30.0, runs=4)] * 3))

    assert not _keys(read.recent_findings) & {"load_jump", "load_drop", "load_steady"}


def test_a_blank_week_makes_the_rhythm_patchy():
    weeks = [Week(km=30.0, runs=4), Week(km=0.0, runs=0)] * 2

    read = _read(_recent(weeks=weeks + [Week(km=30.0, runs=4)]))

    assert "patchy" in _keys(read.recent_findings)


def test_two_runs_a_week_has_room_for_a_third():
    read = _read(_recent(weeks=[Week(km=14.0, runs=2)] * 6))

    assert "light" in _keys(read.recent_findings)


def test_runs_of_one_length_are_missing_a_long_run():
    read = _read(_recent(run_lengths_km=[6.0, 6.5, 6.0, 7.0, 6.0]))

    assert read.focus is not None and read.focus.key == "same_length"
    assert read.focus.figures == (7.0, 6.0)


def test_a_long_run_carrying_the_week_is_flagged():
    read = _read(_recent(run_lengths_km=[5.0, 5.0, 5.0, 20.0]))

    assert "long_too_big" in _keys(read.recent_findings)


@pytest.mark.parametrize(
    "trend,key", [("improving", "fitness_up"), ("declining", "fitness_down")]
)
def test_a_fitness_trend_is_reported_only_when_it_moves(trend, key):
    assert key in _keys(_read(_recent(fitness_trend=trend)).recent_findings)
    assert not _keys(_read().recent_findings) & {"fitness_up", "fitness_down"}


# -- A plan in progress changes what the recent read may suggest -------------


def test_a_plan_owns_the_quality_so_all_easy_is_not_a_gap():
    read = read_training(_recent(split=ALL_EASY), has_goal=True, goal=_goal())

    assert "easy_by_plan" in _keys(read.recent_findings)
    assert read.focus is None


def test_a_plan_owns_the_long_run_and_its_own_deloads():
    weeks = [Week(km=30.0, runs=2)] * 3 + [Week(km=12.0, runs=2)]
    recent = _recent(weeks=weeks, run_lengths_km=[6.0, 6.0, 6.0, 6.0])

    read = read_training(recent, has_goal=True, goal=_goal())

    assert not _keys(read.recent_findings) & {"same_length", "load_drop", "light"}


# -- Against the goal --------------------------------------------------------


def test_a_plan_run_as_written_is_on_track():
    read = read_training(_recent(), has_goal=True, goal=_goal())

    assert read.goal_state == GOAL_ON_TRACK and read.headline == "goal_on_track"
    assert _keys(read.goal_findings) == {"sessions_ok", "volume_ok", "long_on_plan"}


def test_a_plan_with_no_completed_week_is_too_early_to_judge():
    read = read_training(_recent(), has_goal=True, goal=None)

    assert read.goal_state == GOAL_TOO_EARLY and read.goal_findings == ()
    assert read.headline == "goal_too_early"


@pytest.mark.parametrize(
    "overrides,key,status",
    [
        ({"done_sessions": 9}, "sessions_slipping", WATCH),
        ({"done_sessions": 5}, "sessions_missed", CHANGE),
        ({"actual_km": 100.0}, "volume_light", WATCH),
        ({"actual_km": 70.0}, "volume_short", CHANGE),
        ({"actual_km": 150.0}, "volume_over", WATCH),
        ({"longest_km": 15.0}, "long_light", WATCH),
        ({"longest_km": 10.0}, "long_short", CHANGE),
    ],
)
def test_each_shortfall_is_graded_by_how_far_off_it_is(overrides, key, status):
    read = read_training(_recent(), has_goal=True, goal=_goal(**overrides))

    finding = next(f for f in read.goal_findings if f.key == key)
    assert finding.status == status
    assert read.goal_state == (GOAL_BEHIND if status == CHANGE else GOAL_DRIFTING)
    assert read.focus == finding


def test_a_week_with_nothing_planned_is_not_judged():
    goal = _goal(planned_sessions=0, planned_km=0.0, planned_long_km=0.0)

    read = read_training(_recent(), has_goal=True, goal=goal)

    assert read.goal_findings == () and read.goal_state == GOAL_TOO_EARLY


# -- Goal time ---------------------------------------------------------------

FIFTY_MINUTES = 3000


def _time(predicted: int, weeks_to_go: int = 8) -> GoalTime:
    return GoalTime(
        goal_seconds=FIFTY_MINUTES, predicted_seconds=predicted, weeks_to_go=weeks_to_go
    )


@pytest.mark.parametrize(
    "predicted,key,status",
    [
        (2950, "time_ahead", GOOD),
        (3000, "time_ahead", GOOD),
        # Eight weeks closes about 4%: 3100 is 3.3% away, 3200 is 6.7%, 3300 is 10%.
        (3100, "time_reachable", GOOD),
        (3200, "time_stretch", WATCH),
        (3300, "time_far", CHANGE),
    ],
)
def test_a_goal_time_is_judged_by_the_gap_the_weeks_left_can_close(
    predicted, key, status
):
    read = read_training(
        _recent(), has_goal=True, goal=_goal(), goal_time=_time(predicted)
    )

    finding = next(f for f in read.goal_findings if f.area == "race_time")
    assert (finding.key, finding.status) == (key, status)
    assert finding.figures == (predicted, FIFTY_MINUTES)


def test_the_same_gap_is_out_of_reach_with_no_weeks_left():
    early = read_training(
        _recent(), has_goal=True, goal=_goal(), goal_time=_time(3100, weeks_to_go=8)
    )
    late = read_training(
        _recent(), has_goal=True, goal=_goal(), goal_time=_time(3100, weeks_to_go=0)
    )

    assert early.goal_state == GOAL_ON_TRACK
    assert late.goal_state == GOAL_BEHIND
    assert late.focus is not None and late.focus.key == "time_far"


def test_no_block_is_credited_with_closing_more_than_the_ceiling():
    read = read_training(
        _recent(), has_goal=True, goal=_goal(), goal_time=_time(3400, weeks_to_go=40)
    )

    assert "time_far" in _keys(read.goal_findings)


def test_a_goal_time_is_judged_before_the_first_plan_week_is_done():
    read = read_training(_recent(), has_goal=True, goal=None, goal_time=_time(3300))

    assert _keys(read.goal_findings) == {"time_far"}
    assert read.goal_state == GOAL_BEHIND


def test_missing_the_planned_runs_outranks_an_unreachable_time():
    read = read_training(
        _recent(),
        has_goal=True,
        goal=_goal(done_sessions=5),
        goal_time=_time(3300),
    )

    assert read.focus is not None and read.focus.key == "sessions_missed"


def test_a_time_with_nothing_to_compare_is_not_judged():
    read = read_training(_recent(), has_goal=True, goal=_goal(), goal_time=_time(0))

    assert "race_time" not in {finding.area for finding in read.goal_findings}


# -- The one change: safety, then the goal, then refinements -----------------


def test_a_volume_jump_outranks_being_behind_on_the_goal():
    weeks = [Week(km=30.0, runs=4)] * 3 + [Week(km=45.0, runs=5)]

    read = read_training(
        _recent(weeks=weeks), has_goal=True, goal=_goal(actual_km=70.0)
    )

    assert read.goal_state == GOAL_BEHIND
    assert read.focus is not None and read.focus.key == "load_jump"


def test_being_behind_on_the_goal_outranks_a_refinement():
    read = read_training(
        _recent(fitness_trend="declining"),
        has_goal=True,
        goal=_goal(longest_km=10.0),
    )

    assert read.focus is not None and read.focus.key == "long_short"


def test_on_track_with_a_recent_concern_says_both():
    read = read_training(_recent(split=TOO_HARD), has_goal=True, goal=_goal())

    assert read.goal_state == GOAL_ON_TRACK
    assert read.headline == "goal_on_track_but"
    assert read.focus is not None and read.focus.key == "too_hard"
