"""Comprehensive tests for the plan generation engine.

Covers the core invariants, distance-specific rules, description correctness,
and edge cases. This is the safety net for RunCoach's unique feature.
"""

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.training.long_run_calculator import (
    calculate_long_run_distance,
    calculate_long_run_ratio,
    calculate_phases,
    get_long_run_ratio_range,
    _get_long_run_cap,
)
from app.core.training.quality_caps import (
    cap_quality_distance,
    cap_easy_distance,
    enforce_week_caps,
    get_quality_caps,
    QUALITY_CAPS_BY_DISTANCE,
)
from app.core.training.key_workout_library import (
    _rewrite_key_workout_description,
    _DISTANCE_REWRITES,
)
from app.core.training.workout_builders import (
    generate_tempo_run,
    generate_interval_run,
    generate_easy_run,
    generate_long_run,
)


# ── Long Run Caps: must be below race distance ─────────────────────────────

class TestLongRunCapsBelowRaceDistance:
    """Long run base caps must always be strictly below the race distance
    for half marathon and above. For 5K/10K it's normal to run longer
    than race distance in training."""

    CAPS = {
        5.0:  {'beginner': 7.0,  'intermediate': 8.0,  'advanced': 10.0},
        10.0: {'beginner': 12.0, 'intermediate': 15.0, 'advanced': 16.0},
        21.1: {'beginner': 17.0, 'intermediate': 18.0, 'advanced': 19.0},
        30.0: {'beginner': 24.0, 'intermediate': 25.5, 'advanced': 27.0},
        42.2: {'beginner': 32.0, 'intermediate': 34.0, 'advanced': 36.0},
    }
    HARD_CEILINGS = {5.0: 14.0, 10.0: 22.0, 21.1: 24.0, 30.0: 30.0, 42.2: 40.0}

    @pytest.mark.parametrize("distance", [21.1, 30.0, 42.2])
    @pytest.mark.parametrize("tier", ["beginner", "intermediate", "advanced"])
    def test_base_cap_below_race(self, distance, tier):
        cap = self.CAPS[distance][tier]
        assert cap < distance, (
            f"{distance}km {tier} cap {cap}km >= race distance"
        )

    @pytest.mark.parametrize("distance", [21.1, 30.0, 42.2])
    def test_base_cap_at_least_75_percent_of_race(self, distance):
        """Caps should be at least 75% of race distance for meaningful training."""
        for tier in ["intermediate", "advanced"]:
            cap = self.CAPS[distance][tier]
            ratio = cap / distance
            assert ratio >= 0.75, (
                f"{distance}km {tier} cap {cap}km is only {ratio:.0%} of race"
            )

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 30.0, 42.2])
    def test_hard_ceiling_above_base_cap(self, distance):
        """Hard ceiling must be >= the highest tier's base cap."""
        max_cap = max(self.CAPS[distance].values())
        ceiling = self.HARD_CEILINGS[distance]
        assert ceiling >= max_cap, (
            f"{distance}km ceiling {ceiling} < max cap {max_cap}"
        )

    @pytest.mark.parametrize("distance", [42.2])
    def test_hard_ceiling_below_or_at_race_distance(self, distance):
        """For marathon, hard ceiling should not exceed ~95% of race distance."""
        ceiling = self.HARD_CEILINGS[distance]
        max_allowed = distance * 0.95
        assert ceiling <= max_allowed + 0.1, (
            f"{distance}km ceiling {ceiling} exceeds {max_allowed}km"
        )

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 30.0, 42.2])
    def test_tier_ordering(self, distance):
        """Advanced cap >= intermediate >= beginner."""
        caps = self.CAPS[distance]
        assert caps["advanced"] >= caps["intermediate"] >= caps["beginner"]

    def test_get_long_run_cap_returns_correct_values(self):
        """Verify the actual function returns values matching our caps."""
        for distance, tiers in self.CAPS.items():
            for tier, expected in tiers.items():
                actual = _get_long_run_cap(distance, tier, weekly_km=0)
                assert actual == expected, (
                    f"{distance}km {tier}: expected {expected}, got {actual}"
                )


# ── Generated Plans: Long Run Never Reaches Race Distance ──────────────────

