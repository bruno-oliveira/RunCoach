"""Tests that adaptation respects frequency-specific composer policies.

Phase 3 of the per-frequency composer spec: the adaptive engine must not
push a plan past the structural constraints its composer defines — a 3-run
plan's long run stays below 55%, a 6-run plan's recovery slot is never
removed, and quality count never exceeds the composer's cap.
"""

import pytest

from app.core.training.frequency import get_composer
from app.core.training.frequency.five_run import FiveRunComposer
from app.core.training.frequency.four_run import FourRunComposer
from app.core.training.frequency.six_run import SixRunComposer
from app.core.training.frequency.three_run import ThreeRunComposer


class TestAdaptationPolicyConstraints:
    """Each composer's AdaptationPolicy expresses structural limits."""

    @pytest.mark.parametrize("freq", [2, 3, 4, 5, 6])
    def test_policy_long_run_bounds_are_sensible(self, freq):
        composer = get_composer(freq)
        policy = composer.adaptation_policy()
        assert 0.0 < policy.long_run_pct_floor < policy.long_run_pct_cap <= 1.0

    @pytest.mark.parametrize("freq", [2, 3, 4, 5, 6])
    def test_policy_quality_bounds_are_sensible(self, freq):
        composer = get_composer(freq)
        policy = composer.adaptation_policy()
        assert policy.min_quality_count >= 0
        assert policy.max_quality_count >= policy.min_quality_count

    def test_three_run_long_run_cap(self):
        policy = ThreeRunComposer().adaptation_policy()
        assert policy.long_run_pct_cap == 0.55

    def test_four_run_long_run_cap(self):
        policy = FourRunComposer().adaptation_policy()
        assert policy.long_run_pct_cap == 0.40

    def test_five_run_medium_long_floor(self):
        policy = FiveRunComposer().adaptation_policy()
        assert policy.medium_long_pct_floor == 0.15

    def test_six_run_recovery_protected(self):
        from app.domain.frequency import SlotType

        policy = SixRunComposer().adaptation_policy()
        assert SlotType.RECOVERY in policy.protected_slots

    def test_six_run_quality_cap(self):
        policy = SixRunComposer().adaptation_policy()
        assert policy.max_quality_count == 2

    @pytest.mark.parametrize("freq", [3, 4, 5, 6])
    def test_can_suggest_frequency_increase(self, freq):
        composer = get_composer(freq)
        policy = composer.adaptation_policy()
        if policy.can_suggest_frequency_change:
            assert policy.frequency_change_direction in (1, -1)


class TestEnforceComposerPolicy:
    """_enforce_composer_policy clamps long-run share within policy bounds."""

    def _make_workout(self, workout_type, distance_km):
        class FakeWorkout:
            def __init__(self, wt, d):
                self.workout_type = wt
                self.distance_km = d

        return FakeWorkout(workout_type, distance_km)

    def _make_plan(self, max_runs, composer_name):
        class FakePlan:
            def __init__(self, mr, cn):
                self.max_runs_per_week = mr
                self.frequency_composer = cn
                self.is_trail = False

        return FakePlan(max_runs, composer_name)

    def test_long_run_capped_at_policy_limit(self):
        from app.contexts.plan.adaptation.week_adjuster import _enforce_composer_policy

        plan = self._make_plan(3, "three_run")
        workouts = [
            self._make_workout("easy", 3.0),
            self._make_workout("tempo", 4.0),
            self._make_workout("long", 15.0),  # 68% of 22 km — way above 55% cap
        ]
        _enforce_composer_policy(plan, workouts, "build")
        total = sum(w.distance_km for w in workouts)
        long_share = workouts[2].distance_km / total
        assert long_share <= 0.57, f"long run share {long_share:.2%} exceeds cap"

    def test_long_run_floored_at_policy_limit(self):
        from app.contexts.plan.adaptation.week_adjuster import _enforce_composer_policy

        plan = self._make_plan(3, "three_run")
        workouts = [
            self._make_workout("easy", 12.0),
            self._make_workout("tempo", 8.0),
            self._make_workout("long", 3.0),  # 13% — way below 40% floor
        ]
        _enforce_composer_policy(plan, workouts, "build")
        total = sum(w.distance_km for w in workouts)
        long_share = workouts[2].distance_km / total
        # The floor is 0.35; rounding to 0.1 km granularity can land slightly
        # below the exact ratio, so we check within 0.02 tolerance.
        assert long_share >= 0.33, f"long run share {long_share:.2%} below floor"
        assert workouts[2].distance_km > 3.0, "long run should have grown"

    def test_no_op_when_no_composer(self):
        from app.contexts.plan.adaptation.week_adjuster import _enforce_composer_policy

        plan = self._make_plan(4, None)
        workouts = [
            self._make_workout("easy", 5.0),
            self._make_workout("long", 20.0),
        ]
        _enforce_composer_policy(plan, workouts, "build")
        assert workouts[1].distance_km == 20.0

    def test_no_op_for_trail_plan(self):
        from app.contexts.plan.adaptation.week_adjuster import _enforce_composer_policy

        plan = self._make_plan(4, None)
        plan.is_trail = True
        workouts = [
            self._make_workout("easy", 5.0),
            self._make_workout("long", 20.0),
        ]
        _enforce_composer_policy(plan, workouts, "build")
        assert workouts[1].distance_km == 20.0
