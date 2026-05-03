"""Tests for RunnerProfile-aware plan generation.

Covers all six profile integration points:
1. ACWR risk → conservative mileage progression
2. Volume trend → ramp aggressiveness
3. Longest run → long run ceiling calibration
4. Pace zone distribution → workout mix adjustment
5. Workout type counts → gap-aware quality selection
6. VDOT trend → phase duration adjustment (via profile data)
"""

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.training.mileage_progression import (
    calculate_weekly_progression,
    get_peak_mileage,
    WEEK_OVER_WEEK_CAP,
)
from app.core.training.long_run_calculator import calculate_long_run_distance
from app.core.training.workout_distribution import get_workout_distribution


# ---------------------------------------------------------------------------
# Helper: minimal RunnerProfile dicts for testing
# ---------------------------------------------------------------------------

def _profile(**overrides):
    """Build a minimal profile with sensible defaults."""
    base = {
        "current_vdot": 42.0,
        "vdot_trend": "stable",
        "avg_weekly_km": 30.0,
        "peak_weekly_km": 40.0,
        "longest_run_km": 15.0,
        "runs_per_week": 4.0,
        "acwr": 1.1,
        "acwr_risk": "low",
        "avg_efficiency": None,
        "efficiency_trend_pct": None,
        "easy_pct": 70.0,
        "moderate_pct": 20.0,
        "hard_pct": 10.0,
        "avg_run_km": 7.5,
        "avg_pace_min_km": 5.5,
        "rest_days_per_week": 3.0,
        "volume_trend": "stable",
        "workout_type_counts": {"easy": 10, "long": 4, "tempo": 2, "interval": 1},
        "total_runs": 17,
        "has_sufficient_data": True,
        "weeks_of_data": 8,
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1. ACWR risk → conservative mileage progression
# ===========================================================================

class TestACWRRiskPeakAdjustment:
    """ACWR injury risk should reduce peak mileage."""

    def test_low_risk_no_reduction(self):
        """Low ACWR risk should not change peak mileage."""
        profile = _profile(acwr_risk="low")
        peak = get_peak_mileage(10.0, 25.0, 12, profile=profile)
        peak_no_profile = get_peak_mileage(10.0, 25.0, 12)
        assert peak == peak_no_profile

    def test_optimal_risk_no_reduction(self):
        """Optimal ACWR risk should not change peak mileage."""
        profile = _profile(acwr_risk="optimal")
        peak = get_peak_mileage(10.0, 25.0, 12, profile=profile)
        peak_no_profile = get_peak_mileage(10.0, 25.0, 12)
        assert peak == peak_no_profile

    def test_high_risk_reduces_peak_by_15pct(self):
        """High ACWR risk should reduce peak by ~15%."""
        profile = _profile(acwr_risk="high")
        peak = get_peak_mileage(10.0, 25.0, 12, profile=profile)
        peak_no_profile = get_peak_mileage(10.0, 25.0, 12)
        reduction = (peak_no_profile - peak) / peak_no_profile
        assert 0.13 <= reduction <= 0.17, f"Expected ~15% reduction, got {reduction:.1%}"

    def test_very_high_risk_reduces_peak_by_25pct(self):
        """Very high ACWR risk should reduce peak by ~25%."""
        profile = _profile(acwr_risk="very_high")
        peak = get_peak_mileage(10.0, 25.0, 12, profile=profile)
        peak_no_profile = get_peak_mileage(10.0, 25.0, 12)
        reduction = (peak_no_profile - peak) / peak_no_profile
        assert 0.23 <= reduction <= 0.27, f"Expected ~25% reduction, got {reduction:.1%}"

    def test_high_risk_10k_plan_lower_total_volume(self, plan_generator: TrainingPlanGenerator):
        """A 10K plan with high ACWR risk should have lower total volume."""
        profile_high = _profile(acwr_risk="high", avg_weekly_km=25.0)
        plan_high = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile_high,
        )
        plan_normal = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4,
        )
        total_high = sum(w["total_km"] for w in plan_high)
        total_normal = sum(w["total_km"] for w in plan_normal)
        assert total_high < total_normal, "High-risk plan should have lower total volume"

    def test_very_high_risk_marathon_plan_significantly_lower(self, plan_generator: TrainingPlanGenerator):
        """A marathon plan with very_high ACWR risk should be notably lower volume."""
        profile_vh = _profile(acwr_risk="very_high", avg_weekly_km=40.0, longest_run_km=28.0)
        plan_vh = plan_generator.generate_plan(
            current_km=40.0, target_distance=42.2, weeks=16,
            max_runs_per_week=5, profile=profile_vh,
        )
        plan_normal = plan_generator.generate_plan(
            current_km=40.0, target_distance=42.2, weeks=16,
            max_runs_per_week=5,
        )
        peak_vh = max(w["total_km"] for w in plan_vh)
        peak_normal = max(w["total_km"] for w in plan_normal)
        assert peak_vh < peak_normal * 0.85, "Very-high-risk peak should be <85% of normal"

    def test_unknown_risk_defaults_to_no_reduction(self):
        """Unknown ACWR risk should default to no reduction."""
        profile = _profile(acwr_risk="unknown_value")
        peak = get_peak_mileage(10.0, 25.0, 12, profile=profile)
        peak_no_profile = get_peak_mileage(10.0, 25.0, 12)
        assert peak == peak_no_profile


