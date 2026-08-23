"""The arithmetic a backyard goal implies.

The profile's job is to turn "24 loops" into the numbers everything else
reads: a rest budget, a loop pace, tier-aware plan constraints, and the ultra
projection the engine periodises against.
"""

import pytest

from app.core.training.backyard_profile import (
    BACKYARD_CORRAL_MINUTES,
    BACKYARD_LOOP_KM,
    MAX_TARGET_LOOPS,
    MIN_TARGET_LOOPS,
    backyard_max_weekly_km,
    backyard_max_weeks,
    backyard_min_runs_per_week,
    backyard_min_weekly_km,
    backyard_min_weeks,
    classify_backyard,
)
from app.core.training.trail_profile import TRAIL_DISTANCE_MAX_KM


class TestTierClassification:
    @pytest.mark.parametrize(
        "loops,tier",
        [
            (6, "first_timer"),
            (11, "first_timer"),
            (12, "day"),
            (17, "day"),
            (18, "night"),
            (29, "night"),
            (30, "multi_day"),
            (48, "multi_day"),
        ],
    )
    def test_tier_boundaries(self, loops, tier):
        assert classify_backyard(loops).tier == tier

    def test_darkness_flags_escalate_with_loop_count(self):
        assert not classify_backyard(8).runs_in_darkness
        assert classify_backyard(14).runs_in_darkness
        assert not classify_backyard(14).crosses_full_night
        assert classify_backyard(24).crosses_full_night
        assert not classify_backyard(24).crosses_two_nights
        assert classify_backyard(36).crosses_two_nights


class TestRestBudget:
    def test_loop_budget_and_turnaround_fill_the_hour(self):
        for loops in (6, 12, 24, 36):
            p = classify_backyard(loops)
            assert p.loop_budget_minutes + p.turnaround_minutes == pytest.approx(
                BACKYARD_CORRAL_MINUTES
            )

    def test_more_ambition_buys_more_rest_and_costs_more_pace(self):
        """Rest is the only place recovery comes from, so it has to grow."""
        first = classify_backyard(8)
        night = classify_backyard(24)
        multi = classify_backyard(36)
        assert first.turnaround_minutes < night.turnaround_minutes
        assert night.turnaround_minutes < multi.turnaround_minutes
        assert first.loop_pace_min_km > night.loop_pace_min_km
        assert night.loop_pace_min_km > multi.loop_pace_min_km

    def test_standard_loop_paces_are_runnable(self):
        for loops in range(MIN_TARGET_LOOPS, MAX_TARGET_LOOPS + 1):
            pace = classify_backyard(loops).loop_pace_min_km
            assert 6.0 < pace < 9.0

    def test_climb_makes_the_same_budget_a_harder_flat_ask(self):
        flat = classify_backyard(24, BACKYARD_LOOP_KM, 0.0)
        hilly = classify_backyard(24, BACKYARD_LOOP_KM, 150.0)
        assert hilly.loop_budget_minutes == flat.loop_budget_minutes
        assert hilly.flat_equivalent_pace_min_km < flat.flat_equivalent_pace_min_km
        assert flat.flat_equivalent_pace_min_km == pytest.approx(flat.loop_pace_min_km)


class TestTotals:
    def test_twenty_four_loops_is_a_hundred_miles(self):
        p = classify_backyard(24)
        assert p.total_distance_km == pytest.approx(160.9, abs=0.1)
        assert p.target_hours == 24


class TestTrailProjection:
    def test_projection_is_clamped_to_the_engine_ceiling(self):
        p = classify_backyard(48)
        assert p.total_distance_km > TRAIL_DISTANCE_MAX_KM
        assert p.equivalent_distance_km == TRAIL_DISTANCE_MAX_KM

    def test_projection_preserves_the_loop_gradient(self):
        """Elevation *class* is a ratio, so scaling must keep m/km intact."""
        p = classify_backyard(40, BACKYARD_LOOP_KM, 200.0)
        projected = p.as_trail_profile()
        assert projected.m_per_km == pytest.approx(p.m_per_km, rel=1e-6)
        assert projected.elevation_class == p.elevation_class

    def test_flat_loop_projects_flat(self):
        assert classify_backyard(24, BACKYARD_LOOP_KM, 0.0).elevation_class == "flat"

    def test_steep_loop_projects_mountainous(self):
        assert (
            classify_backyard(24, BACKYARD_LOOP_KM, 400.0).elevation_class
            == "mountainous"
        )


class TestConstraints:
    def test_weeks_window_widens_with_the_goal(self):
        for smaller, bigger in ((8, 14), (14, 24), (24, 36)):
            a, b = classify_backyard(smaller), classify_backyard(bigger)
            assert backyard_min_weeks(a) < backyard_min_weeks(b)
            assert backyard_max_weeks(a) < backyard_max_weeks(b)

    def test_min_weeks_never_exceeds_max(self):
        for loops in range(MIN_TARGET_LOOPS, MAX_TARGET_LOOPS + 1):
            p = classify_backyard(loops)
            assert backyard_min_weeks(p) < backyard_max_weeks(p)

    def test_runs_per_week_floor_rises_with_the_goal(self):
        assert backyard_min_runs_per_week(classify_backyard(8)) == 3
        assert backyard_min_runs_per_week(classify_backyard(24)) == 5

    def test_base_requirement_scales_with_loops_not_the_clamped_projection(self):
        """36 and 48 loops project to the same distance but are not the same ask."""
        a = classify_backyard(36)
        b = classify_backyard(48)
        assert a.equivalent_distance_km == b.equivalent_distance_km
        assert backyard_min_weekly_km(a) < backyard_min_weekly_km(b)

    def test_hilly_loop_raises_the_base_requirement(self):
        flat = classify_backyard(24, BACKYARD_LOOP_KM, 0.0)
        hilly = classify_backyard(24, BACKYARD_LOOP_KM, 250.0)
        assert backyard_min_weekly_km(hilly) > backyard_min_weekly_km(flat)

    def test_min_base_always_below_the_high_mileage_warning(self):
        for loops in range(MIN_TARGET_LOOPS, MAX_TARGET_LOOPS + 1):
            p = classify_backyard(loops)
            assert backyard_min_weekly_km(p) < backyard_max_weekly_km(p)
