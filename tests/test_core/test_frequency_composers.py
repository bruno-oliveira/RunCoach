"""Tests for the per-frequency composer system.

Validates the structural contracts each composer must uphold:
- slot counts match the stated frequency
- volume percentages sum to ~1.0
- long-run ratios are within the adaptation policy bounds
- quality budgets respect phase rules
- protected slots are declared in the adaptation policy
- validate_week catches violations
"""

import pytest

from app.core.training.frequency import get_composer
from app.domain.frequency import AdaptationPolicy, SlotType, WorkoutSlot

PHASES = ("base", "build", "peak", "taper")
FREQUENCIES = (2, 3, 4, 5, 6)


@pytest.fixture(params=FREQUENCIES)
def composer(request):
    return get_composer(request.param)


class TestRegistry:
    def test_all_frequencies_registered(self):
        for freq in FREQUENCIES:
            c = get_composer(freq)
            assert c.frequency == freq

    def test_invalid_frequency_raises(self):
        with pytest.raises(ValueError, match="No composer for 1"):
            get_composer(1)
        with pytest.raises(ValueError, match="No composer for 7"):
            get_composer(7)


class TestSlotStructure:
    def test_slot_count_matches_frequency(self, composer):
        for phase in PHASES:
            slots = composer.slots(phase)
            assert len(slots) == composer.frequency, (
                f"{composer.__class__.__name__} {phase}: "
                f"expected {composer.frequency} slots, got {len(slots)}"
            )

    def test_volume_percentages_sum_to_one(self, composer):
        for phase in PHASES:
            slots = composer.slots(phase)
            total_pct = sum(s.volume_pct for s in slots)
            assert abs(total_pct - 1.0) < 0.02, (
                f"{composer.__class__.__name__} {phase}: "
                f"volume sums to {total_pct:.3f}, expected ~1.0"
            )

    def test_exactly_one_long_run_per_week(self, composer):
        for phase in PHASES:
            slots = composer.slots(phase)
            long_count = sum(1 for s in slots if s.slot_type == SlotType.LONG)
            assert long_count == 1, (
                f"{composer.__class__.__name__} {phase}: "
                f"expected 1 long run, got {long_count}"
            )

    def test_all_slots_are_workout_slot_instances(self, composer):
        for phase in PHASES:
            for slot in composer.slots(phase):
                assert isinstance(slot, WorkoutSlot)


class TestLongRunRatios:
    def test_ratios_are_valid_ranges(self, composer):
        for phase in PHASES:
            lo, hi = composer.long_run_pct(phase)
            assert 0.0 < lo < 1.0
            assert 0.0 < hi < 1.0
            assert lo <= hi, (
                f"{composer.__class__.__name__} {phase}: min {lo} > max {hi}"
            )

    def test_ratios_within_adaptation_bounds(self, composer):
        policy = composer.adaptation_policy()
        for phase in PHASES:
            lo, hi = composer.long_run_pct(phase)
            assert lo >= policy.long_run_pct_floor - 0.05, (
                f"{composer.__class__.__name__} {phase}: "
                f"min ratio {lo} below policy floor {policy.long_run_pct_floor}"
            )
            assert hi <= policy.long_run_pct_cap + 0.05, (
                f"{composer.__class__.__name__} {phase}: "
                f"max ratio {hi} above policy cap {policy.long_run_pct_cap}"
            )

    def test_higher_frequency_has_lower_long_run_share(self):
        """Consensus principle: long-run % decreases as frequency increases."""
        for phase in ("build", "peak"):
            prev_hi = 1.0
            for freq in FREQUENCIES:
                c = get_composer(freq)
                _, hi = c.long_run_pct(phase)
                assert hi <= prev_hi + 0.02, (
                    f"freq {freq} {phase}: max long-run pct {hi} >= "
                    f"prev freq's {prev_hi}"
                )
                prev_hi = hi


