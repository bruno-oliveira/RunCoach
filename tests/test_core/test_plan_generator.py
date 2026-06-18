"""Tests for TrainingPlanGenerator."""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training import (
    long_run_calculator,
    mileage_progression,
    phase_calculator,
    workout_distribution,
)


class TestTrainingPlanGenerator:
    """Tests for TrainingPlanGenerator class."""

    def test_weekly_cap_uses_single_constant(self):
        """plan_generator must derive the 10% cap from
        mileage_progression.WEEK_OVER_WEEK_CAP, not hardcoded literals."""
        import inspect

        from app.contexts.plan.generators import plan_generator as pg

        src = inspect.getsource(pg)
        assert "WEEK_OVER_WEEK_CAP" in src, (
            f"{pg.__name__} should reference WEEK_OVER_WEEK_CAP"
        )

    # ------------------------------------------------------------------
    # Basic plan generation per distance
    # ------------------------------------------------------------------

    def test_generate_5k_plan(self, plan_generator: TrainingPlanGenerator):
        """Test generating a 5K training plan."""
        plan = plan_generator.generate_plan(
            current_km=20.0,
            target_distance=5,
            weeks=8,
            max_runs_per_week=4,
        )

        assert len(plan) == 8
        assert all("week" in week for week in plan)
        assert all("total_km" in week for week in plan)
        assert all("daily_workouts" in week for week in plan)
        assert all("phase" in week for week in plan)
        assert all("training_tips" in week for week in plan)

    def test_generate_10k_plan(self, plan_generator: TrainingPlanGenerator):
        """Test generating a 10K training plan."""
        plan = plan_generator.generate_plan(
            current_km=25.0,
            target_distance=10,
            weeks=10,
            max_runs_per_week=4,
        )

        assert len(plan) == 10
        # Verify progressive weekly mileage
        first_week_km = plan[0]["total_km"]
        last_week_km = plan[-2]["total_km"]  # Week before taper
        assert last_week_km >= first_week_km

    def test_generate_half_marathon_plan(self, plan_generator: TrainingPlanGenerator):
        """Test generating a half marathon training plan."""
        plan = plan_generator.generate_plan(
            current_km=30.0,
            target_distance=21.1,
            weeks=12,
            max_runs_per_week=5,
        )

        assert len(plan) == 12

    def test_generate_marathon_plan(self, plan_generator: TrainingPlanGenerator):
        """Test generating a marathon training plan."""
        plan = plan_generator.generate_plan(
            current_km=45.0,
            target_distance=42.2,
            weeks=16,
            max_runs_per_week=5,
        )

        assert len(plan) == 16
        # Marathon plans should have higher peak mileage
        peak_km = max(week["total_km"] for week in plan)
        assert peak_km > 50

    def test_generate_trail_plan(self, plan_generator: TrainingPlanGenerator):
        """Test generating a trail running plan."""
        plan = plan_generator.generate_plan(
            current_km=25.0,
            target_distance=30,
            weeks=10,
            max_runs_per_week=5,
        )

        assert len(plan) == 10
        assert all("week" in week for week in plan)
        assert all("daily_workouts" in week for week in plan)

    # ------------------------------------------------------------------
    # Workout structure and types
    # ------------------------------------------------------------------

    def test_daily_workouts_structure(self, plan_generator: TrainingPlanGenerator):
        """Test that daily workouts have correct structure."""
        plan = plan_generator.generate_plan(
            current_km=20.0,
            target_distance=5,
            weeks=6,
            max_runs_per_week=4,
        )

        for week in plan:
            workouts = week.get("daily_workouts", [])
            assert len(workouts) == 7  # 7 days per week

            for workout in workouts:
                assert "day" in workout
                assert "type" in workout
                assert "distance" in workout or workout["type"] == "rest"
                assert 1 <= workout["day"] <= 7

    def test_workout_types(self, plan_generator: TrainingPlanGenerator):
        """Test that valid workout types are used."""
        plan = plan_generator.generate_plan(
            current_km=30.0,
            target_distance=10,
            weeks=8,
            max_runs_per_week=4,
        )

        valid_types = {
            "easy",
            "long",
            "tempo",
            "interval",
            "rest",
            "hill",
            "strength",
            "recovery",
        }

        for week in plan:
            for workout in week.get("daily_workouts", []):
                assert workout["type"] in valid_types

    def test_phase_in_weekly_plan(self, plan_generator: TrainingPlanGenerator):
        """Each weekly plan should include phase information."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)

        for week in plan:
            assert "phase" in week
            assert week["phase"] in ["base", "build", "peak", "taper"]

    def test_recovery_days_zero_distance(self, plan_generator: TrainingPlanGenerator):
        """Recovery days should always have 0km distance."""
        plan = plan_generator.generate_plan(current_km=20, target_distance=10, weeks=12)

        for week in plan:
            for workout in week["daily_workouts"]:
                if workout["type"] == "recovery":
                    assert workout.get("distance", 0) == 0, (
                        f"Week {week['week']} Day {workout['day']}: Recovery has distance"
                    )

    # ------------------------------------------------------------------
    # Weekly mileage and progression
    # ------------------------------------------------------------------

    def test_weekly_mileage_calculation(self, plan_generator: TrainingPlanGenerator):
        """Actual total distance should match target within 5%."""
        plan = plan_generator.generate_plan(current_km=20, target_distance=10, weeks=12)

        for week in plan:
            target = week["total_km"]
            actual = sum(w.get("distance", 0) for w in week["daily_workouts"])
            diff_pct = abs(actual - target) / target if target > 0 else 0
            assert diff_pct <= 0.05, (
                f"Week {week['week']}: {diff_pct:.1%} difference exceeds 5%"
            )

    def test_taper_week(self, plan_generator: TrainingPlanGenerator):
        """Test that the last week has reduced mileage (taper)."""
        plan = plan_generator.generate_plan(
            current_km=30.0,
            target_distance=10,
            weeks=10,
            max_runs_per_week=4,
        )

        peak_km = max(week["total_km"] for week in plan[:-2])
        final_week_km = plan[-1]["total_km"]
        assert final_week_km < peak_km

    def test_progressive_overload(self, plan_generator: TrainingPlanGenerator):
        """Test that mileage generally increases through the plan."""
        plan = plan_generator.generate_plan(
            current_km=20.0,
            target_distance=21.1,
            weeks=12,
            max_runs_per_week=5,
        )

        first_half = plan[:6]
        second_half = plan[6:-2]  # Exclude taper weeks

        avg_first = sum(w["total_km"] for w in first_half) / len(first_half)
        avg_second = sum(w["total_km"] for w in second_half) / len(second_half)

        assert avg_second > avg_first

    def test_conservative_progression(self, plan_generator: TrainingPlanGenerator):
        """Progressive build weeks within phases should have conservative increases."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)

        volumes = [week["total_km"] for week in plan]
        phases = [week["phase"] for week in plan]

        for i in range(1, len(volumes)):
            if phases[i] != phases[i - 1]:
                continue
            prev_change = (
                (volumes[i - 1] - volumes[i - 2]) / volumes[i - 2] if i > 1 else 0
            )
            if prev_change < -0.20:
                continue
            curr_change = (volumes[i] - volumes[i - 1]) / volumes[i - 1]
            if curr_change > 0:
                assert curr_change <= 0.20, (
                    f"Week {i + 1}: {curr_change:.1%} increase exceeds 20% safety limit"
                )

    def test_peak_mileage_consistent_with_length(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Peak mileage should scale with plan length."""
        plan_8 = plan_generator.generate_plan(
            current_km=10, target_distance=10, weeks=8
        )
        plan_12 = plan_generator.generate_plan(
            current_km=10, target_distance=10, weeks=12
        )
        plan_17 = plan_generator.generate_plan(
            current_km=10, target_distance=10, weeks=17
        )

        peak_8 = max(w["total_km"] for w in plan_8)
        peak_12 = max(w["total_km"] for w in plan_12)
        peak_17 = max(w["total_km"] for w in plan_17)

        assert peak_17 > peak_12 > peak_8, (
            "Peak mileage should increase with longer plans"
        )

    # ------------------------------------------------------------------
    # Phase calculation
    # ------------------------------------------------------------------

    def test_phase_calculation_8_weeks_10k(self, plan_generator: TrainingPlanGenerator):
        """10K 8-week plan: 2-week taper for smoother volume reduction."""
        phases = phase_calculator.calculate_phases(8, target_distance=10.0)
        assert sum(phases.values()) == 8
        assert phases["taper"] == 2
        assert phases["base"] >= 2
        assert phases["build"] >= 2

    def test_phase_calculation_17_weeks_marathon(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Marathon 17-week plan: 3-week taper, longer build."""
        phases = phase_calculator.calculate_phases(17, target_distance=42.2)
        assert sum(phases.values()) == 17
        assert phases["taper"] == 3
        assert phases["build"] >= phases["base"]

    def test_phase_calculation_10_weeks_half(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Half marathon 10-week plan: 2-week taper."""
        phases = phase_calculator.calculate_phases(10, target_distance=21.1)
        assert sum(phases.values()) == 10
        assert phases["taper"] == 2
        assert phases["base"] >= 2
        assert phases["build"] >= 2

    def test_get_phase_base(self, plan_generator: TrainingPlanGenerator):
        phases = {"base": 4, "build": 3, "peak": 1, "taper": 2}
        assert phase_calculator.get_phase(1, phases) == "base"
        assert phase_calculator.get_phase(4, phases) == "base"

    def test_get_phase_build(self, plan_generator: TrainingPlanGenerator):
        phases = {"base": 4, "build": 3, "peak": 1, "taper": 2}
        assert phase_calculator.get_phase(5, phases) == "build"
        assert phase_calculator.get_phase(7, phases) == "build"

    # ------------------------------------------------------------------
    # Recovery weeks and rest-day rules
    # ------------------------------------------------------------------

    def test_recovery_week_pattern(self, plan_generator: TrainingPlanGenerator):
        """Recovery weeks occur at the 5th week within each phase (phase-relative scheduling).

        For a 16-week marathon plan: base=5, build=6. Recovery at the 5th step within each
        phase — global weeks 5 (last base) and 10 (5th build week). Both should show ~20%
        mileage reduction vs the previous week (modern deload depth).
        """
        plan = plan_generator.generate_plan(
            current_km=20,
            target_distance=42.2,
            weeks=16,
            max_runs_per_week=5,
        )

        # Verify plan marks recovery weeks correctly and they show reduced volume
        recovery_indices = [i for i, w in enumerate(plan) if w.get("is_recovery")]
        assert len(recovery_indices) >= 1, (
            "16-week plan should have at least one recovery week"
        )

        for week_idx in recovery_indices:
            if week_idx == 0:
                continue
            recovery_week = plan[week_idx]
            previous_week = plan[week_idx - 1]
            expected_recovery = previous_week["total_km"] * 0.80
            actual_recovery = recovery_week["total_km"]
            tolerance = expected_recovery * 0.15
            assert abs(actual_recovery - expected_recovery) <= tolerance, (
                f"Week {week_idx + 1} marked is_recovery but volume not reduced: "
                f"expected ~{expected_recovery:.1f} km, got {actual_recovery:.1f} km"
            )

        # Taper weeks should also be well below peak
        taper_weeks = plan[-3:]
        peak_km = max(w["total_km"] for w in plan[:-3])
        race_week = taper_weeks[-1]
        assert race_week["total_km"] <= peak_km * 0.8
        assert race_week["total_km"] >= peak_km * 0.3

    def test_long_run_before_rest_day(self, plan_generator: TrainingPlanGenerator):
        """Verify long run is always preceded by rest day."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            schedule = {w["day"]: w["type"] for w in week["daily_workouts"]}
            long_run_day = next((d for d, t in schedule.items() if t == "long"), None)
            if long_run_day:
                assert schedule.get(long_run_day - 1) == "rest", (
                    f"Week {week['week']}: Long run on day {long_run_day} not preceded by rest"
                )

    def test_long_run_after_recovery(self, plan_generator: TrainingPlanGenerator):
        """Verify long run is followed by recovery rest."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            schedule = {w["day"]: w["type"] for w in week["daily_workouts"]}
            long_run_day = next((d for d, t in schedule.items() if t == "long"), None)
            if long_run_day:
                assert schedule.get(long_run_day + 1) in ["rest", "recovery"], (
                    f"Week {week['week']}: Long run on day {long_run_day} not followed by rest/recovery"
                )

    def test_recovery_week_ratio_reduction(self, plan_generator: TrainingPlanGenerator):
        """Recovery weeks genuinely deload the long run and the weekly volume.

        The earlier form of this check compared the long run's *share* of the
        weekly total (long / total). That share is confounded once a week
        carries a substantial prescriptive quality session: recovery weeks drop
        the quality day, so the long run's share of the (smaller) recovery week
        can rise even though the long run itself is deloaded. The real invariant
        is the absolute deload — both the weekly volume and the long run shrink
        in a recovery week — so that is asserted directly here.
        """
        plan = plan_generator.generate_plan(current_km=25, target_distance=30, weeks=12)

        for week_idx in range(1, len(plan)):
            current_week = plan[week_idx]
            prev_week = plan[week_idx - 1]

            if current_week["is_recovery"] and not prev_week["is_recovery"]:
                prev_long = next(
                    (w for w in prev_week["daily_workouts"] if w["type"] == "long"),
                    None,
                )
                curr_long = next(
                    (w for w in current_week["daily_workouts"] if w["type"] == "long"),
                    None,
                )

                assert current_week["total_km"] < prev_week["total_km"], (
                    f"Week {current_week['week']}: recovery week volume "
                    f"({current_week['total_km']}km) not below previous "
                    f"({prev_week['total_km']}km)"
                )

                if prev_long and curr_long and prev_long["distance"] > 0:
                    long_reduction = (
                        prev_long["distance"] - curr_long["distance"]
                    ) / prev_long["distance"]
                    assert 0.03 <= long_reduction <= 0.55, (
                        f"Week {current_week['week']}: long-run deload "
                        f"{long_reduction:.1%} outside expected range"
                    )

    # ------------------------------------------------------------------
    # Workout-type placement rules
    # ------------------------------------------------------------------

    def test_limited_quality_in_base(self, plan_generator: TrainingPlanGenerator):
        """Base phase allows at most 1 light quality session (strides/threshold)."""
        plan = plan_generator.generate_plan(
            current_km=10, target_distance=10, weeks=12, max_runs_per_week=4
        )
        for week in plan:
            if week["phase"] == "base":
                workout_types = [w["type"] for w in week["daily_workouts"]]
                quality_count = sum(
                    1 for t in workout_types if t in ("interval", "tempo", "hill")
                )
                assert quality_count <= 1, (
                    f"Week {week['week']}: base phase has {quality_count} quality workouts (max 1)"
                )

    def test_strength_on_easy_days_only(self, plan_generator: TrainingPlanGenerator):
        """Strength training should only be on easy run days."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            for workout in week["daily_workouts"]:
                if workout.get("strength_session"):
                    assert workout["type"] == "easy", (
                        f"Strength session on {workout['type']} day (should be easy only)"
                    )

    def test_swimming_in_base_build_only(self, plan_generator: TrainingPlanGenerator):
        """Swimming should only be in base/build phases."""
        plan = plan_generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            if week["phase"] in ["peak", "taper"]:
                for workout in week["daily_workouts"]:
                    swimming = workout.get("optional_cross_training", {}).get("type")
                    assert swimming != "swimming_cross_training", (
                        f"Week {week['week']}: Swimming in {week['phase']} phase"
                    )

    # ------------------------------------------------------------------
    # Training enrichments (tips, strength)
    # ------------------------------------------------------------------

    def test_training_tips_included(self, plan_generator: TrainingPlanGenerator):
        """Test that training tips are included in the plan."""
        plan = plan_generator.generate_plan(
            current_km=20.0,
            target_distance=5,
            weeks=6,
            max_runs_per_week=4,
        )
        assert any(week.get("training_tips") for week in plan)

    def test_strength_training_included(self, plan_generator: TrainingPlanGenerator):
        """Test that strength training recommendations are included."""
        plan = plan_generator.generate_plan(
            current_km=25.0,
            target_distance=10,
            weeks=8,
            max_runs_per_week=4,
        )
        assert any(week.get("strength_training") for week in plan)

    # ------------------------------------------------------------------
    # Constraints and edge cases
    # ------------------------------------------------------------------

    def test_10k_race_with_10km_base(self, plan_generator: TrainingPlanGenerator):
        """Regression test for user feedback scenario."""
        plan = plan_generator.generate_plan(
            current_km=10,
            target_distance=10,
            weeks=12,
            max_runs_per_week=4,
        )

        peak_km = max(week["total_km"] for week in plan)
        assert peak_km <= 35, f"Peak mileage {peak_km} too high for 10km base"

        max_long_run = max(
            workout["distance"]
            for week in plan
            for workout in week["daily_workouts"]
            if workout["type"] == "long"
        )
        assert max_long_run <= 15, f"Long run {max_long_run}km too long for 10K race"

        for week in plan:
            run_days = sum(
                1
                for w in week["daily_workouts"]
                if w["type"] not in ["rest", "recovery"]
            )
            assert run_days == 4, f"Week {week['week']} has {run_days} runs, expected 4"

    def test_max_runs_per_week_constraint(self, plan_generator: TrainingPlanGenerator):
        """Test that max_runs_per_week constraint is respected for all values."""
        for max_runs in [3, 4, 5, 6]:
            plan = plan_generator.generate_plan(
                current_km=20.0,
                target_distance=10,
                weeks=8,
                max_runs_per_week=max_runs,
            )
            for week in plan:
                run_days = sum(
                    1
                    for w in week["daily_workouts"]
                    if w["type"] not in ["rest", "recovery"]
                )
                assert run_days == max_runs, (
                    f"Week {week['week']} has {run_days} runs, expected {max_runs}"
                )
                long_runs = sum(
                    1 for w in week["daily_workouts"] if w["type"] == "long"
                )
                assert long_runs >= 1, f"Week {week['week']} has no long run"

    def test_workout_distribution_with_different_max_runs(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Test _get_workout_distribution() with different max_runs values."""
        distribution_3 = workout_distribution.get_workout_distribution(
            10,
            3,
            phase="build",
            week_number=3,
            target_distance=10.0,
        )
        assert distribution_3["long"] == 1
        assert (
            sum(v for k, v in distribution_3.items() if k not in ["rest", "recovery"])
            <= 3
        )

        distribution_4 = workout_distribution.get_workout_distribution(
            10,
            4,
            phase="build",
            week_number=3,
            target_distance=10.0,
        )
        assert distribution_4["long"] == 1
        assert (
            sum(v for k, v in distribution_4.items() if k not in ["rest", "recovery"])
            <= 4
        )

        distribution_6 = workout_distribution.get_workout_distribution(
            10,
            6,
            phase="build",
            week_number=3,
            target_distance=10.0,
        )
        assert distribution_6["long"] == 1
        assert (
            sum(v for k, v in distribution_6.items() if k not in ["rest", "recovery"])
            <= 6
        )

    def test_get_peak_mileage_with_various_bases(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Test _get_peak_mileage() with various base/target combinations."""
        peak_low = mileage_progression.get_peak_mileage(10, 10, 12)
        assert 20 <= peak_low <= 30

        peak_high = mileage_progression.get_peak_mileage(10, 25, 12)
        assert 30 <= peak_high <= 75

        peak_marathon = mileage_progression.get_peak_mileage(42.2, 40, 16)
        assert 80 <= peak_marathon <= 100

    def test_calculate_long_run_distance_caps(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Test _calculate_long_run_distance() respects hard ceilings."""
        assert long_run_calculator.calculate_long_run_distance(50, 5) <= 14
        assert long_run_calculator.calculate_long_run_distance(60, 10) <= 22
        assert long_run_calculator.calculate_long_run_distance(80, 21.1) <= 28
        assert long_run_calculator.calculate_long_run_distance(100, 42.2) <= 38

    # ------------------------------------------------------------------
    # Long run progression and distribution
    # ------------------------------------------------------------------

    def test_long_run_progression(self, plan_generator: TrainingPlanGenerator):
        """Test that long run distances increase progressively through plan."""
        plan = plan_generator.generate_plan(
            current_km=20, target_distance=21.1, weeks=12
        )

        long_runs = []
        for week in plan:
            lr = next((w for w in week["daily_workouts"] if w["type"] == "long"), None)
            if lr:
                long_runs.append(
                    {
                        "week": week["week"],
                        "phase": week["phase"],
                        "is_recovery": week["is_recovery"],
                        "distance": lr["distance"],
                        "ratio": lr["distance"] / week["total_km"],
                    }
                )

        for phase in ["base", "build", "peak"]:
            phase_runs = [
                r for r in long_runs if r["phase"] == phase and not r["is_recovery"]
            ]
            if len(phase_runs) > 1:
                for i in range(1, len(phase_runs)):
                    assert (
                        phase_runs[i]["distance"]
                        >= phase_runs[i - 1]["distance"] * 0.95
                    ), f"Long run decreased in {phase} phase"
                    assert phase_runs[i]["ratio"] >= phase_runs[i - 1]["ratio"] - 0.03

    def test_phase_distance_distribution(self, plan_generator: TrainingPlanGenerator):
        """Verify progressive long run ratios with phase-appropriate ranges."""
        plan = plan_generator.generate_plan(
            current_km=30, target_distance=21.1, weeks=16
        )

        for week in plan:
            phase = week["phase"]
            min_ratio, max_ratio = long_run_calculator.get_long_run_ratio_range(
                phase, 21.1, 16
            )

            long_run = next(
                (w for w in week["daily_workouts"] if w["type"] == "long"), None
            )
            if long_run:
                long_pct = long_run["distance"] / week["total_km"]

                if phase == "taper":
                    tolerance = 0.20
                elif week["is_recovery"]:
                    tolerance = 0.08
                elif phase in ["peak", "build"]:
                    tolerance = 0.12
                else:
                    tolerance = 0.08

                assert long_pct <= max_ratio + tolerance, (
                    f"Week {week['week']} ({phase}): Long run {long_pct:.1%} exceeds maximum {max_ratio:.1%}"
                )
                if phase not in ["peak"]:
                    assert long_pct >= min_ratio - tolerance, (
                        f"Week {week['week']} ({phase}): Long run {long_pct:.1%} below minimum {min_ratio:.1%}"
                    )

    # ------------------------------------------------------------------
    # Improvement verification tests
    # ------------------------------------------------------------------

    def test_base_phase_has_quality_session(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Base phase should have exactly 1 quality session for 4+ run days."""
        plan = plan_generator.generate_plan(
            current_km=25, target_distance=10, weeks=12, max_runs_per_week=4
        )
        base_non_recovery = [
            w for w in plan if w["phase"] == "base" and not w["is_recovery"]
        ]
        assert base_non_recovery, "Plan should have non-recovery base weeks"
        for week in base_non_recovery:
            workout_types = [w["type"] for w in week["daily_workouts"]]
            quality_count = sum(
                1 for t in workout_types if t in ("interval", "tempo", "hill")
            )
            assert quality_count == 1, (
                f"Week {week['week']}: base phase has {quality_count} quality (expected 1)"
            )

    def test_5k_two_week_taper(self, plan_generator: TrainingPlanGenerator):
        """5K/10K plans of 8+ weeks should have 2-week taper."""
        from app.exceptions import InsufficientTimeException

        for dist in [5.0, 10.0]:
            phases = phase_calculator.calculate_phases(8, target_distance=dist)
            assert phases["taper"] == 2, f"{dist}km 8wk should have 2-week taper"
        with pytest.raises(InsufficientTimeException):
            phase_calculator.calculate_phases(4, target_distance=5.0)

    def test_two_run_quality_in_build_peak(self, plan_generator: TrainingPlanGenerator):
        """2-run plans should have 1 quality session in build/peak phases."""
        plan = plan_generator.generate_plan(
            current_km=15,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=2,
        )
        quality_found = False
        for week in plan:
            if week["phase"] in ("build", "peak") and not week["is_recovery"]:
                workout_types = [w["type"] for w in week["daily_workouts"]]
                quality_count = sum(
                    1 for t in workout_types if t in ("interval", "tempo", "hill")
                )
                assert quality_count == 1, (
                    f"Week {week['week']} ({week['phase']}): expected 1 quality, got {quality_count}"
                )
                quality_found = True
        assert quality_found, "Plan should have build/peak weeks with quality"

    def test_low_volume_carries_duration_hint(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Sub-3km easies must carry a duration_min UX hint after the post-build pass."""
        plan = plan_generator.generate_plan(
            current_km=5.0,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=3,
        )
        found_short_easy = False
        for week in plan:
            for workout in week["daily_workouts"]:
                if workout["type"] == "easy" and 0 < workout.get("distance", 0) < 3.0:
                    assert "duration_min" in workout, (
                        f"W{week['week']} D{workout['day']}: short easy should carry duration_min"
                    )
                    assert workout["duration_min"] > 0
                    found_short_easy = True
        assert found_short_easy, "Low-volume plan should have at least one sub-3km easy"

    def test_marathon_adequate_peak_and_long_run(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Marathon plans should reach adequate peak mileage and long run distances."""
        plan = plan_generator.generate_plan(
            current_km=25,
            target_distance=42.2,
            weeks=16,
            max_runs_per_week=4,
        )
        peak_km = max(w["total_km"] for w in plan if not w.get("is_recovery", False))
        assert peak_km >= 45, f"Marathon peak {peak_km}km is too low (need >=45)"
        max_long = max(
            d["distance"]
            for w in plan
            for d in w["daily_workouts"]
            if d["type"] == "long"
        )
        assert max_long >= 25, (
            f"Marathon max long run {max_long}km is too short (need >=25)"
        )

    def test_marathon_has_multiple_peak_weeks(
        self, plan_generator: TrainingPlanGenerator
    ):
        """Marathon plans should have at least 2 peak weeks."""
        phases = phase_calculator.calculate_phases(16, target_distance=42.2)
        assert phases["peak"] >= 2, (
            f"Marathon 16wk has {phases['peak']} peak weeks (need >=2)"
        )
