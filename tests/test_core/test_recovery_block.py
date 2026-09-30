"""The recovery block prescribed after a race plan finishes.

Pins the coaching rules the block exists to keep: length follows the race
(one easy day per mile, rounded to weeks, plus a week back to steady), volume
climbs back to — and never past — the share of peak the "Recover first" line
quotes, and the days straight after the race stay quiet.
"""

from datetime import date

import pytest

from app.core.race.recovery import NEXT_BLOCK_FRACTION
from app.core.training.periodization.plan_calendar import plan_has_ended
from app.core.training.periodization.recovery_block import (
    build_recovery_block,
    peak_weekly_km,
    recovery_prescription,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator

ZONES = VDOTCalculator.get_pace_zones(45)


def _block(race_km=42.2, peak_km=60.0, runs=4, zones=ZONES):
    return build_recovery_block(
        race_km=race_km,
        race_name="Marathon",
        peak_km=peak_km,
        runs_per_week=runs,
        pace_zones=zones,
    )


def _runs(week):
    return [d for d in week["daily_workouts"] if d["type"] != "rest"]


@pytest.mark.parametrize(
    ("race_km", "weeks"),
    [(5.0, 2), (10.0, 2), (21.1, 3), (42.2, 5), (100.0, 5)],
)
def test_block_length_follows_the_race(race_km, weeks):
    assert recovery_prescription(race_km).weeks == weeks


@pytest.mark.parametrize("race_km", [5.0, 21.1, 42.2, 160.0])
def test_volume_climbs_back_to_the_next_block_share_of_peak(race_km):
    fractions = recovery_prescription(race_km).volume_fractions

    assert list(fractions) == sorted(fractions)
    assert fractions[-1] == pytest.approx(NEXT_BLOCK_FRACTION)
    assert max(fractions) <= NEXT_BLOCK_FRACTION


def test_every_week_sums_to_its_target_and_every_day_is_present():
    for week in _block():
        assert [d["day"] for d in week["daily_workouts"]] == list(range(1, 8))
        total = round(sum(d["distance"] for d in week["daily_workouts"]), 1)
        assert total == week["total_km"] == week["weekly_target_km"]
        assert week["is_recovery"] is True
        assert week["phase"] == "recovery"


def test_first_week_is_short_easy_running_after_two_days_off():
    first = _block()[0]
    by_day = {d["day"]: d for d in first["daily_workouts"]}

    assert by_day[1]["type"] == "rest" and by_day[2]["type"] == "rest"
    for run in _runs(first):
        assert run["type"] == "easy"
        assert all(step["kind"] != "strides" for step in run["steps"])
        assert run["steps"][0]["effort"] == "very easy"
    # One run fewer than the runner was doing.
    assert len(_runs(first)) == 3


def test_no_quality_anywhere_in_the_block():
    for week in _block():
        for run in _runs(week):
            assert run["type"] in {"easy", "long"}
            assert run["intensity"] == "low"
            zones = {s["pace_zone"] for s in run["steps"]}
            assert zones <= {"E", "R"}  # R only for strides


def test_long_run_returns_longer_than_the_easy_days():
    for week in _block()[1:]:
        runs = _runs(week)
        long_runs = [r for r in runs if r["type"] == "long"]
        assert len(long_runs) == 1
        assert long_runs[0]["day"] == 6
        easy = [r["distance"] for r in runs if r["type"] == "easy"]
        assert long_runs[0]["distance"] > max(easy)


def test_strides_are_carved_out_of_the_run_not_added_on_top():
    for week in _block():
        for run in _runs(week):
            steps_m = sum(
                (s["distance_m"] or 0) * (s["repeat"] or 1) for s in run["steps"]
            )
            assert steps_m == pytest.approx(run["distance"] * 1000, abs=1)


def test_strides_return_late_after_a_marathon():
    weeks = _block()
    has_strides = [
        any(step["kind"] == "strides" for run in _runs(week) for step in run["steps"])
        for week in weeks
    ]
    assert has_strides == [False, False, False, True, True]


def test_a_low_volume_runner_is_never_pushed_above_their_own_peak():
    block = _block(race_km=5.0, peak_km=8.0, runs=2)

    for week in block:
        assert week["total_km"] <= 8.0 * NEXT_BLOCK_FRACTION + 0.05
        assert len(_runs(week)) == 2


def test_no_pace_zones_still_builds_a_runnable_block():
    block = _block(zones=None)
    assert all(run["steps"] for week in block for run in _runs(week))


def test_zero_peak_builds_nothing():
    assert _block(peak_km=0.0) == []


def test_peak_weekly_km_reads_the_biggest_week():
    assert peak_weekly_km([{"total_km": 30}, {"total_km": 52.5}, {}]) == 52.5
    assert peak_weekly_km([]) == 0.0


def test_a_plan_ends_on_the_monday_after_its_last_week():
    start = date(2026, 3, 2)  # a Monday

    assert not plan_has_ended(start, 2, date(2026, 3, 15))  # last Sunday
    assert plan_has_ended(start, 2, date(2026, 3, 16))  # the Monday after
    assert not plan_has_ended(None, 2, date(2026, 3, 16))
    assert not plan_has_ended(start, None, date(2027, 1, 1))