class TestQualityBudget:
    def test_base_has_zero_quality(self, composer):
        assert composer.quality_budget("base") == 0

    def test_build_peak_have_quality(self, composer):
        if composer.frequency >= 4:
            assert composer.quality_budget("build") >= 1
            assert composer.quality_budget("peak") >= 1

    def test_quality_within_policy_bounds(self, composer):
        policy = composer.adaptation_policy()
        for phase in PHASES:
            budget = composer.quality_budget(phase)
            assert budget <= policy.max_quality_count, (
                f"{composer.__class__.__name__} {phase}: "
                f"quality budget {budget} > policy max {policy.max_quality_count}"
            )

    def test_quality_scales_with_frequency(self):
        """Consensus principle: quality sessions scale with frequency."""
        low_freq = get_composer(2)
        high_freq = get_composer(5)
        assert high_freq.quality_budget("build") >= low_freq.quality_budget("build")
        assert high_freq.quality_budget("peak") >= low_freq.quality_budget("peak")


class TestAdaptationPolicy:
    def test_policy_is_valid(self, composer):
        policy = composer.adaptation_policy()
        assert isinstance(policy, AdaptationPolicy)
        assert 0 < policy.long_run_pct_floor < 1
        assert 0 < policy.long_run_pct_cap < 1
        assert policy.long_run_pct_floor <= policy.long_run_pct_cap
        assert policy.min_quality_count <= policy.max_quality_count

    def test_two_run_cannot_go_lower(self):
        c = get_composer(2)
        policy = c.adaptation_policy()
        assert policy.can_suggest_frequency_change is True
        assert policy.frequency_change_direction == 1

    def test_six_run_does_not_suggest_increase(self):
        c = get_composer(6)
        policy = c.adaptation_policy()
        assert policy.can_suggest_frequency_change is False

    def test_recovery_protected_at_six(self):
        c = get_composer(6)
        policy = c.adaptation_policy()
        assert SlotType.RECOVERY in policy.protected_slots


class TestMediumLongRun:
    """Consensus principle: medium-long run appears at 5+ frequency."""

    def test_no_medium_long_below_five(self):
        for freq in (2, 3, 4):
            c = get_composer(freq)
            for phase in PHASES:
                slots = c.slots(phase)
                ml_count = sum(1 for s in slots if s.slot_type == SlotType.MEDIUM_LONG)
                assert ml_count == 0, f"freq {freq} {phase}: has medium-long run"

    def test_medium_long_at_five_plus(self):
        for freq in (5, 6):
            c = get_composer(freq)
            for phase in PHASES:
                slots = c.slots(phase)
                ml_count = sum(1 for s in slots if s.slot_type == SlotType.MEDIUM_LONG)
                assert ml_count == 1, (
                    f"freq {freq} {phase}: expected 1 medium-long, got {ml_count}"
                )

    def test_medium_long_policy_floor_at_five_plus(self):
        for freq in (5, 6):
            c = get_composer(freq)
            policy = c.adaptation_policy()
            assert policy.medium_long_pct_floor is not None
            assert policy.medium_long_pct_floor > 0

    def test_no_medium_long_policy_below_five(self):
        for freq in (2, 3, 4):
            c = get_composer(freq)
            policy = c.adaptation_policy()
            assert policy.medium_long_pct_floor is None


class TestRecoveryRun:
    """Consensus: recovery runs appear at 5+ frequency (here: 6)."""

    def test_recovery_only_at_six(self):
        for freq in (2, 3, 4, 5):
            c = get_composer(freq)
            for phase in PHASES:
                slots = c.slots(phase)
                rec_count = sum(1 for s in slots if s.slot_type == SlotType.RECOVERY)
                assert rec_count == 0, f"freq {freq} {phase}: has recovery run"

    def test_recovery_present_at_six(self):
        c = get_composer(6)
        for phase in PHASES:
            slots = c.slots(phase)
            rec_count = sum(1 for s in slots if s.slot_type == SlotType.RECOVERY)
            assert rec_count == 1, (
                f"six_run {phase}: expected 1 recovery, got {rec_count}"
            )

    def test_recovery_is_protected_at_six(self):
        c = get_composer(6)
        for phase in PHASES:
            slots = c.slots(phase)
            rec = next(s for s in slots if s.slot_type == SlotType.RECOVERY)
            assert rec.is_protected is True


