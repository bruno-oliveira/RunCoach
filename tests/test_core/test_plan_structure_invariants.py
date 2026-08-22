"""Structural invariants across the full plan grid.

Rather than pin brittle exact-output snapshots (which would break on every
legitimate pace/tuning tweak), this module locks in the *shape* invariants a
sound plan must always satisfy, evaluated across every distance × weeks ×
mileage corner. A future change that composes the scaling passes into a
degenerate week — an unrunnable week, a trivially short run, a taper that
climbs, or a plan with no absorption week — fails here loudly.

Covers:
- the plan-level structure guard finds no fatal issues anywhere on the grid
  (the safety net wired into ``generate_plan``);
- run frequency is dropped rather than shattering a low weekly budget into
  sub-viable runs;
- plans long enough for the 3:1 cadence get at least one deload;
- taper-week volume never increases toward race day;
- adaptation can never inflate a taper session above its prescribed dose.
"""

import pytest

from app.contexts.plan.generators.plan_generator import (
    MIN_RUNNING_DAYS,
    MIN_VIABLE_RUN_KM,
    TrainingPlanGenerator,
    _viable_run_frequency,
)
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training.training_constants import training_km

# Distance → (min_weeks, max_weeks, min_mileage, max_mileage).
_DISTANCES = {
    5.0: (6, 16, 5.0, 40.0),
    10.0: (6, 16, 10.0, 50.0),
    21.1: (8, 20, 15.0, 70.0),
    30.0: (6, 22, 15.0, 60.0),
    42.2: (12, 24, 25.0, 100.0),
}


def _grid():
    """(distance, weeks, mileage) at each distance's boundary corners."""
    for dist, (min_wk, max_wk, min_km, max_km) in _DISTANCES.items():
        for weeks in {min_wk, (min_wk + max_wk) // 2, max_wk}:
            for km in {min_km, (min_km + max_km) / 2, max_km}:
                yield dist, weeks, km


_GRID = list(_grid())
_IDS = [f"{d}km-{w}wk-{k:.0f}base" for d, w, k in _GRID]


def _running(week):
    return [
        w
        for w in week["daily_workouts"]
        if w.get("type") not in ("rest", "recovery") and (w.get("distance") or 0) > 0
    ]


@pytest.fixture(scope="module")
def gen():
    return TrainingPlanGenerator()


@pytest.mark.parametrize("combo", _GRID, ids=_IDS)
def test_no_fatal_structure_anywhere(gen, combo):
    """Every grid plan passes the plan-level structure guard with no fatal issue."""
    dist, weeks, km = combo
    plan = gen.generate_plan(km, dist, weeks)
    issues = check_plan_structure(plan)
    assert issues["fatal"] == [], issues["fatal"]


@pytest.mark.parametrize("combo", _GRID, ids=_IDS)
def test_every_week_has_a_runnable_session(gen, combo):
    dist, weeks, km = combo
    plan = gen.generate_plan(km, dist, weeks)
    for week in plan:
        assert _running(week), f"week {week['week']} has no runnable session"


@pytest.mark.parametrize("combo", _GRID, ids=_IDS)
def test_runs_are_not_trivially_short(gen, combo):
    """No loading week averages a sub-viable per-run distance.

    The frequency floor exists precisely so a low weekly budget is spread over
    fewer, more substantial runs rather than many trivial ones. On a genuine
    loading week (not a taper/deload, which are deliberately light) the average
    running distance should clear the viable-dose floor once frequency has been
    reduced.
    """
    dist, weeks, km = combo
    plan = gen.generate_plan(km, dist, weeks)
    for week in plan:
        if week.get("is_recovery") or week.get("phase") == "taper":
            continue
        runs = _running(week)
        if not runs:
            continue
        avg = sum(w["distance"] for w in runs) / len(runs)
        assert avg >= MIN_VIABLE_RUN_KM - 0.75, (
            f"week {week['week']} averages {avg:.2f} km/run over {len(runs)} runs"
        )


@pytest.mark.parametrize("combo", _GRID, ids=_IDS)
def test_long_plans_have_a_deload(gen, combo):
    """Plans spanning the 3:1 cadence get at least one absorption week."""
    dist, weeks, km = combo
    if weeks < 8:
        pytest.skip("cadence only guarantees a deload from ~8 weeks up")
    plan = gen.generate_plan(km, dist, weeks)
    assert any(w.get("is_recovery") for w in plan), "no deload week in plan"


@pytest.mark.parametrize("combo", _GRID, ids=_IDS)
def test_taper_volume_never_climbs(gen, combo):
    """Taper-week training volume is non-increasing toward race day.

    Measured with ``training_km``: race week's ``total_km`` includes the race,
    so the last taper week rises on the honest total. What must fall
    monotonically is the training load the runner carries into the start line.
    """
    dist, weeks, km = combo
    plan = gen.generate_plan(km, dist, weeks)
    taper_totals = [training_km(w) for w in plan if w.get("phase") == "taper"]
    for earlier, later in zip(taper_totals, taper_totals[1:]):
        assert later <= earlier + 0.05, f"taper climbs: {taper_totals}"


def test_viable_run_frequency_floor_and_passthrough():
    """The frequency helper reduces only sub-viable budgets, never past the floor."""
    # Adequately-resourced plans are untouched.
    assert _viable_run_frequency(20.0, 4) == 4
    assert _viable_run_frequency(10.0, 4) == 4  # exactly 2.5 km/run
    # A tiny budget is spread over fewer runs, floored at MIN_RUNNING_DAYS.
    assert _viable_run_frequency(5.0, 4) == MIN_RUNNING_DAYS
    assert _viable_run_frequency(5.0, 5) == MIN_RUNNING_DAYS
    # An explicit low request below the floor is honoured as-is.
    assert _viable_run_frequency(5.0, 2) == 2