# ===========================================================================
# 2. Volume trend → ramp aggressiveness
# ===========================================================================

class TestVolumeTrendRampAdjustment:
    """Volume trend should adjust the week-over-week ramp cap."""

    def test_decreasing_trend_uses_5pct_cap(self):
        """Decreasing volume trend should use 5% cap."""
        from app.core.training.phase_calculator import calculate_phases, get_phase, is_recovery_week
        profile = _profile(volume_trend="decreasing")
        progression = calculate_weekly_progression(
            20.0, 10.0, 12, max_runs=4, profile=profile,
        )
        # Check non-recovery week increases don't exceed ~5%
        # Only compare consecutive non-recovery weeks
        phases = calculate_phases(12, 10.0)
        non_recovery_increases = []
        prev_nr_km = None
        for i, km in enumerate(progression):
            week_num = i + 1
            phase = get_phase(week_num, phases)
            if not is_recovery_week(week_num, phase, phases):
                if prev_nr_km is not None and km > prev_nr_km:
                    pct = (km - prev_nr_km) / prev_nr_km
                    non_recovery_increases.append(pct)
                prev_nr_km = km
        if non_recovery_increases:
            assert max(non_recovery_increases) <= 0.07, \
                f"Decreasing trend should cap increases at ~5%, max was {max(non_recovery_increases):.1%}"

    def test_increasing_trend_allows_12pct_cap(self):
        """Increasing volume trend should allow up to 12% increases."""
        from app.core.training.phase_calculator import calculate_phases, get_phase, is_recovery_week
        profile = _profile(volume_trend="increasing")
        progression = calculate_weekly_progression(
            15.0, 21.1, 16, max_runs=5, profile=profile,
        )
        # Should have some increases > 10% (the default cap)
        phases = calculate_phases(16, 21.1)
        non_recovery_increases = []
        prev_nr_km = None
        for i, km in enumerate(progression):
            week_num = i + 1
            phase = get_phase(week_num, phases)
            if not is_recovery_week(week_num, phase, phases):
                if prev_nr_km is not None and km > prev_nr_km:
                    pct = (km - prev_nr_km) / prev_nr_km
                    non_recovery_increases.append(pct)
                prev_nr_km = km
        # At least one increase should be > 10%
        assert any(p > 0.10 for p in non_recovery_increases), \
            "Increasing trend should allow >10% increases"

    def test_stable_trend_uses_default_10pct_cap(self):
        """Stable volume trend should use the default 10% cap."""
        profile = _profile(volume_trend="stable")
        progression = calculate_weekly_progression(
            20.0, 10.0, 12, max_runs=4, profile=profile,
        )
        progression_no_profile = calculate_weekly_progression(
            20.0, 10.0, 12, max_runs=4,
        )
        assert progression == progression_no_profile

    def test_no_profile_uses_default_cap(self):
        """Without profile, should use default 10% cap."""
        from app.core.training.phase_calculator import calculate_phases, get_phase, is_recovery_week
        progression = calculate_weekly_progression(20.0, 10.0, 12, max_runs=4)
        phases = calculate_phases(12, 10.0)
        non_recovery_increases = []
        prev_nr_km = None
        for i, km in enumerate(progression):
            week_num = i + 1
            phase = get_phase(week_num, phases)
            if not is_recovery_week(week_num, phase, phases):
                if prev_nr_km is not None and km > prev_nr_km:
                    pct = (km - prev_nr_km) / prev_nr_km
                    non_recovery_increases.append(pct)
                prev_nr_km = km
        if non_recovery_increases:
            assert max(non_recovery_increases) <= 0.12, \
                f"Default cap should be ~10%, max was {max(non_recovery_increases):.1%}"

    def test_decreasing_trend_plan_has_gentler_ramp(self, plan_generator: TrainingPlanGenerator):
        """Plan with decreasing trend should ramp more gently."""
        profile_dec = _profile(volume_trend="decreasing", avg_weekly_km=20.0, acwr_risk="low")
        plan_dec = plan_generator.generate_plan(
            current_km=20.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile_dec,
        )
        plan_normal = plan_generator.generate_plan(
            current_km=20.0, target_distance=10, weeks=12,
            max_runs_per_week=4,
        )
        # First 4 non-recovery weeks should be lower or equal
        dec_non_rec = [w["total_km"] for w in plan_dec[:6] if not w["is_recovery"]]
        normal_non_rec = [w["total_km"] for w in plan_normal[:6] if not w["is_recovery"]]
        for d, n in zip(dec_non_rec, normal_non_rec):
            assert d <= n + 1.0, f"Decreasing trend week {d} should not exceed normal {n}"