class TestValidateWeek:
    def test_valid_week_returns_empty(self, composer):
        n = composer.frequency
        distances = [10.0 / n] * n
        types = [s.slot_type.value for s in composer.slots("build")]
        violations = composer.validate_week(distances, types)
        assert violations == []

    def test_empty_week_returns_empty(self, composer):
        assert composer.validate_week([], []) == []

    def test_overloaded_long_run_detected(self):
        c = get_composer(4)
        distances = [2.0, 2.0, 2.0, 40.0]
        types = ["easy", "quality", "easy", "long"]
        violations = c.validate_week(distances, types)
        assert len(violations) >= 1
        assert "Long run" in violations[0]

    def test_six_run_missing_recovery_detected(self):
        c = get_composer(6)
        distances = [5.0] * 6
        types = ["easy", "quality", "easy", "quality", "medium_long", "long"]
        violations = c.validate_week(distances, types)
        assert any("recovery" in v.lower() for v in violations)


# ---------------------------------------------------------------------------
# Phase 2 integration tests: verify the wiring produces structurally
# different plans at different frequencies.
# ---------------------------------------------------------------------------


def _week_types(week: dict) -> list[str]:
    """Extract the non-rest workout types from a week."""
    return [
        w["type"]
        for w in week.get("daily_workouts", [])
        if w.get("type") not in ("rest", "recovery") and w.get("distance", 0) > 0
    ]


def _plan_for(runs: int, distance: float = 21.1, km: float = 40, weeks: int = 12):
    from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator

    return TrainingPlanGenerator().generate_plan(
        current_km=km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
    )


class TestPlanStructuralDifferences:
    """Phase 2 exit criterion: structurally different plans at different
    frequencies, not just scaled volumes."""

    def test_two_vs_six_run_different_type_sets(self):
        plan2 = _plan_for(2)
        plan6 = _plan_for(6, km=60)
        types2 = {t for wk in plan2 for t in _week_types(wk)}
        types6 = {t for wk in plan6 for t in _week_types(wk)}
        assert "medium_long" not in types2
        assert "medium_long" in types6

    def test_six_run_has_recovery_slot(self):
        plan6 = _plan_for(6, km=60)
        has_recovery = any(
            any(w.get("type") == "recovery" for w in wk.get("daily_workouts", []))
            for wk in plan6
        )
        assert has_recovery

    def test_long_run_ratio_decreases_with_frequency(self):
        ratios = {}
        for runs in (3, 5):
            plan = _plan_for(runs, km=40 if runs <= 3 else 50)
            build_weeks = [
                wk
                for wk in plan
                if wk.get("phase") == "build" and not wk.get("is_recovery")
            ]
            if not build_weeks:
                continue
            week_ratios = []
            for wk in build_weeks:
                total = wk.get("total_km", 0)
                if total <= 0:
                    continue
                long_d = max(
                    (
                        w.get("distance", 0)
                        for w in wk["daily_workouts"]
                        if w.get("type") == "long"
                    ),
                    default=0,
                )
                week_ratios.append(long_d / total)
            if week_ratios:
                ratios[runs] = sum(week_ratios) / len(week_ratios)
        assert ratios.get(3, 0) > ratios.get(5, 1), (
            f"3-run long-run ratio ({ratios.get(3):.2f}) should exceed "
            f"5-run ({ratios.get(5):.2f})"
        )

    def test_quality_count_scales_with_frequency(self):
        """Higher frequency plans should carry more quality sessions."""

        def _avg_quality(plan):
            build = [
                wk
                for wk in plan
                if wk.get("phase") == "build" and not wk.get("is_recovery")
            ]
            if not build:
                return 0
            counts = []
            for wk in build:
                q = sum(
                    1
                    for w in wk["daily_workouts"]
                    if w.get("type") in ("tempo", "interval", "hill")
                    and w.get("distance", 0) > 0
                )
                counts.append(q)
            return sum(counts) / len(counts)

        plan3 = _plan_for(3, km=30)
        plan5 = _plan_for(5, km=50)
        assert _avg_quality(plan5) > _avg_quality(plan3)

    def test_medium_long_only_at_five_plus(self):
        for runs in (2, 3, 4):
            plan = _plan_for(runs, km=30)
            all_types = {t for wk in plan for t in _week_types(wk)}
            assert "medium_long" not in all_types, (
                f"{runs}-run plan should not have medium_long"
            )
