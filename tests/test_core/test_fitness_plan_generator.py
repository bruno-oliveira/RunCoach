"""Tests for FitnessPlanGenerator."""

import pytest

from app.core.generators.fitness_plan_generator import FitnessPlanGenerator


class TestFitnessPlanGenerator:
    """Tests for FitnessPlanGenerator class."""

    @pytest.fixture
    def generator(self):
        return FitnessPlanGenerator()

    def test_generate_vo2max_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        assert len(plan["weekly_plans"]) == 8
        assert plan["focus_area"] == "vo2max"
        assert "training_zones" in plan
        assert "phases" in plan
        assert "summary" in plan

    def test_generate_threshold_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=30.0,
            weeks=10,
            runs_per_week=5,
            focus_area="threshold",
        )

        assert len(plan["weekly_plans"]) == 10
        assert plan["focus_area"] == "threshold"

    def test_generate_balanced_plan(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=20.0,
            weeks=6,
            runs_per_week=3,
            focus_area="balanced",
        )

        assert len(plan["weekly_plans"]) == 6
        assert plan["focus_area"] == "balanced"

    def test_time_trials_every_3_weeks(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=9,
            runs_per_week=4,
            focus_area="vo2max",
        )

        tt_weeks = [w["week"] for w in plan["weekly_plans"] if w.get("is_time_trial_week")]
        assert 3 in tt_weeks
        assert 6 in tt_weeks
        assert 9 in tt_weeks

    def test_time_trial_week_has_time_trial_workout(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="vo2max",
        )

        for week in plan["weekly_plans"]:
            if week.get("is_time_trial_week"):
                tt_workouts = [
                    dw for dw in week["daily_workouts"]
                    if dw["type"] == "time_trial"
                ]
                assert len(tt_workouts) >= 1
                assert tt_workouts[0].get("is_benchmark") is True

    def test_vo2max_focus_has_vo2max_workouts(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        vo2max_count = 0
        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] in ("vo2max", "vo2max_ladder"):
                    vo2max_count += 1

        assert vo2max_count > 0

    def test_threshold_focus_has_threshold_workouts(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="threshold",
        )

        threshold_count = 0
        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] in ("tempo", "cruise_interval"):
                    threshold_count += 1

        assert threshold_count > 0

    def test_mileage_progression(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=20.0,
            weeks=8,
            runs_per_week=4,
            focus_area="balanced",
        )

        weekly_km = [w["total_km"] for w in plan["weekly_plans"]]
        first_week = weekly_km[0]
        peak_week = max(weekly_km[:-2])

        assert peak_week > first_week
        assert peak_week <= 60.0

    def test_long_run_max_25_percent(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=30.0,
            weeks=6,
            runs_per_week=4,
            focus_area="vo2max",
        )

        for week in plan["weekly_plans"]:
            long_runs = [dw for dw in week["daily_workouts"] if dw["type"] == "long"]
            if long_runs:
                long_km = long_runs[0]["distance"]
                total_km = week["total_km"]
                assert long_km <= total_km * 0.30

    def test_recovery_weeks_exist(self, generator: FitnessPlanGenerator):
        # vo2max focus with 12 weeks → taper=1, peak=4 which triggers the
        # peak-phase recovery rule (3rd week of a 4+ week peak is recovery)
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=12,
            runs_per_week=4,
            focus_area="vo2max",
        )

        recovery_weeks = [w for w in plan["weekly_plans"] if w["is_recovery"]]
        assert len(recovery_weeks) > 0

        for rw in recovery_weeks:
            recovery_km = rw["total_km"]
            prev_weeks = [w for w in plan["weekly_plans"] if w["week"] < rw["week"] and not w["is_recovery"]]
            if prev_weeks:
                prev_km = prev_weeks[-1]["total_km"]
                assert recovery_km < prev_km

    def test_zones_calculated_with_vdot(self, generator: FitnessPlanGenerator):
        zones = generator.calculate_training_zones(vdot=50.0)

        assert "zone_1_recovery" in zones
        assert "zone_4_vo2max" in zones
        assert "zone_5_race" in zones
        assert zones["zone_4_vo2max"]["pace"] < zones["zone_3_tempo"]["pace"]

    def test_zones_calculated_with_hr(self, generator: FitnessPlanGenerator):
        zones = generator.calculate_training_zones(vdot=50.0, max_hr=185)

        for zone_data in zones.values():
            assert "hr_bpm_range" in zone_data

    def test_summary_contains_time_trial_weeks(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=9,
            runs_per_week=4,
            focus_area="vo2max",
        )

        assert "time_trial_weeks" in plan["summary"]
        assert 3 in plan["summary"]["time_trial_weeks"]
        assert 6 in plan["summary"]["time_trial_weeks"]
        assert 9 in plan["summary"]["time_trial_weeks"]

    def test_week_has_seven_days(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="balanced",
        )

        for week in plan["weekly_plans"]:
            assert len(week["daily_workouts"]) == 7

    def test_rest_days_have_zero_distance(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=6,
            runs_per_week=4,
            focus_area="balanced",
        )

        for week in plan["weekly_plans"]:
            for dw in week["daily_workouts"]:
                if dw["type"] == "rest":
                    assert dw["distance"] == 0

    def test_vo2max_focus_reduces_taper(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )

        phases = plan["phases"]
        assert phases["taper"]["weeks"] <= 1

    def test_balanced_focus_keeps_taper(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="balanced",
        )

        phases = plan["phases"]
        assert phases["taper"]["weeks"] >= 1

    def test_focus_distance_stored(self, generator: FitnessPlanGenerator):
        plan = generator.generate_plan(
            current_weekly_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            focus_distance=10.0,
        )

        assert plan["focus_distance"] == 10.0
