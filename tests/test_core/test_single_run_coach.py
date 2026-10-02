"""The pure halves of the single-run coach: split, pick, and review."""

from datetime import date, timedelta

import pytest

from app.core.coaching.intensity_split import (
    BALANCED,
    MOSTLY_EASY,
    TOO_HARD,
    intensity_split,
    is_hard_session,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.workouts.single_run import build_single_run
from app.core.training.workouts.single_run_review import (
    FASTER,
    FULL,
    ON_TARGET,
    OVER,
    SHORT,
    SLOWER,
    review_single_run,
)
from app.core.training.workouts.single_run_suggestion import (
    COMING_BACK,
    HARD_RECENTLY,
    LONG_DUE,
    LOW_READINESS_REASON,
    NO_HISTORY,
    PLAN_OWNS_QUALITY,
    PLAN_TODAY,
    QUALITY_DUE,
    REST_DAY,
    REST_DAY_LOW,
    STEADY,
    TOO_MUCH_HARD,
    RecentRun,
    suggest_single_run,
)

TODAY = date(2026, 10, 2)
ZONES = VDOTCalculator.get_pace_zones(45)


# -- split ------------------------------------------------------------------


def test_split_counts_whole_sessions_by_distance():
    split = intensity_split(
        [("easy", 8.0), ("long", 16.0), (None, 6.0), ("tempo", 10.0)]
    )
    assert split is not None
    assert (split.easy_km, split.hard_km, split.runs) == (30.0, 10.0, 4)
    assert split.easy_share == pytest.approx(0.75)
    assert split.verdict == BALANCED


@pytest.mark.parametrize(
    "runs, verdict",
    [
        ([("tempo", 8.0), ("interval", 8.0), ("easy", 6.0), ("easy", 6.0)], TOO_HARD),
        ([("easy", 8.0)] * 5, MOSTLY_EASY),
    ],
)
def test_split_verdicts(runs, verdict):
    split = intensity_split(runs)
    assert split is not None and split.verdict == verdict


def test_split_refuses_to_judge_too_little_running():
    assert intensity_split([("easy", 8.0), ("tempo", 8.0)]) is None
    assert intensity_split([("easy", 2.0)] * 4) is None
    assert intensity_split([("easy", None), ("easy", 0.0)]) is None


def test_untyped_and_long_runs_are_easy_volume():
    assert not is_hard_session(None)
    assert not is_hard_session("long")
    assert is_hard_session("cruise_interval")
    assert is_hard_session("race")


# -- pick -------------------------------------------------------------------


def _run(days_ago: int, km: float, family="easy", hard=False) -> RecentRun:
    return RecentRun(TODAY - timedelta(days=days_ago), km, family, hard)


def _pick(runs, **overrides):
    args = dict(
        today=TODAY,
        runs=runs,
        weekly_km=30.0,
        split=intensity_split(
            ("tempo" if run.hard else run.family, run.distance_km) for run in runs
        ),
        readiness_score=None,
        has_plan=False,
        planned_today=False,
    )
    args.update(overrides)
    return suggest_single_run(**args)


EASY_WEEKS = [_run(d, 8.0) for d in (1, 3, 5, 8, 10, 12)] + [_run(2, 14.0, "long")]


def test_no_history_starts_short_and_easy():
    pick = _pick([], weekly_km=0.0)
    assert (pick.run_type, pick.reason) == ("easy", NO_HISTORY)
    assert pick.distance_km <= 5.0


def test_a_run_down_morning_beats_everything_else():
    pick = _pick(EASY_WEEKS, readiness_score=30.0)
    assert (pick.run_type, pick.reason) == ("easy", LOW_READINESS_REASON)
    assert pick.distance_km < 8.0


def test_a_layoff_eases_back_in():
    pick = _pick([_run(d, 8.0) for d in (12, 14, 16, 18)])
    assert (pick.run_type, pick.reason) == ("easy", COMING_BACK)


def test_a_hard_session_two_days_ago_means_easy_today():
    pick = _pick(EASY_WEEKS + [_run(2, 9.0, "tempo", hard=True)])
    assert (pick.run_type, pick.reason) == ("easy", HARD_RECENTLY)


def test_an_extra_on_a_plan_day_is_short():
    pick = _pick(EASY_WEEKS, has_plan=True, planned_today=True)
    assert (pick.run_type, pick.reason) == ("easy", PLAN_TODAY)
    assert pick.distance_km < 8.0


def test_too_much_hard_running_prescribes_easy():
    runs = [_run(d, 8.0, "tempo", hard=True) for d in (4, 7, 11)] + [_run(5, 6.0)]
    pick = _pick(runs)
    assert (pick.run_type, pick.reason) == ("easy", TOO_MUCH_HARD)


def test_a_plan_owns_the_quality():
    pick = _pick(EASY_WEEKS, has_plan=True)
    assert (pick.run_type, pick.reason) == ("easy", PLAN_OWNS_QUALITY)


def test_a_week_without_a_long_run_makes_one_due():
    runs = [_run(d, 8.0) for d in (1, 3, 5, 8, 10)] + [_run(9, 14.0, "long")]
    pick = _pick(runs)
    assert (pick.run_type, pick.reason) == ("long", LONG_DUE)
    # About a third of the week, never a leap past the longest recent run.
    assert 8.0 <= pick.distance_km <= 14.0 * 1.1


def test_fresh_and_mostly_easy_earns_quality_and_alternates():
    pick = _pick(EASY_WEEKS)
    assert (pick.run_type, pick.reason) == ("tempo", QUALITY_DUE)

    after_a_tempo = EASY_WEEKS + [_run(6, 8.0, "tempo", hard=True)]
    assert _pick(after_a_tempo).run_type == "interval"


def test_thin_history_stays_easy():
    pick = _pick([_run(1, 3.0), _run(3, 3.0)], weekly_km=6.0)
    assert (pick.run_type, pick.reason) == ("easy", STEADY)


def test_the_rest_day_link_always_gets_a_gentle_run():
    pick = _pick(EASY_WEEKS, rest_day=True)
    assert (pick.run_type, pick.reason) == ("easy", REST_DAY)
    assert pick.distance_km <= 5.0
    assert _pick(EASY_WEEKS, rest_day=True, readiness_score=20.0).reason == REST_DAY_LOW


def test_every_pick_is_a_distance_the_builder_accepts():
    for runs in ([], EASY_WEEKS, [_run(9, 40.0, "long")] + EASY_WEEKS[:5]):
        for weekly in (0.0, 12.0, 30.0, 120.0):
            pick = _pick(runs, weekly_km=weekly)
            build_single_run(pick.run_type, pick.distance_km, ZONES, weekly)


# -- review -----------------------------------------------------------------


def test_an_easy_run_is_judged_against_its_pace_range():
    workout = build_single_run("easy", 6.0, ZONES, 30.0)
    review = review_single_run(workout, 6.0, 5.6)
    assert review is not None and not review.is_session_average
    assert (review.pace_verdict, review.distance_verdict) == (ON_TARGET, FULL)
    assert review.target_fast < review.target_slow

    assert review_single_run(workout, 6.0, 4.9).pace_verdict == FASTER
    assert review_single_run(workout, 6.0, 6.5).pace_verdict == SLOWER


def test_a_structured_run_is_judged_against_the_session_average():
    workout = build_single_run("tempo", 8.0, ZONES, 30.0)
    review = review_single_run(workout, 8.0, 5.1)
    assert review is not None and review.is_session_average
    # Slower than the tempo pace, faster than the easy bookends.
    assert ZONES["T"]["pace_min_km"] < review.target_fast
    assert review.target_fast < ZONES["E"]["pace_min_km_slow"]
    assert review.target_slow == review.target_fast

    on_it = review_single_run(workout, 8.0, review.target_fast)
    assert on_it.pace_verdict == ON_TARGET
    assert review_single_run(workout, 8.0, 4.3).pace_verdict == FASTER


def test_distance_is_reported_when_it_was_not_the_full_session():
    workout = build_single_run("easy", 8.0, ZONES, 30.0)
    assert review_single_run(workout, 5.0, 5.6).distance_verdict == SHORT
    assert review_single_run(workout, 11.0, 5.6).distance_verdict == OVER


def test_nothing_is_claimed_without_a_pace_on_either_side():
    by_effort = build_single_run("tempo", 8.0, None, 30.0)
    assert review_single_run(by_effort, 8.0, 5.0) is None
    paced = build_single_run("easy", 6.0, ZONES, 30.0)
    assert review_single_run(paced, 6.0, None) is None