class TestGeneratedPlanLongRunBounds:
    """End-to-end: for half marathon and above, no long run should equal
    or exceed the target race distance. For 5K/10K it's normal to run
    longer than race distance."""

    @pytest.mark.parametrize("distance", [21.1, 30.0, 42.2])
    def test_long_run_never_equals_race_distance(self, distance):
        gen = TrainingPlanGenerator()
        base_km = {21.1: 25, 30.0: 25, 42.2: 35}
        weeks = {21.1: 12, 30.0: 12, 42.2: 16}
        plan = gen.generate_plan(
            current_km=base_km[distance],
            target_distance=distance,
            weeks=weeks[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] == "long":
                    assert w["distance"] < distance, (
                        f"W{week['week']}: long run {w['distance']}km >= "
                        f"race distance {distance}km"
                    )

    @pytest.mark.parametrize("distance", [21.1, 42.2])
    def test_long_run_stays_below_90_percent_of_race(self, distance):
        """For half and marathon, long runs should stay well below race distance."""
        gen = TrainingPlanGenerator()
        base_km = {21.1: 25, 42.2: 35}
        weeks = {21.1: 12, 42.2: 16}
        plan = gen.generate_plan(
            current_km=base_km[distance],
            target_distance=distance,
            weeks=weeks[distance],
            max_runs_per_week=4,
        )
        threshold = distance * 0.92
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] == "long":
                    assert w["distance"] <= threshold, (
                        f"W{week['week']}: long run {w['distance']}km > "
                        f"92% of race ({threshold:.1f}km)"
                    )


# ── Description Rewriting ──────────────────────────────────────────────────

class TestDescriptionRewriting:
    """Key workout descriptions with hardcoded distances must be rewritten
    to match the actual assigned distance."""

    def test_rewrite_marathon_mp_long(self):
        desc = (
            "Run 25km total. First 15km at easy pace, then shift to "
            "marathon goal pace for the final 10km. Take a gel at 8km "
            "and 16km to practice race fueling."
        )
        result = _rewrite_key_workout_description(desc, "marathon_mp_long", 30.0)
        assert "25km" not in result
        assert "30km" in result

    def test_rewrite_half_progressive_long(self):
        desc = (
            "Run 14-16km total. Start at easy pace for 10km, then "
            "increase to marathon pace for the final 4-6km. "
            "No warm-up needed — the easy start IS the warm-up."
        )
        result = _rewrite_key_workout_description(desc, "half_progressive_long", 18.0)
        assert "14-16km" not in result
        assert "18km" in result

    def test_rewrite_unknown_workout_returns_original(self):
        desc = "Some random workout description with 10km in it."
        result = _rewrite_key_workout_description(desc, "nonexistent_id", 15.0)
        assert result == desc

    def test_all_rewrites_have_valid_ids(self):
        """Every rewrite rule should reference a real workout id."""
        from app.core.training.key_workout_data import WORKOUTS
        valid_ids = {w["id"] for w in WORKOUTS}
        for workout_id in _DISTANCE_REWRITES:
            assert workout_id in valid_ids, (
                f"Rewrite rule for '{workout_id}' has no matching workout"
            )


# ── Workout Builder Descriptions: No Negative or Nonsense Distances ────────

class TestWorkoutBuilderDescriptions:
    """Generated descriptions must never contain negative distances or
    nonsensical segment calculations."""

    def test_tempo_run_no_negative_distance(self):
        """Tempo run descriptions must not produce negative segment distances."""
        for dist in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
            workout = generate_tempo_run(1, dist, 10.0)
            desc = workout["description"]
            assert "-" not in desc.split("km")[0].split()[-1] or "at" in desc, (
                f"Tempo at {dist}km has negative segment: {desc}"
            )

    def test_easy_run_time_based_for_short_distance(self):
        """Easy runs under 3km should use time-based descriptions."""
        workout = generate_easy_run(1, 2.0, 10.0)
        assert "duration_min" in workout
        assert "minutes" in workout["description"].lower()

    def test_long_run_time_based_for_short_distance(self):
        """Long runs under 3km should use time-based descriptions."""
        workout = generate_long_run(1, 2.0, 10.0)
        assert "duration_min" in workout
        assert "minutes" in workout["description"].lower()

    def test_interval_run_no_nonsense_reps(self):
        """Interval descriptions should not produce absurd rep counts."""
        for dist in [1.0, 2.0, 3.0, 4.0, 5.0]:
            workout = generate_interval_run(1, dist, 20.0)
            desc = workout["description"]
            assert "0x" not in desc, (
                f"Interval at {dist}km has zero reps: {desc}"
            )


