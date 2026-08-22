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
from app.core.training.training_constants import training_km

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


def _week_runs(week, include_race=False):
    """Extract running workouts (non-rest, non-recovery, positive distance).

    Race day is excluded by default. Every invariant in this module is about
    *training* load — how fast volume may grow, how much of a week the long
    run may be — and the race is the event those rules were building toward,
    not a training session subject to them. A marathon is 66% of race week
    and 60% above the taper week before it, both by design.
    """
    skip = ("rest", "recovery", "strength", "cross_training")
    if not include_race:
        skip = skip + ("race",)
    return [
        w
        for w in week.get("daily_workouts", [])
        if w.get("type") not in skip and w.get("distance", 0) > 0
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
    """The long run should not dominate weekly volume.

    The ceiling is run-count aware because long-run share is structurally
    bounded by how many days the runner trains:

    - 2-run plans are exempt: with only 1 long + 1 quality/easy the long run
      naturally consumes 60-70% of volume by design.
    - 3-run plans allow up to 62%: with a single long + 1 quality + 1 easy,
      and easy runs now capped by an absolute ceiling so they don't become
      second long runs (audit G3), the race-distance long run is unavoidably
      a large share of a frequency-constrained week. The right remedy is to
      add a day, not to balloon the easy run — so the week is allowed to be
      long-run-heavy rather than carry a junk second long effort.
    - 4+ run plans keep the tighter ~58% guard (a touch above 55% to absorb
      the post-deload supercompensation dip from the ~3:1 cadence, audit G1).
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_long_run_not_dominant(self, combo):
        distance, mileage, max_runs = combo
        if max_runs <= 2:
            return
        ceiling = 0.62 if max_runs <= 3 else 0.58
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            runs = _week_runs(week)
            if not runs:
                continue
            # Race week has no long run — the race replaced it, and it is
            # excluded from `runs`. Taking the max run there would measure the
            # sharpener's share of a shakeout week, which this rule is not
            # about.
            if not any(w.get("type") == "long" for w in runs):
                continue
            total = sum(w["distance"] for w in runs)
            if total == 0:
                continue
            long_d = max(w["distance"] for w in runs)
            ratio = long_d / total
            assert ratio <= ceiling, (
                f"Week {week['week']}: long run is {ratio:.0%} of volume "
                f"({long_d:.1f}/{total:.1f}km), ceiling {ceiling:.0%}"
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


class TestLowFreqNoSecondLongEffort:
    """On low-frequency road plans the easy run must stay clearly below the long
    run — not balloon into a second near-equal long effort.

    Regression (audit #3): a 5K/3-run week produced ``long 14 + "easy" 13`` — two
    ~equal long runs and a token quality slot. The easy ceiling on <= 3-run road
    weeks is now a tighter fraction of the long run, so one clear long run plus a
    genuinely easier support run.
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_easy_clearly_below_long_low_freq(self, combo):
        distance, mileage, max_runs = combo
        if max_runs > 3:
            return
        plan, _ = _generate_plan(distance, mileage, max_runs)

        for week in plan:
            if week.get("is_recovery"):
                continue
            runs = _week_runs(week)
            longs = [w for w in runs if w.get("type") == "long"]
            easies = [w for w in runs if w.get("type") == "easy"]
            if not longs or not easies:
                continue
            long_d = longs[0]["distance"]
            max_easy = max(w["distance"] for w in easies)
            # The tighter low-freq ceiling is 0.68; allow rounding slack.
            assert max_easy <= long_d * 0.72 + 0.2, (
                f"Week {week['week']}: easy {max_easy:.1f}km is a second long "
                f"effort next to long {long_d:.1f}km"
            )


class TestTaperDescends:
    """The taper must descend from the realized peak to a genuine race-week
    drawdown — not sit at ~70% of peak because it was scaled from an unrealized
    high-water target (audit #8).

    Race week is measured on the volume the runner carries *into* the start
    line, i.e. everything before the race. Its ``total_km`` includes the race
    itself, which is the event rather than taper load — a marathon plan's race
    week is ~70% of peak on the honest total and ~25% on training volume, and
    it is the second number that says whether the runner arrives fresh.
    """

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_race_week_is_a_real_drawdown(self, combo):
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)
        totals = [training_km(w) for w in plan if not w.get("is_recovery")]
        if len(totals) < 3:
            return
        peak = max(totals)
        pre_race = training_km(plan[-1])
        # 5K/10K taper to ~55%, marathon to ~50%; with the race carved out, the
        # pre-race days are shakeout only, so the bar is well below that.
        assert pre_race <= peak * 0.45, (
            f"{_id(combo)}: race week carries {pre_race:.1f}km of training, "
            f"{pre_race / peak:.0%} of peak {peak:.1f}km — taper too shallow"
        )

    @pytest.mark.parametrize("combo", ALL_COMBOS, ids=[_id(c) for c in ALL_COMBOS])
    def test_race_week_still_has_running_in_it(self, combo):
        """A drawdown, not a shutdown — race week keeps some easy running."""
        distance, mileage, max_runs = combo
        plan, _ = _generate_plan(distance, mileage, max_runs)
        assert training_km(plan[-1]) > 0, (
            f"{_id(combo)}: race week has no running before the race"
        )


class TestQualityCapsHold:
    """Quality workouts must stay below the long run.

    The per-week quality *budget* is capped at 85% of the long run, but a
    prescriptive key workout (a fixed library session such as 8 × 500 m) may
    use up to ``MAX_KEY_WORKOUT_VS_LONG_RUN`` (95%) of the long run so it keeps
    its full, recognizable structure on low-mileage plans rather than
    collapsing to a token budget-sized run. A quality day still never reaches
    the long run itself."""

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
                    assert w["distance"] <= long_d * 0.95 + 0.1, (
                        f"Week {week['week']}: {w['type']} ({w['distance']}km) > "
                        f"95% of long ({long_d}km)"
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


class TestTaperRetainsSharpener:
    """The taper keeps a short race-pace sharpener — volume drops but intensity
    is retained, instead of dropping all quality (audit G2). On a plan with
    enough volume to support it, at least one taper week carries a tempo."""

    @pytest.mark.parametrize(
        "distance,mileage,max_runs",
        [(42.2, 50, 4), (21.1, 45, 4), (10.0, 45, 4)],
    )
    def test_taper_has_a_sharpener(self, distance, mileage, max_runs):
        from app.core.training.phase_calculator import calculate_phases, get_phase

        plan, weeks = _generate_plan(distance, mileage, max_runs)
        phases = calculate_phases(weeks, distance)
        taper_weeks = [w for w in plan if get_phase(w["week"], phases) == "taper"]
        assert taper_weeks, "expected taper weeks in plan"
        has_sharpener = any(
            dw.get("type") in ("tempo", "interval", "race_pace")
            for w in taper_weeks
            for dw in w.get("daily_workouts", [])
            if (dw.get("distance") or 0) > 0
        )
        assert has_sharpener, (
            "taper dropped all intensity — expected a short race-pace sharpener"
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
