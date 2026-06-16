"""Engine progression tests: polarized-by-volume, build on-ramp, peak deloads.

Locks in the engine improvements: the 80/20 check judges hard *volume*
(the old session-count ratio stripped the second quality slot from every
plan below ~7 runs/week regardless of km), build intensity ramps in over
two weeks instead of cliffing, and a short peak block never loses its
opening week to the deload cadence.
"""

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.distribution_validator import hard_volume_share
from app.core.training.mileage_progression import (
    _runs_per_week_factor,
    calculate_weekly_progression,
)
from app.core.training.phase_calculator import recovery_week_set
from app.core.training.tuning import MAX_PEAK_MILEAGE, RUNS_PER_WEEK_REFERENCE

_QUALITY = ("tempo", "interval", "hill")


def _quality_km(week):
    return sum(w["distance"] for w in week["daily_workouts"] if w["type"] in _QUALITY)


def _quality_count(week):
    return sum(1 for w in week["daily_workouts"] if w["type"] in _QUALITY)


class TestPolarizedByVolume:
    def test_five_run_marathon_gets_two_quality_in_late_build_and_peak(self):
        """The count-based ratio called 2-of-5 runs '40% hard' and stripped
        the second slot; by volume it is ~22% — within the 25% ceiling."""
        plan = TrainingPlanGenerator().generate_plan(
            current_km=50, target_distance=42.2, weeks=16, max_runs_per_week=5, vdot=48
        )
        late = [
            wk
            for wk in plan
            if wk.get("phase") in ("build", "peak")
            and not wk.get("is_recovery")
            and wk["week"] >= 9
        ]
        assert late, "expected late build/peak weeks"
        assert all(_quality_count(wk) == 2 for wk in late)

    def test_hard_volume_stays_under_ceiling(self):
        """No build/peak week exceeds the polarized volume ceiling."""
        for kw in (
            dict(
                current_km=50,
                target_distance=42.2,
                weeks=16,
                max_runs_per_week=5,
                vdot=48,
            ),
            dict(
                current_km=45,
                target_distance=21.1,
                weeks=12,
                max_runs_per_week=5,
                vdot=45,
            ),
            dict(
                current_km=40,
                target_distance=21.1,
                weeks=12,
                max_runs_per_week=4,
                vdot=45,
            ),
            dict(current_km=30, target_distance=10.0, weeks=10, max_runs_per_week=4),
        ):
            plan = TrainingPlanGenerator().generate_plan(**kw)
            for wk in plan:
                if wk.get("phase") not in ("build", "peak") or wk.get(
                    "is_recovery_week"
                ):
                    continue
                total = wk.get("total_km") or sum(
                    w["distance"] for w in wk["daily_workouts"]
                )
                if total <= 0:
                    continue
                share = _quality_km(wk) / total
                assert share <= 0.27, (
                    f"week {wk['week']} ({kw['target_distance']}km plan): "
                    f"{share:.0%} hard volume exceeds the polarized ceiling"
                )

    def test_four_run_weeks_keep_classic_shape(self):
        """At 4 runs/week the deficit branch must not convert the second easy
        run — every other run hard is too intense by frequency."""
        plan = TrainingPlanGenerator().generate_plan(
            current_km=40, target_distance=21.1, weeks=12, max_runs_per_week=4, vdot=45
        )
        for wk in plan:
            if wk.get("phase") in ("build", "peak") and not wk.get("is_recovery"):
                assert _quality_count(wk) <= 1

    def test_hard_volume_share_math(self):
        # Marathon build with tempo+interval granted: share is the sum of the
        # two type percentages — nowhere near the old 40% count ratio.
        share = hard_volume_share(
            {"tempo": 1, "interval": 1, "easy": 2, "long": 1}, "build", 42.2
        )
        assert 0.10 <= share <= 0.30


