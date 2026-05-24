"""Tests for the trail Intensive Training Weekend (ITW) feature."""

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training import phase_calculator
from app.core.training.trail_profile import classify_trail


def _gen(distance, gain, weeks=16, current_km=45, terrain=None, enabled=True):
    prof = classify_trail(distance, gain)
    plan = TrainingPlanGenerator().generate_plan(
        current_km,
        distance,
        weeks,
        max_runs_per_week=5,
        trail_profile=prof,
        terrain=terrain,
        intensive_weekend_enabled=enabled,
    )
    return plan, prof


def _peak_end(distance, gain, weeks=16):
    prof = classify_trail(distance, gain)
    phases = phase_calculator.calculate_phases(weeks, distance, trail_profile=prof)
    return phases["base"] + phases["build"] + phases["peak"], phases, prof


class TestIsIntensiveWeekend:
    def test_fires_on_last_peak_week_for_ultra(self):
        peak_end, phases, prof = _peak_end(55.0, 2800.0)
        assert phase_calculator.is_intensive_weekend(peak_end, "peak", phases, prof)

    def test_not_for_short_bracket(self):
        peak_end, phases, prof = _peak_end(15.0, 400.0, weeks=12)
        assert not phase_calculator.is_intensive_weekend(peak_end, "peak", phases, prof)

    def test_not_for_road(self):
        phases = phase_calculator.calculate_phases(16, 42.2)
        peak_end = phases["base"] + phases["build"] + phases["peak"]
        assert not phase_calculator.is_intensive_weekend(peak_end, "peak", phases, None)

    def test_not_in_base_phase(self):
        _, phases, prof = _peak_end(55.0, 2800.0)
        assert not phase_calculator.is_intensive_weekend(1, "base", phases, prof)


class TestITWGeneration:
    def test_enabled_produces_exactly_one_itw_week(self):
        plan, _ = _gen(55.0, 2800.0)
        assert len([w for w in plan if w.get("intensive_weekend")]) == 1

    def test_disabled_produces_no_itw_week(self):
        plan, _ = _gen(55.0, 2800.0, enabled=False)
        assert [w for w in plan if w.get("intensive_weekend")] == []

    def test_weekend_is_quality_then_long(self):
        plan, _ = _gen(55.0, 2800.0)
        week = next(w for w in plan if w.get("intensive_weekend"))
        sat = next(d for d in week["daily_workouts"] if d["day"] == 6)
        sun = next(d for d in week["daily_workouts"] if d["day"] == 7)
        assert sat["itw_role"] == "quality" and sat.get("key_workout_id")
        assert sun["itw_role"] == "long2" and sun.get("key_workout_id")
        assert sat["type"] in ("interval", "hill")
        assert sun["type"] == "long"
        # The long sits on legs fatigued by the quality session: Sun > Sat.
        assert sun["distance"] > sat["distance"] > 0

    def test_hilly_ultra_uses_hike_run_long(self):
        plan, _ = _gen(55.0, 2800.0)
        week = next(w for w in plan if w.get("intensive_weekend"))
        sun = next(d for d in week["daily_workouts"] if d["day"] == 7)
        assert sun["key_workout_id"] == "trail_hike_run_long"

    def test_flat_ultra_uses_pyramid_and_back_to_back(self):
        plan, _ = _gen(55.0, 300.0, terrain="flat")
        week = next(w for w in plan if w.get("intensive_weekend"))
        sat = next(d for d in week["daily_workouts"] if d["day"] == 6)
        sun = next(d for d in week["daily_workouts"] if d["day"] == 7)
        assert sat["key_workout_id"] in (
            "trail_pyramid_intervals",
            "trail_ladder_intervals",
        )
        assert sun["key_workout_id"] == "trail_b2b_day2"

    def test_short_bracket_never_gets_itw(self):
        plan, _ = _gen(15.0, 400.0, weeks=12, current_km=30)
        assert [w for w in plan if w.get("intensive_weekend")] == []

    def test_standard_bracket_gets_back_to_back_long(self):
        plan, _ = _gen(32.0, 600.0)
        week = next(w for w in plan if w.get("intensive_weekend"))
        sun = next(d for d in week["daily_workouts"] if d["day"] == 7)
        assert sun["key_workout_id"] == "trail_b2b_day2"
