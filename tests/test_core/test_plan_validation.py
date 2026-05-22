"""Regression test harness for plan generation correctness.

Generates plans across a wide matrix of inputs (mileage, runs/week, distance)
and verifies structural invariants that must hold for every generated plan.
This catches regressions in the core algorithm that unit tests on individual
modules would miss — the interaction between mileage progression, workout
allocation, quality caps, and weekly scaling.
"""

import pytest

from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator

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


MIN_RUNS = {5.0: 2, 10.0: 2, 21.1: 3, 30.0: 4, 42.2: 4}


def _valid_combos():
    """Yield (distance, mileage, max_runs) for all *realistic* non-beginner
    combos.

    Respects the same min-runs constraints as the PlanRequest schema
    (half: 3+, trail/marathon: 4+) and additionally filters out combos
    whose base mileage is too thin for the requested runs-per-week count
    — e.g. 5 km/week split across 5 runs produces ~1 km easy runs that
    behave pathologically under the 10 % rule once strides (~0.6 km) are
    included. Those corner cases aren't realistic prescriptions for any
    user, so we don't ask the validator to handle them.
    """
    for distance in SUPPORTED_DISTANCES:
        for mileage in MILEAGES:
            if mileage < MIN_MILEAGE[distance]:
                continue
            min_runs = MIN_RUNS.get(distance, 2)
            for max_runs in RUNS_OPTIONS:
                if max_runs < min_runs:
                    continue
                # Need ≥ 2.5 km of average per-run headroom to keep the
                # easy runs above the strides-included floor (≤ 2 km/run
                # is too thin for any realistic prescription and exposes
                # rounding artefacts in the budget arithmetic).
                if mileage < 2.5 * max_runs:
                    continue
                yield distance, mileage, max_runs