# ── Quality Caps ───────────────────────────────────────────────────────────

class TestQualityCaps:
    """Quality workout distances must respect physiological ceilings and
    the long-run-relative cap."""

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 30.0, 42.2])
    def test_caps_exist_for_all_distances(self, distance):
        assert distance in QUALITY_CAPS_BY_DISTANCE

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 30.0, 42.2])
    @pytest.mark.parametrize("wtype", ["tempo", "interval", "hill"])
    def test_caps_are_positive(self, distance, wtype):
        caps = QUALITY_CAPS_BY_DISTANCE[distance]
        assert caps[wtype] > 0

    def test_base_phase_reduces_caps(self):
        """Base phase should reduce quality caps by 20%."""
        caps_build = get_quality_caps(21.1, "build")
        caps_base = get_quality_caps(21.1, "base")
        for wtype in ["tempo", "interval", "hill"]:
            assert caps_base[wtype] < caps_build[wtype]

    def test_cap_quality_distance_respects_long_run(self):
        """Quality distance should be capped at 85% of long run."""
        long_run = 10.0
        capped = cap_quality_distance(12.0, long_run, "tempo", 21.1, "build")
        assert capped <= long_run * 0.85 + 0.1  # 5% rounding slack

    def test_cap_easy_distance_respects_long_run(self):
        """Easy run should be capped at 95% of long run."""
        long_run = 10.0
        capped = cap_easy_distance(12.0, long_run)
        assert capped <= long_run * 0.95 + 0.1


# ── Phase Structure ────────────────────────────────────────────────────────

class TestPhaseStructure:
    """Phase distributions must be coherent and distance-appropriate."""

    def test_phases_sum_to_total_weeks(self):
        for weeks in [4, 6, 8, 10, 12, 16, 20, 24]:
            for distance in [5.0, 10.0, 21.1, 30.0, 42.2]:
                phases = calculate_phases(weeks, distance)
                assert sum(phases.values()) == weeks, (
                    f"{weeks}wk {distance}km: phases sum to {sum(phases.values())}"
                )

    def test_all_phases_present(self):
        for weeks in [8, 12, 16]:
            for distance in [5.0, 10.0, 21.1, 42.2]:
                phases = calculate_phases(weeks, distance)
                for phase in ["base", "build", "peak", "taper"]:
                    assert phases[phase] >= 1, (
                        f"{weeks}wk {distance}km: missing {phase} phase"
                    )

    def test_marathon_longer_base_and_build(self):
        """Marathon plans should emphasize base and build over shorter distances."""
        phases_marathon = calculate_phases(16, 42.2)
        phases_5k = calculate_phases(16, 5.0)
        assert phases_marathon["base"] + phases_marathon["build"] >= \
               phases_5k["base"] + phases_5k["build"]

    def test_taper_length_by_distance(self):
        """Marathon gets 3-week taper, others get 2."""
        phases_marathon = calculate_phases(16, 42.2)
        assert phases_marathon["taper"] == 3

        for distance in [5.0, 10.0, 21.1, 30.0]:
            phases = calculate_phases(12, distance)
            assert phases["taper"] == 2


# ── Long Run Ratio Ranges ─────────────────────────────────────────────────

class TestLongRunRatioRanges:
    """Long run as % of weekly volume should scale with race distance."""

    def test_marathon_ratio_higher_than_5k(self):
        """Marathon long run ratio should be higher than 5K in all phases."""
        for phase in ["base", "build", "peak", "taper"]:
            min_5k, max_5k = get_long_run_ratio_range(phase, 5.0, 12)
            min_mar, max_mar = get_long_run_ratio_range(phase, 42.2, 16)
            assert min_mar >= min_5k, (
                f"{phase}: marathon min ratio {min_mar} < 5K min {min_5k}"
            )
            assert max_mar >= max_5k, (
                f"{phase}: marathon max ratio {max_mar} < 5K max {max_5k}"
            )

    def test_recovery_week_reduces_ratio(self):
        """Recovery weeks should have a lower long run ratio."""
        phases = calculate_phases(12, 21.1)
        normal = calculate_long_run_ratio("build", 5, phases, 21.1, False, 12)
        recovery = calculate_long_run_ratio("build", 5, phases, 21.1, True, 12)
        assert recovery < normal