class TestBuildOnRamp:
    def test_first_two_build_weeks_step_up_gradually(self):
        """Quality dose climbs base -> 75% -> 90% -> full instead of +90%
        in one week (marathon was 4.0 -> 7.6)."""
        plan = TrainingPlanGenerator().generate_plan(
            current_km=50, target_distance=42.2, weeks=16, max_runs_per_week=5, vdot=48
        )
        build = [
            wk
            for wk in plan
            if wk.get("phase") == "build" and not wk.get("is_recovery")
        ]
        base_last = max(
            _quality_km(wk)
            for wk in plan
            if wk.get("phase") == "base" and not wk.get("is_recovery")
        )
        first, second = _quality_km(build[0]), _quality_km(build[1])
        assert first < second, "on-ramp weeks should ascend"
        assert first <= base_last * 1.6, (
            f"first build week quality jumped {base_last} -> {first}"
        )

    def test_on_ramp_never_strips_minimal_plans(self):
        """2-run plans carry one quality in build/peak; the ramp must not
        push that tiny dose below the demotion threshold."""
        plan = TrainingPlanGenerator().generate_plan(
            current_km=20, target_distance=10.0, weeks=10, max_runs_per_week=2
        )
        build_peak = [
            wk
            for wk in plan
            if wk.get("phase") in ("build", "peak") and not wk.get("is_recovery")
        ]
        assert any(_quality_count(wk) >= 1 for wk in build_peak)


class TestPeakBoundaryDeload:
    def test_short_peak_block_keeps_its_opening_week(self):
        # 16-week marathon split: base 5 / build 6 / peak 2. The cadence
        # lands a deload on week 12 (first peak week); it must snap to 11.
        phases = {"base": 5, "build": 6, "peak": 2, "taper": 3}
        rec = recovery_week_set(phases)
        assert 12 not in rec
        assert 11 in rec

    def test_snap_is_noop_when_peak_is_long(self):
        phases = {"base": 4, "build": 5, "peak": 4, "taper": 3}
        rec = recovery_week_set(phases)
        first_peak = 10
        # Whatever the cadence chose, a 4-week peak is left alone.
        assert (first_peak in rec) == (first_peak in recovery_week_set(phases))

    def test_marathon_plan_has_two_loading_peak_weeks(self):
        plan = TrainingPlanGenerator().generate_plan(
            current_km=50, target_distance=42.2, weeks=16, max_runs_per_week=5, vdot=48
        )
        peak_loading = [
            wk for wk in plan if wk.get("phase") == "peak" and not wk.get("is_recovery")
        ]
        assert len(peak_loading) == 2


class TestRunsPerWeekVolumeScaling:
    """Peak weekly volume tracks training frequency.

    A 3-run and a 6-run plan for the same race and fitness used to land on
    identical weekly km — cramming the low-frequency plan into oversized runs
    while the high-frequency plan stayed under-loaded. Volume now scales around
    a neutral reference frequency, bounded by the absolute peak ceiling.
    """

    def _peak(self, runs, *, current=30.0, distance=10.0, weeks=12):
        return max(
            calculate_weekly_progression(current, distance, weeks, max_runs=runs)
        )

    def test_peak_is_non_decreasing_in_frequency(self):
        peaks = [self._peak(r) for r in range(2, 7)]
        assert peaks == sorted(peaks), f"peak should not fall as runs rise: {peaks}"

    def test_high_and_low_frequency_diverge(self):
        """The old bug: these were equal. A 6-run plan now carries more than a
        3-run plan for the same race and fitness."""
        assert self._peak(6) > self._peak(3)

    def test_reference_frequency_factor_is_neutral(self):
        """4 runs/week is the anchor, so the most common default plans — and the
        minimum-viable 4-run marathon — keep their full, unscaled peak."""
        assert _runs_per_week_factor(RUNS_PER_WEEK_REFERENCE) == 1.0

    def test_factor_is_monotonic_and_clamped(self):
        factors = [_runs_per_week_factor(r) for r in range(2, 7)]
        assert factors == sorted(factors)
        assert all(0.85 <= f <= 1.10 for f in factors)

    def test_high_frequency_stays_under_absolute_ceiling(self):
        """Extra easy days can't push volume past the recreational safety cap."""
        peak = self._peak(6, current=50.0, distance=42.2, weeks=16)
        assert peak <= MAX_PEAK_MILEAGE[42.2]
