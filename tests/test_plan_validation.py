"""Regression test harness for plan generation correctness.

Generates plans across a wide matrix of inputs (mileage, runs/week, distance)
and verifies structural invariants that must hold for every generated plan.
This catches regressions in the core algorithm that unit tests on individual
modules would miss — the interaction between mileage progression, workout
allocation, quality caps, and weekly scaling.
"""

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.constants import SUPPORTED_DISTANCES, DISTANCE_NAMES


# ── Shared fixtures & helpers ──────────────────────────────────────────────

MIN_MILEAGE = {5.0: 5.0, 10.0: 10.0, 21.1: 15.0, 30.0: 15.0, 42.2: 25.0}
DEFAULT_WEEKS = {5.0: 8, 10.0: 10, 21.1: 12, 30.0: 12, 42.2: 16}
MILEAGES = list(range(5, 95, 5))
RUNS_OPTIONS = [2, 3, 4, 5]


def _generate_plan(distance, mileage, max_runs):
    """Generate a plan, returning (plan, weeks) or raising on invalid combo."""
    weeks = DEFAULT_WEEKS[distance]
    gen = TrainingPlanGenerator()
    plan = gen.generate_plan(float(mileage), distance, weeks, max_runs)
    return plan, weeks


def _valid_combos():
    """Yield (distance, mileage, max_runs) for all valid non-beginner combos."""
    for distance in SUPPORTED_DISTANCES:
        for mileage in MILEAGES:
            if mileage < MIN_MILEAGE[distance]:
                continue
            for max_runs in RUNS_OPTIONS:
                yield distance, mileage, max_runs


def _week_runs(week):
    """Extract running workouts (non-rest, non-recovery, positive distance)."""
    return [
        w for w in week.get("daily_workouts", [])
        if w.get("type") not in ("rest", "recovery", "strength", "cross_training")
        and w.get("distance", 0) > 0
    ]


# ── Parametrised test IDs ──────────────────────────────────────────────────

def _id(combo):
    d, m, r = combo
    return f"{DISTANCE_NAMES[d]}-{m}km-{r}runs"


ALL_COMBOS = list(_valid_combos())


# ── Tests ──────────────────────────────────────────────────────────────────

class TestPlanGenerationSucceeds:
    """Every valid input combination must produce a plan without crashing."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_generates_without_error(self, combo):
        distance, mileage, max_runs = combo
        plan, weeks = _generate_plan(distance, mileage, max_runs)
        assert len(plan) == weeks


class TestTenPercentRule:
    """No non-recovery week may exceed 11% over the previous non-recovery
    week's actual total.  We allow 11% (not 10%) to absorb rounding."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_no_excessive_jumps(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)
        high_water = float(mileage)

        for week in plan:
            runs = _week_runs(week)
            total = sum(w["distance"] for w in runs)
            is_recovery = week.get("is_recovery", False)

            if not is_recovery and high_water > 0:
                increase_pct = ((total - high_water) / high_water) * 100
                assert increase_pct <= 11, (
                    f"Week {week['week']}: {increase_pct:.1f}% jump "
                    f"({high_water:.1f} -> {total:.1f}km)"
                )

            if not is_recovery and total > high_water:
                high_water = total


class TestEasyNeverExceedsLongRun:
    """No easy run may be longer than the long run in the same week."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_easy_le_long(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            workouts = week.get("daily_workouts", [])
            longs = [w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]

            for w in workouts:
                if w.get("type") == "easy" and w.get("distance", 0) > 0:
                    assert w["distance"] <= long_d + 0.1, (
                        f"Week {week['week']}: easy ({w['distance']}km) > "
                        f"long ({long_d}km)"
                    )


class TestRunCountRespected:
    """No week should exceed the requested max runs per week."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_max_runs_not_exceeded(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            runs = _week_runs(week)
            assert len(runs) <= max_runs, (
                f"Week {week['week']}: {len(runs)} runs (max {max_runs})"
            )


class TestLongRunDominance:
    """The long run should be ≤ 55% of weekly volume for non-trail plans
    with starting mileage ≥ 15km.  Trail at very low volume is exempt."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_long_run_not_dominant(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            runs = _week_runs(week)
            if not runs:
                continue
            total = sum(w["distance"] for w in runs)
            if total == 0:
                continue
            long_d = max(w["distance"] for w in runs)
            ratio = long_d / total
            assert ratio <= 0.56, (
                f"Week {week['week']}: long run is {ratio:.0%} of volume "
                f"({long_d:.1f}/{total:.1f}km)"
            )


class TestNoZeroDistanceRunningWorkouts:
    """Running workouts (non-rest/recovery) should not have 0 distance,
    except during taper's final week where sub-km runs might be expected."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_no_zero_runners(self, combo):
        distance, mileage, max_runs = combo
        plan, weeks = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            if week["week"] == weeks:
                continue
            for w in week.get("daily_workouts", []):
                if w.get("type") in ("rest", "recovery"):
                    continue
                if w.get("type") in ("easy", "tempo", "interval", "hill", "long"):
                    assert w.get("distance", 0) > 0, (
                        f"Week {week['week']}: {w['type']} has 0 distance"
                    )


class TestQualityCapsHold:
    """Quality workouts should not exceed 90% of the long run (allowing 5%
    rounding slack over the 85% structural cap)."""

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_quality_le_long(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            workouts = week.get("daily_workouts", [])
            longs = [w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]

            for w in workouts:
                if w.get("type") in ("tempo", "interval", "hill") and w.get("distance", 0) > 0:
                    assert w["distance"] <= long_d * 0.90, (
                        f"Week {week['week']}: {w['type']} ({w['distance']}km) > "
                        f"90% of long ({long_d}km)"
                    )