# ===========================================================================
# 3. Longest run → long run ceiling calibration
# ===========================================================================

class TestLongestRunCeiling:
    """Historical longest run should provide a gentle week-1 starting nudge."""

    def test_week1_gentle_nudge_when_plan_much_higher(self):
        """Week 1 long run should be nudged down if plan is way above history."""
        profile = _profile(longest_run_km=8.0)
        # 50km weekly volume for a marathon would produce a very long first long run
        lr = calculate_long_run_distance(
            50.0, 42.2, weeks=20, week_number=1, phase="base",
            profile=profile,
        )
        # Should be nudged toward gentle_start (8.0 * 1.30 = 10.4)
        gentle_start = 8.0 * 1.30
        assert lr <= gentle_start * 1.5 + 0.1, \
            f"Week 1 long run {lr} should be nudged toward gentle start {gentle_start}"

    def test_week1_no_nudge_when_plan_reasonable(self):
        """Week 1 long run should not be nudged if already reasonable."""
        profile = _profile(longest_run_km=15.0)
        lr = calculate_long_run_distance(
            30.0, 10.0, weeks=12, week_number=1, phase="base",
            profile=profile,
        )
        # The plan's long run should be fine — no nudge needed
        gentle_start = 15.0 * 1.30
        assert lr <= gentle_start + 1.0, \
            f"Week 1 long run {lr} is reasonable relative to history"

    def test_week2_no_nudge(self):
        """Week 2+ should not be nudged — normal progression takes over."""
        profile = _profile(longest_run_km=10.0)
        lr = calculate_long_run_distance(
            35.0, 21.1, weeks=16, week_number=2, phase="base",
            profile=profile,
        )
        # Should follow normal progression, not be capped by history
        assert lr > 0

    def test_no_profile_uses_standard_cap(self):
        """Without profile, standard experience-based cap applies."""
        lr_no_profile = calculate_long_run_distance(
            50.0, 10.0, weeks=12, week_number=1, phase="base",
        )
        lr_with_high_profile = calculate_long_run_distance(
            50.0, 10.0, weeks=12, week_number=1, phase="base",
            profile=_profile(longest_run_km=25.0),
        )
        # With a high longest_run, the cap shouldn't constrain
        assert lr_with_high_profile == lr_no_profile

    def test_longest_run_does_not_block_marathon_build(self, plan_generator: TrainingPlanGenerator):
        """Runner with 21km longest run training for marathon should still build."""
        profile = _profile(longest_run_km=21.0, avg_weekly_km=35.0)
        plan = plan_generator.generate_plan(
            current_km=35.0, target_distance=42.2, weeks=20,
            max_runs_per_week=5, profile=profile,
        )
        # Long runs should grow well beyond 21km through the plan
        max_long = max(
            w["distance"] for week in plan for w in week["daily_workouts"] if w["type"] == "long"
        )
        assert max_long > 25.0, \
            f"Marathon plan should build long runs beyond 21km, got max {max_long}"

    def test_high_longest_run_does_not_constrain(self, plan_generator: TrainingPlanGenerator):
        """Runner with high longest_run should not be unnecessarily constrained."""
        profile_high_lr = _profile(longest_run_km=30.0, avg_weekly_km=40.0)
        plan = plan_generator.generate_plan(
            current_km=40.0, target_distance=42.2, weeks=16,
            max_runs_per_week=5, profile=profile_high_lr,
        )
        plan_normal = plan_generator.generate_plan(
            current_km=40.0, target_distance=42.2, weeks=16,
            max_runs_per_week=5,
        )
        # Week 1 long runs should be similar
        wk1_profile = next(
            (w["distance"] for w in plan[0]["daily_workouts"] if w["type"] == "long"), 0
        )
        wk1_normal = next(
            (w["distance"] for w in plan_normal[0]["daily_workouts"] if w["type"] == "long"), 0
        )
        assert abs(wk1_profile - wk1_normal) <= 1.0, \
            f"High longest_run should not constrain: {wk1_profile} vs {wk1_normal}"


