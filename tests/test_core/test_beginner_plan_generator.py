"""Tests for BeginnerPlanGenerator."""

import pytest

from app.contexts.plan.generators.beginner_plan_generator import (
    BEGINNER_TIPS,
    BeginnerPlanGenerator,
)


@pytest.fixture
def gen():
    return BeginnerPlanGenerator()


class TestBeginnerPlanStructure:
    """Plan length and week numbering."""

    def test_5k_plan_length(self, gen):
        plan = gen.generate_plan(5.0, 10)
        assert len(plan) == 10

    def test_10k_plan_length(self, gen):
        plan = gen.generate_plan(10.0, 10)
        assert len(plan) == 10

    def test_10k_short_plan_length(self, gen):
        plan = gen.generate_plan(10.0, 6)
        assert len(plan) == 6

    def test_week_numbers_sequential(self, gen):
        plan = gen.generate_plan(10.0, 12)
        assert [w["week"] for w in plan] == list(range(1, 13))


class TestBeginnerVs10K:
    """5K and 10K beginner plans must differ structurally."""

    def test_10k_not_identical_to_5k(self, gen):
        p5 = gen.generate_plan(5.0, 10)
        p10 = gen.generate_plan(10.0, 10)
        phases_5 = [w["phase"] for w in p5]
        phases_10 = [w["phase"] for w in p10]
        assert phases_5 != phases_10, "10K plan should have extension phases, not all beginner"

    def test_10k_always_has_extension_weeks(self, gen):
        """Every 10K plan must include at least one non-beginner phase week."""
        for weeks in [6, 8, 10, 12, 16]:
            plan = gen.generate_plan(10.0, weeks)
            phases = {w["phase"] for w in plan}
            assert phases - {"beginner"}, (
                f"10K {weeks}w plan has only beginner phases — no extension weeks"
            )

    def test_5k_plan_all_beginner_phase(self, gen):
        """5K plans (up to 10 weeks) should be entirely C25K (beginner phase)."""
        plan = gen.generate_plan(5.0, 10)
        assert all(w["phase"] == "beginner" for w in plan)

    def test_10k_extension_has_long_run(self, gen):
        plan = gen.generate_plan(10.0, 10)
        extension_weeks = [w for w in plan if w["phase"] != "beginner"]
        assert extension_weeks, "10K plan should have extension weeks"
        for week in extension_weeks:
            types = [d["type"] for d in week["daily_workouts"]]
            assert "long" in types, f"Week {week['week']}: extension week missing long run"

    def test_10k_has_taper_week(self, gen):
        plan = gen.generate_plan(10.0, 10)
        assert plan[-1]["phase"] == "taper"

    def test_10k_taper_reduces_volume(self, gen):
        plan = gen.generate_plan(10.0, 12)
        non_taper = [w for w in plan if w["phase"] != "taper" and w["phase"] != "beginner"]
        taper = [w for w in plan if w["phase"] == "taper"]
        if non_taper and taper:
            peak_km = max(w["total_km"] for w in non_taper)
            assert taper[-1]["total_km"] < peak_km


class TestBeginnerTips:
    """Tips should reference the correct target distance."""

    def test_5k_tips_mention_5k(self, gen):
        plan = gen.generate_plan(5.0, 10)
        late_weeks = [w for w in plan if w["week"] >= 8]
        for week in late_weeks:
            tips = week["training_tips"]
            assert any("5K" in t for t in tips), f"Week {week['week']}: tips should mention 5K"
            assert not any("10K" in t for t in tips), f"Week {week['week']}: 5K tips should not mention 10K"

    def test_10k_tips_mention_10k(self, gen):
        plan = gen.generate_plan(10.0, 12)
        late_weeks = [w for w in plan if w["week"] >= 8]
        for week in late_weeks:
            tips = week["training_tips"]
            assert any("10K" in t for t in tips), f"Week {week['week']}: tips should mention 10K"
            assert not any("5K" in t for t in tips), f"Week {week['week']}: 10K tips should not mention 5K"


class TestC25KCompression:
    """Compressed C25K sequences preserve progression."""

    def test_compressed_preserves_first_week(self, gen):
        """Even short plans should start with week 1 content (the easiest)."""
        plan = gen.generate_plan(10.0, 6)
        first_workout = plan[0]["daily_workouts"][0]
        assert first_workout["run_min"] == 1, "Compressed plan should start from week 1 level"

    def test_compressed_ends_with_continuous_running(self, gen):
        """C25K portion should end with continuous running (walk_min == 0)."""
        plan = gen.generate_plan(10.0, 8)
        c25k_weeks = [w for w in plan if w["phase"] == "beginner"]
        last_c25k = c25k_weeks[-1]
        last_workout = last_c25k["daily_workouts"][0]
        assert last_workout.get("walk_min", 0) == 0, "C25K should end with continuous running"


class TestBeginnerPlanBeginner:
    """All beginner plans have is_beginner_plan flag."""

    def test_all_weeks_flagged(self, gen):
        for dist in [5.0, 10.0]:
            plan = gen.generate_plan(dist, 10)
            for week in plan:
                assert week["is_beginner_plan"] is True

    def test_max_3_runs_per_week(self, gen):
        """Beginner plans cap at 3 runs regardless of max_runs_per_week input."""
        plan = gen.generate_plan(5.0, 10, max_runs_per_week=5)
        for week in plan:
            run_days = len(week["daily_workouts"])
            assert run_days <= 3


class TestIntegrationWithMainGenerator:
    """BeginnerPlanGenerator is invoked via TrainingPlanGenerator for 0km base."""

    def test_zero_km_5k_uses_beginner(self):
        from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(0, 5.0, 10)
        assert plan[0].get("is_beginner_plan") is True

    def test_zero_km_10k_uses_beginner(self):
        from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(0, 10.0, 10)
        assert plan[0].get("is_beginner_plan") is True
        phases = {w["phase"] for w in plan}
        assert phases - {"beginner"}, "10K beginner plan should have extension weeks"
