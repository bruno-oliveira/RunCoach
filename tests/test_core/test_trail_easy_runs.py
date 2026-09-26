"""Trail weekday easy runs stay easy runs.

Trail plans had no absolute ceiling on an easy run, and a plan-level refill
pass topped weeks back up to target by growing easy runs as far as the long
run: a 100K peak week prescribed three 42 km "easy" runs beside a 42 km long
run, and a 50K plan's easy runs kept growing into the taper as the long run
shrank.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.profiles.trail_profile import classify_trail
from app.core.training.tuning import TRAIL_MAX_EASY_RUN_KM

# (current km/week, weeks, runs/week, race km, elevation m)
TRAIL_CASES = [
    (30, 12, 4, 30, 800),
    (50, 16, 4, 50, 2500),
    (70, 20, 5, 100, 6000),
]


def _plan(current_km, weeks, runs, race_km, elevation_m):
    return TrainingPlanGenerator().generate_plan(
        current_km,
        30.0,
        weeks,
        runs,
        trail_profile=classify_trail(race_km, elevation_m),
    )


def _easy_runs(week):
    return [
        w["distance"]
        for w in week["daily_workouts"]
        if w.get("type") == "easy" and (w.get("distance") or 0) > 0
    ]


def _long_run(week):
    return max(
        (w["distance"] for w in week["daily_workouts"] if w.get("type") == "long"),
        default=0.0,
    )


# The ceiling scales with the week's *target*, which this generator doesn't
# expose; below ~107 km/week it is the flat TRAIL_MAX_EASY_RUN_KM, so pin that
# on the sub-100 km plans and cover the high-volume 100K by the ratio below.
@pytest.mark.parametrize("case", TRAIL_CASES[:2])
def test_easy_runs_respect_the_flat_trail_ceiling(case):
    plan = _plan(*case)
    for week in plan:
        for km in _easy_runs(week):
            assert km <= TRAIL_MAX_EASY_RUN_KM + 0.05, (week["week"], km)


@pytest.mark.parametrize("case", TRAIL_CASES)
def test_peak_easy_runs_stay_well_short_of_the_long_run(case):
    plan = _plan(*case)
    for week in plan:
        if week.get("phase") != "peak" or week.get("is_recovery"):
            continue
        long_km = _long_run(week)
        for km in _easy_runs(week):
            assert km <= 0.6 * long_km, (week["week"], km, long_km)


@pytest.mark.parametrize("case", TRAIL_CASES)
def test_taper_easy_runs_never_grow_past_peak(case):
    plan = _plan(*case)
    peak_easy = max(
        (km for w in plan if w.get("phase") == "peak" for km in _easy_runs(w)),
        default=0.0,
    )
    for week in plan:
        if week.get("phase") == "taper":
            for km in _easy_runs(week):
                assert km <= peak_easy + 0.05, (week["week"], km, peak_easy)