def _week_runs(week):
    """Extract running workouts (non-rest, non-recovery, positive distance)."""
    return [
        w
        for w in week.get("daily_workouts", [])
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
    """No non-recovery week may exceed 12% over the previous non-recovery
    week's actual total. The base rule is 10%; we allow an extra 2% to
    absorb (a) rounding to 0.1 km on per-workout distances and (b) the
    0.6 km of strides occasionally added to easy runs.
    """

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
                assert increase_pct <= 12, (
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
            longs = [
                w
                for w in workouts
                if w.get("type") == "long" and w.get("distance", 0) > 0
            ]
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
    """The long run should be ≤ 55% of weekly volume for 3+ run plans.

    2-run plans are exempt: with only 1 long + 1 quality/easy, the long
    run naturally consumes 60-70% of volume by design.
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_long_run_not_dominant(self, combo):
        distance, mileage, max_runs = combo
        if max_runs <= 2:
            return
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
            longs = [
                w
                for w in workouts
                if w.get("type") == "long" and w.get("distance", 0) > 0
            ]
            if not longs:
                continue
            long_d = longs[0]["distance"]

            for w in workouts:
                if (
                    w.get("type") in ("tempo", "interval", "hill")
                    and w.get("distance", 0) > 0
                ):
                    if w.get("duration_min"):
                        continue
                    assert w["distance"] <= long_d * 0.90, (
                        f"Week {week['week']}: {w['type']} ({w['distance']}km) > "
                        f"90% of long ({long_d}km)"
                    )


class TestWeeklyTotalWithinTolerance:
    """Sum of workout distances must equal the week's reported total_km
    (and stay within tolerance of the planner target).
    Invariant 1: weekly distances sum to a consistent value.
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_total_matches_sum(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            actual_sum = round(
                sum(w.get("distance", 0) for w in week.get("daily_workouts", [])), 1
            )
            reported = round(week.get("total_km", 0), 1)
            assert abs(actual_sum - reported) <= 0.2, (
                f"Week {week['week']}: sum {actual_sum} != total_km {reported}"
            )


class TestStepDistanceMatchesWorkout:
    """The primary running segments of a workout must sum to its reported
    distance. Recovery jogs and walks are inherent to the structure but
    aren't billed against the workout's km budget.

    Invariant 2: segments reconcile to workout distance.

    Key-workout-overlaid sessions are excluded: their structure is
    authored prescriptively (e.g. "6 × 3 min hill") and is allowed to
    diverge from the budget allocation.
    """

    # Strides are a finishing touch (e.g. 6 × 100 m) that aren't billed
    # against the easy-run budget. Excluded for the same reason recovery/
    # walk are.
    PRIMARY_KINDS = {"warmup", "run", "cooldown", "strides"}

    @classmethod
    def _primary_km(cls, steps):
        from app.core.training.workout_steps import _parse_pace_str_to_min_per_km

        total_m = 0.0
        for s in steps:
            if s.get("kind") not in cls.PRIMARY_KINDS:
                continue
            repeat = s.get("repeat", 1) or 1
            if s.get("distance_m"):
                total_m += s["distance_m"] * repeat
            elif s.get("duration_s"):
                pace = _parse_pace_str_to_min_per_km(
                    s.get("pace_str"),
                    s.get("pace_zone"),
                )
                if pace and pace > 0:
                    total_m += (s["duration_s"] / 60.0) / pace * 1000 * repeat
        return total_m / 1000.0

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_step_sum_matches_distance(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            for w in week.get("daily_workouts", []):
                if w.get("type") in ("rest", "recovery"):
                    continue
                if w.get("key_workout_id"):
                    continue
                steps = w.get("steps") or []
                if not steps:
                    continue
                step_km = self._primary_km(steps)
                planned = w.get("distance", 0) or 0
                # Tolerance is type-aware: easy/long are single-segment so
                # match exactly within rounding; tempo is wu+main+cd which
                # is also tight; intervals/hills include prescriptive
                # fixed-structure variants (e.g. "8 × 30 s hill repeats")
                # whose physical volume can't be scaled to fit any budget.
                if w.get("type") in ("easy", "long"):
                    # 0.3 absorbs cumulative rounding from _set_distance
                    # passes (each round-trip can add ±0.05 km).
                    tolerance = 0.3
                elif w.get("type") == "tempo":
                    tolerance = 0.3 + planned * 0.10
                else:
                    tolerance = 0.6 + planned * 0.40
                assert abs(step_km - planned) <= tolerance, (
                    f"Week {week['week']} D{w.get('day')} {w.get('type')}: "
                    f"primary steps {step_km:.2f}km vs workout {planned}km "
                    f"(tol {tolerance:.2f})"
                )


class TestLowBudgetQualityDemotion:
    """When the planner's quality budget falls below the demotion floor,
    the slot becomes an easy run rather than a thin quality session.
    Invariant 3: no thin-stimulus workouts dressed up as quality.
    """

    def test_tiny_budget_has_no_sub_floor_quality(self):
        from app.contexts.plan.generators.weekly_plan_builder import (
            _QUALITY_DEMOTE_THRESHOLD_KM,
        )

        plan, _ = _generate_plan(5.0, 5, 3)
        for week in plan:
            for w in week.get("daily_workouts", []):
                if w.get("type") in ("tempo", "interval", "hill"):
                    assert w.get("distance", 0) >= _QUALITY_DEMOTE_THRESHOLD_KM, (
                        f"Week {week['week']}: {w['type']} at {w['distance']}km "
                        f"below demote floor {_QUALITY_DEMOTE_THRESHOLD_KM}"
                    )


class TestDurationHintBoundary:
    """Sub-3km running workouts get a duration_min hint; longer ones don't.
    Invariant 3: user-facing values include the time the runner will spend.
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_duration_hint_only_below_3km(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            for w in week.get("daily_workouts", []):
                if w.get("type") in ("rest", "recovery", "run_walk"):
                    continue
                d = w.get("distance", 0) or 0
                if d <= 0:
                    continue
                if d < 3.0:
                    assert w.get("duration_min"), (
                        f"Week {week['week']} D{w.get('day')} {w.get('type')} "
                        f"at {d}km should carry duration_min hint"
                    )
                else:
                    assert not w.get("duration_min"), (
                        f"Week {week['week']} D{w.get('day')} {w.get('type')} "
                        f"at {d}km should NOT carry duration_min hint"
                    )
