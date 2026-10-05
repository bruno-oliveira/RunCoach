"""Tests for the goal-aware progressive pace model."""

from app.core.training.physiology.goal_pace_model import (
    GoalPaceContext,
    blend_fraction,
    blended_vdot,
    goal_pace_context,
    goal_vdot_from_time,
    pin_goal_race_pace,
    progressive_pace_zones,
    race_pace_min_km,
    race_pace_zone_label,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator


class TestGoalVdot:
    def test_5k_25min_matches_calculator(self):
        assert goal_vdot_from_time(5.0, 25 * 60) == VDOTCalculator.calculate_vdot(
            5.0, 25 * 60
        )

    def test_zero_or_missing_returns_none(self):
        assert goal_vdot_from_time(5.0, 0) is None
        assert goal_vdot_from_time(5.0, None) is None
        assert goal_vdot_from_time(0.0, 1500) is None


class TestBlendFraction:
    def test_first_week_is_current_end(self):
        assert blend_fraction(1, 12) == 0.0

    def test_last_week_is_goal_end(self):
        assert blend_fraction(12, 12) == 1.0

    def test_midpoint(self):
        assert blend_fraction(7, 13) == 0.5

    def test_single_week_plan_is_full_goal(self):
        assert blend_fraction(1, 1) == 1.0


class TestBlendedVdot:
    def test_ramps_from_current_to_goal(self):
        first = blended_vdot(40.0, 50.0, 1, 11)
        mid = blended_vdot(40.0, 50.0, 6, 11)
        last = blended_vdot(40.0, 50.0, 11, 11)
        assert first == 40.0
        assert mid == 45.0
        assert last == 50.0
        assert first < mid < last

    def test_missing_current_uses_goal(self):
        assert blended_vdot(None, 50.0, 3, 12) == 50.0

    def test_missing_goal_uses_current(self):
        assert blended_vdot(40.0, None, 3, 12) == 40.0


class TestRacePace:
    def test_race_pace_matches_goal_for_target_distance(self):
        # A goal VDOT derived from 5K in 25:00 should predict ~5:00/km at 5K.
        vdot = goal_vdot_from_time(5.0, 25 * 60)
        pace = race_pace_min_km(vdot, 5.0)
        assert pace is not None
        assert abs(pace - 5.0) < 0.05

    def test_zone_label_by_distance(self):
        assert race_pace_zone_label(5.0) == "I"
        assert race_pace_zone_label(10.0) == "T"
        assert race_pace_zone_label(21.0975) == "M"
        assert race_pace_zone_label(42.195) == "M"


class TestProgressivePaceZones:
    def _ctx(self):
        return GoalPaceContext(
            current_vdot=goal_vdot_from_time(5.0, 28 * 60),
            goal_vdot=goal_vdot_from_time(5.0, 25 * 60),
            goal_pace_min_km=5.0,
            target_distance_km=5.0,
        )

    def test_ladder_is_monotonic(self):
        zones = progressive_pace_zones(self._ctx(), week=12, total_weeks=12)
        e_fast = zones["E"]["pace_min_km_fast"]
        m = zones["M"]["pace_min_km"]
        t = zones["T"]["pace_min_km"]
        i = zones["I"]["pace_min_km"]
        r = zones["R"]["pace_min_km"]
        # Faster pace = smaller min/km; ladder must strictly speed up E>M>T>I>R.
        assert e_fast > m > t > i > r

    def test_race_pinned_to_exact_goal_pace(self):
        zones = progressive_pace_zones(self._ctx(), week=1, total_weeks=12)
        assert zones["race"]["pace_min_km"] == 5.0
        assert zones["race"]["zone_label"] == "I"

    def test_paces_sharpen_across_block(self):
        early = progressive_pace_zones(self._ctx(), week=1, total_weeks=12)
        late = progressive_pace_zones(self._ctx(), week=12, total_weeks=12)
        # Threshold pace should get faster (smaller) as the block progresses.
        assert late["T"]["pace_min_km"] < early["T"]["pace_min_km"]

    def test_empty_without_any_anchor(self):
        ctx = GoalPaceContext(None, None, None, 5.0)
        assert progressive_pace_zones(ctx, 1, 12) == {}

    def test_target_distance_label_pinned_to_goal_every_week(self):
        # A 10K goal at 4.80 min/km: the "10K" race-pace label (used by goal-pace
        # rehearsal sessions) must read the exact goal pace in every week, even
        # though the blended VDOT only converges to it by the final week.
        ctx = GoalPaceContext(
            current_vdot=goal_vdot_from_time(10.0, int(5.4 * 10 * 60)),
            goal_vdot=goal_vdot_from_time(10.0, int(4.8 * 10 * 60)),
            goal_pace_min_km=4.8,
            target_distance_km=10.0,
        )
        early = progressive_pace_zones(ctx, 1, 12)
        late = progressive_pace_zones(ctx, 12, 12)
        assert early["10K"]["pace_min_km"] == 4.8
        assert late["10K"]["pace_min_km"] == 4.8


class TestGoalPaceContext:
    def test_anchors_come_from_the_two_paces(self):
        ctx = goal_pace_context(5.0, 28 / 5, 25 / 5)
        assert ctx.current_vdot == goal_vdot_from_time(5.0, 28 * 60)
        assert ctx.goal_vdot == goal_vdot_from_time(5.0, 25 * 60)
        assert ctx.goal_pace_min_km == 5.0

    def test_missing_current_pace_leaves_only_the_goal_anchor(self):
        ctx = goal_pace_context(5.0, None, 5.0)
        assert ctx.current_vdot is None
        assert ctx.goal_vdot is not None


class TestPinGoalRacePace:
    def test_pins_the_target_distance_and_leaves_training_paces(self):
        vdot = goal_vdot_from_time(5.0, 28 * 60)
        plain = VDOTCalculator.get_pace_zones(vdot, 5.0)
        pinned = pin_goal_race_pace(VDOTCalculator.get_pace_zones(vdot, 5.0), 5.0, 5.0)
        assert pinned["5K"]["pace_str"] == "5:00/km"
        assert pinned["race"]["pace_min_km"] == 5.0
        # Fitness, not the goal, still sets every sustained training pace.
        for key in ("E", "M", "T", "10K"):
            assert pinned[key] == plain[key]

    def test_rep_zones_are_never_slower_than_the_goal(self):
        # 28:00 fitness predicts VO2max reps at ~5:22/km — slower than the
        # 5:00/km the same plan asks for in its goal-pace kilometres.
        vdot = goal_vdot_from_time(5.0, 28 * 60)
        pinned = pin_goal_race_pace(VDOTCalculator.get_pace_zones(vdot, 5.0), 5.0, 5.0)
        assert pinned["I"]["pace_str"] == "5:00/km"
        assert pinned["R"]["pace_str"] == "5:00/km"
        assert pinned["I"]["pace_min_km"] == pinned["R"]["pace_min_km"] == 5.0

    def test_rep_zones_already_faster_than_the_goal_are_left_alone(self):
        vdot = goal_vdot_from_time(5.0, 25 * 60)
        plain = VDOTCalculator.get_pace_zones(vdot, 5.0)
        pinned = pin_goal_race_pace(VDOTCalculator.get_pace_zones(vdot, 5.0), 5.0, 5.0)
        assert pinned["I"] == plain["I"]
        assert pinned["R"] == plain["R"]

    def test_longer_targets_pin_the_race_entry(self):
        zones = VDOTCalculator.get_pace_zones(40.0, 21.1)
        pin_goal_race_pace(zones, 5.45, 21.1)
        assert zones["race"]["pace_min_km"] == 5.45

    def test_no_goal_pace_is_a_no_op(self):
        zones = VDOTCalculator.get_pace_zones(40.0, 5.0)
        assert pin_goal_race_pace(dict(zones), None, 5.0) == zones