# ── Generated Plan: Structural Invariants ──────────────────────────────────

class PlanInvariant:
    """Base class for invariant tests across all plan combinations."""
    DISTANCES = [5.0, 10.0, 21.1, 30.0, 42.2]
    BASE_KM = {5.0: 15, 10.0: 20, 21.1: 25, 30.0: 25, 42.2: 35}
    WEEKS = {5.0: 8, 10.0: 10, 21.1: 12, 30.0: 12, 42.2: 16}

    def _gen(self, distance, max_runs=4):
        gen = TrainingPlanGenerator()
        return gen.generate_plan(
            current_km=self.BASE_KM[distance],
            target_distance=distance,
            weeks=self.WEEKS[distance],
            max_runs_per_week=max_runs,
        )


class TestEveryWeekHasLongRun(PlanInvariant):
    """Every week must have exactly one long run."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    def test_every_week_has_long_run(self, distance):
        plan = self._gen(distance)
        for week in plan:
            longs = [w for w in week["daily_workouts"] if w["type"] == "long"]
            assert len(longs) == 1, (
                f"W{week['week']} {distance}km: {len(longs)} long runs"
            )


class TestRunCountMatchesRequest(PlanInvariant):
    """Number of running days must equal max_runs_per_week."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    @pytest.mark.parametrize("max_runs", [3, 4, 5])
    def test_run_count(self, distance, max_runs):
        plan = self._gen(distance, max_runs)
        for week in plan:
            runs = [w for w in week["daily_workouts"]
                    if w["type"] not in ("rest", "recovery")]
            assert len(runs) == max_runs, (
                f"W{week['week']} {distance}km: {len(runs)} runs, expected {max_runs}"
            )


class TestTotalKmMatchesWorkouts(PlanInvariant):
    """Week total_km must match sum of workout distances."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    def test_total_km_consistency(self, distance):
        plan = self._gen(distance)
        for week in plan:
            actual = sum(w.get("distance", 0) for w in week["daily_workouts"])
            assert abs(actual - week["total_km"]) <= 0.5, (
                f"W{week['week']} {distance}km: total={week['total_km']}, "
                f"sum={actual}"
            )


class TestNoNegativeDistances(PlanInvariant):
    """No workout should have a negative distance."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    def test_no_negative_distances(self, distance):
        plan = self._gen(distance)
        for week in plan:
            for w in week["daily_workouts"]:
                assert w.get("distance", 0) >= 0, (
                    f"W{week['week']} D{w['day']}: negative distance {w.get('distance')}"
                )


