"""Tests for performance plan day distribution and spacing."""

import pytest
from app.core.generators.performance_plan_generator import PerformancePlanGenerator


class TestPerformancePlanDayDistribution:
    """Verify performance plans have balanced day distribution."""

    @pytest.fixture
    def generator(self):
        return PerformancePlanGenerator()

    def _get_run_days(self, plan):
        """Extract days with runs (non-rest) from a plan."""
        run_days = []
        for week in plan['weekly_plans']:
            for day in week['daily_workouts']:
                if day['type'] != 'rest':
                    run_days.append((week['week'], day['day']))
        return run_days

    def _has_max_consecutive_runs(self, plan, max_consecutive):
        """Check if any week has more than max_consecutive run days."""
        for week in plan['weekly_plans']:
            run_flags = [0] * 8  # index 0 unused, 1-7 = days
            for day in week['daily_workouts']:
                if day['type'] != 'rest':
                    run_flags[day['day']] = 1

            max_streak = 0
            current_streak = 0
            for d in range(1, 8):
                if run_flags[d]:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0

            if max_streak > max_consecutive:
                return True
        return False

    @pytest.mark.parametrize("runs_per_week", [2, 3, 4])
    def test_no_three_consecutive_runs_low_volume(self, generator, runs_per_week):
        """2x, 3x, 4x/week plans should never have 3+ consecutive run days."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=runs_per_week,
        )
        assert not self._has_max_consecutive_runs(plan, 2), \
            f"Found 3+ consecutive runs in {runs_per_week}x/week plan"

    @pytest.mark.parametrize("runs_per_week", [2, 3, 4, 5, 6])
    def test_long_run_on_saturday(self, generator, runs_per_week):
        """Long run should always be on Saturday (day 6)."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=runs_per_week,
        )
        for week in plan['weekly_plans']:
            long_runs = [d for d in week['daily_workouts'] if d['type'] == 'long']
            assert len(long_runs) == 1, f"Expected 1 long run, got {len(long_runs)}"
            assert long_runs[0]['day'] == 6, \
                f"Long run on day {long_runs[0]['day']}, expected 6 (Saturday)"

    @pytest.mark.parametrize("phase", ['base', 'build', 'peak', 'taper'])
    def test_quality_workouts_on_tuesday_thursday(self, generator, phase):
        """Quality workouts should be on Tuesday (2) and Thursday (4) for 4x/week."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=4,
        )
        # Check first non-recovery week of the phase
        for week in plan['weekly_plans']:
            if week['phase'] == phase and not week.get('is_recovery', False):
                quality_days = [
                    d['day'] for d in week['daily_workouts']
                    if d.get('quality', False)
                ]
                assert 2 in quality_days, "Quality workout missing on Tuesday"
                if len(quality_days) >= 2:
                    assert 4 in quality_days, "Second quality workout should be on Thursday"
                break