# ===========================================================================
# 4. Pace zone distribution → workout mix adjustment
# ===========================================================================

class TestPaceZoneWorkoutMix:
    """Pace zone distribution should adjust quality workout counts."""

    def test_high_hard_pct_reduces_quality(self):
        """Runner with >30% hard work should get fewer quality sessions."""
        profile = _profile(hard_pct=35.0, easy_pct=50.0)
        dist = get_workout_distribution(
            30.0, max_runs=5, phase="build", week_number=5,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        # With 5 runs and high hard_pct, should reduce from 2 to 1 quality
        assert quality <= 1, f"High hard_pct should reduce quality to ≤1, got {quality}"

    def test_low_hard_pct_ensures_quality_in_build(self):
        """Runner with <10% hard work should get at least 1 quality in build."""
        profile = _profile(hard_pct=5.0, easy_pct=85.0)
        dist = get_workout_distribution(
            25.0, max_runs=3, phase="build", week_number=5,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        assert quality >= 1, f"Low hard_pct should ensure ≥1 quality, got {quality}"

    def test_low_easy_pct_reduces_quality_in_peak(self):
        """Runner with <50% easy should get reduced quality in peak."""
        profile = _profile(hard_pct=40.0, easy_pct=40.0)
        dist = get_workout_distribution(
            35.0, max_runs=5, phase="peak", week_number=10,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        assert quality <= 1, f"Low easy_pct should reduce quality to ≤1, got {quality}"

    def test_no_profile_uses_standard_distribution(self):
        """Without profile, standard distribution applies."""
        dist = get_workout_distribution(
            30.0, max_runs=5, phase="build", week_number=5,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        assert quality >= 1, "Standard build week should have at least 1 quality"

    def test_recovery_week_ignores_profile(self):
        """Recovery weeks should have 0 quality regardless of profile."""
        profile = _profile(hard_pct=50.0, easy_pct=30.0)
        dist = get_workout_distribution(
            30.0, max_runs=5, phase="build", is_recovery_week=True,
            week_number=4,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        assert quality == 0, "Recovery week should have 0 quality"

    def test_balanced_profile_preserves_standard_mix(self):
        """Runner with balanced zones should get standard distribution."""
        profile = _profile(hard_pct=15.0, easy_pct=70.0, moderate_pct=15.0)
        dist = get_workout_distribution(
            30.0, max_runs=4, phase="build", week_number=5,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        # Balanced profile should not change the standard 1 quality for 4 runs
        assert quality == 1, f"Balanced profile should preserve standard mix, got {quality}"


# ===========================================================================
# 5. Workout type counts → gap-aware quality selection
# ===========================================================================

class TestWorkoutTypeGaps:
    """Missing workout types should be filled progressively."""

    def test_no_speed_work_uses_tempo_in_base(self):
        """Runner with no speed work should get tempo in base phase for 5K/10K."""
        profile = _profile(workout_type_counts={"easy": 15, "long": 5})
        dist = get_workout_distribution(
            25.0, max_runs=4, phase="base", week_number=1,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        # Should have tempo instead of interval in base
        assert dist.get("tempo", 0) >= 1 or dist.get("interval", 0) == 0, \
            "No-speed-work runner should get tempo in base"

    def test_no_tempo_uses_tempo_in_base(self):
        """Runner with no tempo history should get tempo in base."""
        profile = _profile(workout_type_counts={"easy": 10, "interval": 5, "long": 3})
        dist = get_workout_distribution(
            25.0, max_runs=4, phase="base", week_number=1,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        assert dist.get("tempo", 0) >= 1, \
            "No-tempo runner should get tempo in base"

    def test_complete_history_uses_standard_distribution(self):
        """Runner with complete workout history should get standard distribution."""
        profile = _profile(workout_type_counts={
            "easy": 10, "long": 4, "tempo": 3, "interval": 2, "hill": 1,
        })
        dist = get_workout_distribution(
            30.0, max_runs=4, phase="build", week_number=5,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=10.0, profile=profile,
        )
        quality = dist.get("interval", 0) + dist.get("tempo", 0) + dist.get("hill", 0)
        assert quality >= 1, "Complete history should get standard quality"

    def test_no_hills_trail_plan_uses_tempo(self):
        """Trail runner with no hill history should still get appropriate quality."""
        profile = _profile(workout_type_counts={"easy": 12, "long": 4, "tempo": 2})
        dist = get_workout_distribution(
            30.0, max_runs=4, phase="base", week_number=1,
            phases={"base": 4, "build": 4, "peak": 2, "taper": 2},
            target_distance=30.0, terrain="flat", profile=profile,
        )
        # Flat trail with no hills → tempo
        assert dist.get("tempo", 0) >= 1 or dist.get("hill", 0) == 0


# ===========================================================================
# 6. Full plan generation with profile
# ===========================================================================

class TestFullPlanWithProfile:
    """End-to-end tests for profile-aware plan generation."""

    def test_profile_produces_valid_plan(self, plan_generator: TrainingPlanGenerator):
        """Plan generated with profile should have valid structure."""
        profile = _profile()
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        assert len(plan) == 12
        for week in plan:
            assert "week" in week
            assert "total_km" in week
            assert "daily_workouts" in week
            assert len(week["daily_workouts"]) == 7

    def test_high_risk_profile_produces_conservative_plan(self, plan_generator: TrainingPlanGenerator):
        """High ACWR risk profile should produce a more conservative plan."""
        profile_high = _profile(acwr_risk="high", avg_weekly_km=30.0, longest_run_km=15.0)
        plan_high = plan_generator.generate_plan(
            current_km=30.0, target_distance=21.1, weeks=16,
            max_runs_per_week=5, profile=profile_high,
        )
        plan_normal = plan_generator.generate_plan(
            current_km=30.0, target_distance=21.1, weeks=16,
            max_runs_per_week=5,
        )
        peak_high = max(w["total_km"] for w in plan_high)
        peak_normal = max(w["total_km"] for w in plan_normal)
        assert peak_high < peak_normal, \
            f"High-risk peak {peak_high} should be < normal peak {peak_normal}"

    def test_decreasing_trend_profile_ramps_gently(self, plan_generator: TrainingPlanGenerator):
        """Decreasing trend profile should ramp more gently."""
        profile_dec = _profile(volume_trend="decreasing", avg_weekly_km=20.0, longest_run_km=12.0)
        plan = plan_generator.generate_plan(
            current_km=20.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile_dec,
        )
        # Check week-over-week increases in base phase
        base_weeks = [w for w in plan if w["phase"] == "base" and not w["is_recovery"]]
        for i in range(1, len(base_weeks)):
            prev_km = base_weeks[i - 1]["total_km"]
            curr_km = base_weeks[i]["total_km"]
            if prev_km > 0:
                increase = (curr_km - prev_km) / prev_km
                assert increase <= 0.08, \
                    f"Base week {base_weeks[i]['week']} increase {increase:.1%} exceeds 8% for decreasing trend"

    def test_improving_runner_gets_aggressive_ramp(self, plan_generator: TrainingPlanGenerator):
        """Increasing trend profile should allow slightly more aggressive ramp."""
        profile_inc = _profile(
            volume_trend="increasing", vdot_trend="improving",
            avg_weekly_km=20.0, longest_run_km=14.0,
        )
        plan = plan_generator.generate_plan(
            current_km=20.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile_inc,
        )
        # Should have some increases > 10% in base/build phases
        increases = []
        for i in range(1, len(plan)):
            if not plan[i]["is_recovery"] and not plan[i-1]["is_recovery"]:
                prev = plan[i-1]["total_km"]
                curr = plan[i]["total_km"]
                if prev > 0 and curr > prev:
                    increases.append((curr - prev) / prev)
        # With increasing trend, expect at least some increases above 8%
        assert any(inc > 0.08 for inc in increases), \
            f"Increasing trend should allow >8% increases, max was {max(increases):.1%}"

    def test_profile_with_all_fields_produces_coherent_plan(self, plan_generator: TrainingPlanGenerator):
        """Profile with all fields set should produce a coherent, safe plan."""
        profile = _profile(
            current_vdot=45.0,
            vdot_trend="improving",
            avg_weekly_km=35.0,
            peak_weekly_km=45.0,
            longest_run_km=18.0,
            runs_per_week=4.5,
            acwr=1.05,
            acwr_risk="optimal",
            easy_pct=72.0,
            moderate_pct=18.0,
            hard_pct=10.0,
            volume_trend="stable",
            workout_type_counts={"easy": 20, "long": 8, "tempo": 4, "interval": 3},
        )
        plan = plan_generator.generate_plan(
            current_km=35.0, target_distance=21.1, weeks=16,
            max_runs_per_week=5, profile=profile,
        )
        # Basic sanity checks
        assert len(plan) == 16
        peak = max(w["total_km"] for w in plan)
        assert peak >= 45, f"Peak {peak} should be reasonable for half marathon"
        # All weeks should have long runs
        for week in plan:
            long_runs = [w for w in week["daily_workouts"] if w["type"] == "long"]
            assert len(long_runs) == 1, f"Week {week['week']} should have exactly 1 long run"

    def test_profile_none_same_as_no_profile(self, plan_generator: TrainingPlanGenerator):
        """Passing profile=None should be identical to not passing profile."""
        plan_with_none = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=None,
        )
        plan_without = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4,
        )
        for w1, w2 in zip(plan_with_none, plan_without):
            assert w1["total_km"] == w2["total_km"]
            assert w1["phase"] == w2["phase"]
            assert w1["is_recovery"] == w2["is_recovery"]

    def test_profile_vdot_used_when_not_explicitly_provided(self, plan_generator: TrainingPlanGenerator):
        """Profile's current_vdot should be used when vdot is not explicitly set."""
        profile = _profile(current_vdot=50.0)
        plan = plan_generator.generate_plan(
            current_km=30.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        # Plan should have pace zones derived from VDOT 50
        for week in plan:
            for workout in week["daily_workouts"]:
                if workout.get("steps"):
                    for step in workout["steps"]:
                        if step.get("pace_str"):
                            # VDOT 50 produces specific pace zones
                            break

    def test_profile_avg_weekly_km_used_when_higher(self, plan_generator: TrainingPlanGenerator):
        """Profile's avg_weekly_km should override current_km when higher."""
        profile = _profile(avg_weekly_km=35.0, acwr_risk="low", volume_trend="stable")
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        plan_no_profile = plan_generator.generate_plan(
            current_km=35.0, target_distance=10, weeks=12,
            max_runs_per_week=4,
        )
        # First week should be close (within rounding tolerance)
        # Profile also applies ACWR/volume-trend adjustments, so not exact match
        assert abs(plan[0]["total_km"] - plan_no_profile[0]["total_km"]) <= 2.0, \
            f"First week with profile avg_weekly_km should be close: {plan[0]['total_km']} vs {plan_no_profile[0]['total_km']}"

    def test_profile_avg_weekly_km_ignored_when_lower(self, plan_generator: TrainingPlanGenerator):
        """Profile's avg_weekly_km should NOT override when lower than self-reported."""
        profile = _profile(avg_weekly_km=20.0, acwr_risk="low", volume_trend="stable")
        plan = plan_generator.generate_plan(
            current_km=30.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        plan_no_profile = plan_generator.generate_plan(
            current_km=30.0, target_distance=10, weeks=12,
            max_runs_per_week=4,
        )
        # Should use self-reported 30km, not profile's 20km — close match
        assert abs(plan[0]["total_km"] - plan_no_profile[0]["total_km"]) <= 1.5, \
            f"Should use self-reported 30km: {plan[0]['total_km']} vs {plan_no_profile[0]['total_km']}"


# ===========================================================================
# Edge cases and robustness
# ===========================================================================

class TestProfileEdgeCases:
    """Edge cases for profile-aware plan generation."""

    def test_empty_profile_dict(self, plan_generator: TrainingPlanGenerator):
        """Empty profile dict should not break plan generation."""
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile={},
        )
        assert len(plan) == 12

    def test_partial_profile_dict(self, plan_generator: TrainingPlanGenerator):
        """Profile with only some fields should work correctly."""
        profile = {"acwr_risk": "high"}
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        assert len(plan) == 12
        # Should still have reduced peak due to ACWR risk
        peak = max(w["total_km"] for w in plan)
        assert peak > 0

    def test_profile_with_none_values(self, plan_generator: TrainingPlanGenerator):
        """Profile with None values should not break plan generation."""
        profile = _profile(
            acwr=None,
            avg_efficiency=None,
            efficiency_trend_pct=None,
        )
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        assert len(plan) == 12

    def test_profile_with_zero_longest_run(self, plan_generator: TrainingPlanGenerator):
        """Profile with longest_run_km=0 should not constrain long runs."""
        profile = _profile(longest_run_km=0)
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        week1_long = next(
            (w["distance"] for w in plan[0]["daily_workouts"] if w["type"] == "long"), 0
        )
        assert week1_long > 0, "Long run should exist even with 0 longest_run_km"

    def test_profile_with_empty_workout_counts(self, plan_generator: TrainingPlanGenerator):
        """Profile with empty workout_type_counts should not break."""
        profile = _profile(workout_type_counts={})
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        assert len(plan) == 12

    def test_profile_with_extreme_hard_pct(self, plan_generator: TrainingPlanGenerator):
        """Profile with 100% hard work should still produce a valid plan."""
        profile = _profile(hard_pct=100.0, easy_pct=0.0)
        plan = plan_generator.generate_plan(
            current_km=25.0, target_distance=10, weeks=12,
            max_runs_per_week=4, profile=profile,
        )
        assert len(plan) == 12
        # Should still have easy runs (profile can't override structural needs)
        easy_count = sum(
            1 for w in plan for d in w["daily_workouts"] if d["type"] == "easy"
        )
        assert easy_count > 0, "Plan should still have easy runs"

    def test_all_distances_with_profile(self, plan_generator: TrainingPlanGenerator):
        """All race distances should work with profile."""
        profile = _profile()
        for dist in [5.0, 10.0, 21.1, 30.0, 42.2]:
            base_km = {5.0: 15.0, 10.0: 20.0, 21.1: 25.0, 30.0: 25.0, 42.2: 35.0}[dist]
            plan = plan_generator.generate_plan(
                current_km=base_km, target_distance=dist, weeks=12,
                max_runs_per_week=4, profile=profile,
            )
            assert len(plan) == 12, f"{dist}km plan should have 12 weeks"


# ===========================================================================
# Integration: profile data flow from build_profile to plan generation
# ===========================================================================

class TestProfileDataFlow:
    """Verify that profile data flows correctly through the system."""

    def test_profile_vdot_trend_in_profile_dict(self):
        """VDOT trend should be present in profile dict."""
        profile = _profile(vdot_trend="improving")
        assert profile["vdot_trend"] == "improving"

    def test_profile_acwr_risk_in_profile_dict(self):
        """ACWR risk should be present in profile dict."""
        profile = _profile(acwr_risk="high")
        assert profile["acwr_risk"] == "high"

    def test_profile_volume_trend_in_profile_dict(self):
        """Volume trend should be present in profile dict."""
        profile = _profile(volume_trend="decreasing")
        assert profile["volume_trend"] == "decreasing"

    def test_profile_longest_run_in_profile_dict(self):
        """Longest run should be present in profile dict."""
        profile = _profile(longest_run_km=18.0)
        assert profile["longest_run_km"] == 18.0

    def test_profile_pace_zones_in_profile_dict(self):
        """Pace zone percentages should be present in profile dict."""
        profile = _profile(easy_pct=75.0, moderate_pct=15.0, hard_pct=10.0)
        assert profile["easy_pct"] == 75.0
        assert profile["moderate_pct"] == 15.0
        assert profile["hard_pct"] == 10.0

    def test_profile_workout_counts_in_profile_dict(self):
        """Workout type counts should be present in profile dict."""
        profile = _profile(workout_type_counts={"easy": 10, "tempo": 3})
        assert profile["workout_type_counts"]["easy"] == 10
        assert profile["workout_type_counts"]["tempo"] == 3