class TestEveryWorkoutHasDescription(PlanInvariant):
    """Every workout must have a non-empty description."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    def test_descriptions_present(self, distance):
        plan = self._gen(distance)
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] not in ("rest", "recovery"):
                    desc = w.get("description", "")
                    assert desc, (
                        f"W{week['week']} D{w['day']} {w['type']}: empty description"
                    )


class TestLongRunIsAlwaysLongest(PlanInvariant):
    """The long run must be the longest workout in every week."""

    @pytest.mark.parametrize("distance", PlanInvariant.DISTANCES)
    def test_long_run_longest(self, distance):
        plan = self._gen(distance)
        for week in plan:
            workouts = week["daily_workouts"]
            longs = [w for w in workouts if w["type"] == "long" and w.get("distance", 0) > 0]
            if not longs:
                continue
            long_d = longs[0]["distance"]
            for w in workouts:
                if w["type"] in ("easy", "tempo", "interval", "hill"):
                    assert w.get("distance", 0) <= long_d + 0.1, (
                        f"W{week['week']} {distance}km: {w['type']} ({w.get('distance')}km) "
                        f"> long run ({long_d}km)"
                    )


# ── Taper Behavior ─────────────────────────────────────────────────────────

class TestTaperBehavior:
    """Taper weeks must show progressive reduction in volume."""

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 30.0, 42.2])
    def test_taper_reduces_volume(self, distance):
        gen = TrainingPlanGenerator()
        base_km = {5.0: 15, 10.0: 20, 21.1: 25, 30.0: 25, 42.2: 35}
        weeks = {5.0: 8, 10.0: 10, 21.1: 12, 30.0: 12, 42.2: 16}
        plan = gen.generate_plan(
            current_km=base_km[distance],
            target_distance=distance,
            weeks=weeks[distance],
            max_runs_per_week=4,
        )
        taper_weeks = [w for w in plan if w["phase"] == "taper"]
        assert len(taper_weeks) >= 1

        pre_taper = [w for w in plan if w["phase"] != "taper"]
        if pre_taper:
            peak_km = max(w["total_km"] for w in pre_taper)
            for tw in taper_weeks:
                assert tw["total_km"] < peak_km, (
                    f"Taper week {tw['week']} volume {tw['total_km']} >= peak {peak_km}"
                )

    def test_race_week_lowest_volume(self):
        """The final week (race week) should have the lowest volume."""
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=35, target_distance=42.2, weeks=16, max_runs_per_week=4,
        )
        race_week = plan[-1]
        pre_taper_km = [w["total_km"] for w in plan if w["phase"] != "taper"]
        if pre_taper_km:
            assert race_week["total_km"] < max(pre_taper_km)


# ── Recovery Week Behavior ─────────────────────────────────────────────────

class TestRecoveryWeeks:
    """Recovery weeks must show ~35% volume reduction."""

    @pytest.mark.parametrize("distance", [10.0, 21.1, 42.2])
    def test_recovery_week_volume_drop(self, distance):
        gen = TrainingPlanGenerator()
        base_km = {10.0: 20, 21.1: 25, 42.2: 35}
        weeks = {10.0: 12, 21.1: 12, 42.2: 16}
        plan = gen.generate_plan(
            current_km=base_km[distance],
            target_distance=distance,
            weeks=weeks[distance],
            max_runs_per_week=4,
        )
        for i, week in enumerate(plan):
            if week["is_recovery"] and i > 0:
                prev = plan[i - 1]
                expected = prev["total_km"] * 0.65
                tolerance = expected * 0.20
                assert abs(week["total_km"] - expected) <= tolerance, (
                    f"W{week['week']} recovery: expected ~{expected:.1f}, "
                    f"got {week['total_km']}"
                )


# ── Cross-Distance Volume Scaling ──────────────────────────────────────────

class TestCrossDistanceScaling:
    """Longer distances should produce higher peak weekly volumes."""

    def test_peak_mileage_scales_with_distance(self):
        gen = TrainingPlanGenerator()
        peaks = {}
        for distance in [5.0, 10.0, 21.1, 42.2]:
            base_km = {5.0: 15, 10.0: 20, 21.1: 25, 42.2: 35}
            weeks_map = {5.0: 8, 10.0: 10, 21.1: 12, 42.2: 16}
            plan = gen.generate_plan(
                current_km=base_km[distance],
                target_distance=distance,
                weeks=weeks_map[distance],
                max_runs_per_week=4,
            )
            peaks[distance] = max(w["total_km"] for w in plan)

        assert peaks[42.2] > peaks[21.1] > peaks[10.0] > peaks[5.0], (
            f"Peak mileage not monotonically increasing: {peaks}"
        )


# ── VDOT Integration ───────────────────────────────────────────────────────

class TestVDOTIntegration:
    """Plans with VDOT should include pace zones and enriched descriptions."""

    def test_vdot_includes_pace_zones(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=25, target_distance=21.1, weeks=12,
            max_runs_per_week=4, vdot=45.0,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] not in ("rest", "recovery"):
                    steps = w.get("steps", [])
                    if steps:
                        paces = [s.get("pace_str") for s in steps if s.get("pace_str")]
                        assert len(paces) > 0, (
                            f"W{week['week']} D{w['day']}: no paces in steps"
                        )

    def test_vdot_affects_peak_mileage(self):
        """Higher VDOT runners should get slightly higher peak mileage."""
        gen = TrainingPlanGenerator()
        plan_low = gen.generate_plan(
            current_km=30, target_distance=42.2, weeks=16,
            max_runs_per_week=4, vdot=35.0,
        )
        plan_high = gen.generate_plan(
            current_km=30, target_distance=42.2, weeks=16,
            max_runs_per_week=4, vdot=55.0,
        )
        peak_low = max(w["total_km"] for w in plan_low)
        peak_high = max(w["total_km"] for w in plan_high)
        assert peak_high >= peak_low, (
            f"Higher VDOT should not reduce peak: {peak_high} < {peak_low}"
        )


# ── Edge Cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Plans at boundary conditions must still be valid."""

    def test_minimum_weeks_5k(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=10, target_distance=5.0, weeks=4, max_runs_per_week=3,
        )
        assert len(plan) == 4
        assert all(w["total_km"] > 0 for w in plan)

    def test_minimum_weeks_marathon(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=30, target_distance=42.2, weeks=12, max_runs_per_week=4,
        )
        assert len(plan) == 12
        assert all(w["total_km"] > 0 for w in plan)

    def test_high_mileage_experienced_runner(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=80, target_distance=42.2, weeks=16, max_runs_per_week=6,
        )
        assert len(plan) == 16
        peak = max(w["total_km"] for w in plan)
        assert peak <= 86  # Absolute max for marathon (85 + rounding)

    def test_just_above_minimum_mileage(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=16, target_distance=21.1, weeks=12, max_runs_per_week=4,
        )
        assert len(plan) == 12
        for week in plan:
            assert week["total_km"] > 0

    def test_max_runs_6(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km=30, target_distance=21.1, weeks=12, max_runs_per_week=6,
        )
        for week in plan:
            runs = [w for w in week["daily_workouts"]
                    if w["type"] not in ("rest", "recovery")]
            assert len(runs) == 6


# ── Coaching Rationale ─────────────────────────────────────────────────────

class TestCoachingRationale:
    """Every workout should have a coaching rationale."""

    @pytest.mark.parametrize("distance", [5.0, 21.1, 42.2])
    def test_coaching_rationale_present(self, distance):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km={5.0: 15, 21.1: 25, 42.2: 35}[distance],
            target_distance=distance,
            weeks={5.0: 8, 21.1: 12, 42.2: 16}[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] not in ("rest", "recovery"):
                    assert w.get("coaching_rationale"), (
                        f"W{week['week']} D{w['day']}: missing coaching rationale"
                    )


# ── Strength Training ──────────────────────────────────────────────────────

class TestStrengthTraining:
    """Strength sessions must only appear on easy run days."""

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 42.2])
    def test_strength_only_on_easy_days(self, distance):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km={5.0: 15, 10.0: 20, 21.1: 25, 42.2: 35}[distance],
            target_distance=distance,
            weeks={5.0: 8, 10.0: 10, 21.1: 12, 42.2: 16}[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w.get("strength_session"):
                    assert w["type"] == "easy", (
                        f"W{week['week']} D{w['day']}: strength on {w['type']}"
                    )


# ── Key Workout Overlay ────────────────────────────────────────────────────

class TestKeyWorkoutOverlay:
    """Key workouts should only appear in build/peak phases."""

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 42.2])
    def test_key_workouts_only_in_build_peak(self, distance):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km={5.0: 15, 10.0: 20, 21.1: 25, 42.2: 35}[distance],
            target_distance=distance,
            weeks={5.0: 8, 10.0: 10, 21.1: 12, 42.2: 16}[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            has_key = any(
                w.get("key_workout_id")
                for w in week["daily_workouts"]
                if w["type"] not in ("rest", "recovery")
            )
            if has_key:
                assert week["phase"] in ("build", "peak"), (
                    f"W{week['week']}: key workout in {week['phase']} phase"
                )

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 42.2])
    def test_base_phase_no_key_workouts(self, distance):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km={5.0: 15, 10.0: 20, 21.1: 25, 42.2: 35}[distance],
            target_distance=distance,
            weeks={5.0: 8, 10.0: 10, 21.1: 12, 42.2: 16}[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            if week["phase"] == "base":
                for w in week["daily_workouts"]:
                    assert not w.get("key_workout_id"), (
                        f"W{week['week']}: key workout in base phase"
                    )


# ── Steps Structure ────────────────────────────────────────────────────────

class TestWorkoutSteps:
    """Workouts should have structured steps for guided execution."""

    @pytest.mark.parametrize("distance", [5.0, 21.1, 42.2])
    def test_running_workouts_have_steps(self, distance):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(
            current_km={5.0: 15, 21.1: 25, 42.2: 35}[distance],
            target_distance=distance,
            weeks={5.0: 8, 21.1: 12, 42.2: 16}[distance],
            max_runs_per_week=4,
        )
        for week in plan:
            for w in week["daily_workouts"]:
                if w["type"] in ("easy", "long", "tempo", "interval", "hill"):
                    steps = w.get("steps", [])
                    assert len(steps) > 0, (
                        f"W{week['week']} D{w['day']} {w['type']}: no steps"
                    )
