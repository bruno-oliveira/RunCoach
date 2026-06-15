"""End-to-end plan generation under the parameterized trail mode.

Verifies that distance + elevation produce structurally different plans:
* Flat trail gets tempo work and zero hill repeats.
* Mountainous gets hill repeats and trims interval/track work.
* Ultra brackets get a 3-week taper.
* Long-run cap stays sane for 100-mile prep.
* Peak weekly mileage scales continuously with distance and elevation.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training import mileage_progression, phase_calculator
from app.core.training.long_run_calculator import (
    _get_long_run_cap,
    calculate_long_run_distance,
    get_long_run_ratio_range,
)
from app.core.training.trail_profile import classify_trail
from app.core.training.workout_steps import _compute_distance_from_steps


def _build_plan(distance, elevation, weeks, runs, current_km, terrain=None):
    profile = classify_trail(distance, elevation)
    return TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
        terrain=terrain,
        trail_profile=profile,
    )


class TestPhaseDistribution:
    """PHASE_DISTRIBUTIONS keys are derived from elevation class."""

    @pytest.mark.parametrize(
        "elevation_class", ["flat", "rolling", "hilly", "mountainous"]
    )
    def test_all_trail_buckets_present_per_phase(self, elevation_class):
        key = f"Trail{elevation_class.capitalize()}"
        for phase in ("base", "build", "peak", "taper"):
            assert key in phase_calculator.PHASE_DISTRIBUTIONS[phase]

    def test_legacy_aliases_resolve(self):
        # 'Trail' and 'FlatTrail' are kept as aliases for unmigrated callsites.
        assert (
            phase_calculator.PHASE_DISTRIBUTIONS["build"]["Trail"]
            == phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailHilly"]
        )
        assert (
            phase_calculator.PHASE_DISTRIBUTIONS["build"]["FlatTrail"]
            == phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailFlat"]
        )

    def test_flat_trail_replaces_hills_with_tempo(self):
        flat = phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailFlat"]
        hilly = phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailHilly"]
        # Flat: zero hill stimulus, more tempo than hilly baseline.
        assert flat["hill"] == 0.0
        assert flat["tempo"] > hilly["tempo"]
        assert flat["interval"] >= hilly["interval"]

    def test_mountainous_intensifies_hill_work(self):
        mountain = phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailMountainous"]
        hilly = phase_calculator.PHASE_DISTRIBUTIONS["build"]["TrailHilly"]
        assert mountain["hill"] > hilly["hill"]
        # Track-style intervals are partly displaced by hill repeats.
        assert mountain["interval"] <= hilly["interval"]

    def test_race_profile_drives_distribution_even_with_flat_training(self):
        profile = classify_trail(50.0, 2500.0)  # mountainous race profile
        key = phase_calculator.get_distance_category(
            50.0,
            terrain="flat",
            trail_profile=profile,
        )
        assert key == "TrailMountainous"

    @pytest.mark.parametrize(
        "elevation_class", ["flat", "rolling", "hilly", "mountainous"]
    )
    def test_distribution_buckets_sum_to_one(self, elevation_class):
        key = f"Trail{elevation_class.capitalize()}"
        for phase in ("base", "build", "peak", "taper"):
            buckets = phase_calculator.PHASE_DISTRIBUTIONS[phase][key]
            total = sum(buckets.values())
            assert total == pytest.approx(1.0, abs=0.01)


class TestPhaseLength:
    """Ultras get a 3-week taper; short/standard stay at 2."""

    def test_short_bracket_2_week_taper(self):
        profile = classify_trail(15.0, 500.0)
        phases = phase_calculator.calculate_phases(12, 15.0, trail_profile=profile)
        assert phases["taper"] == 2

    def test_standard_bracket_2_week_taper(self):
        profile = classify_trail(30.0, 1000.0)
        phases = phase_calculator.calculate_phases(14, 30.0, trail_profile=profile)
        assert phases["taper"] == 2

    def test_ultra_bracket_3_week_taper(self):
        profile = classify_trail(50.0, 2000.0)
        phases = phase_calculator.calculate_phases(20, 50.0, trail_profile=profile)
        assert phases["taper"] == 3

    def test_long_ultra_bracket_3_week_taper(self):
        profile = classify_trail(100.0, 4000.0)
        phases = phase_calculator.calculate_phases(28, 100.0, trail_profile=profile)
        assert phases["taper"] == 3


class TestTaperCurve:
    """Ultra taper drops sharper than marathon."""

    def test_ultra_3_week_taper_more_aggressive_than_marathon(self):
        ultra_profile = classify_trail(80.0, 3000.0)
        ultra_curve = mileage_progression._get_taper_curve(
            3, 80.0, trail_profile=ultra_profile
        )
        marathon_curve = mileage_progression._get_taper_curve(3, 42.2)
        # First and last weeks: ultra trims further from peak than marathon.
        assert ultra_curve[0] <= marathon_curve[0]
        assert ultra_curve[-1] < marathon_curve[-1]


class TestPeakMileage:
    """Trail peak is continuous in distance × elevation."""

    def test_peak_scales_continuously_with_distance(self):
        # Larger distance → larger peak ceiling, all else equal.
        small = mileage_progression.get_peak_mileage(
            30.0,
            current_km=20,
            weeks=12,
            trail_profile=classify_trail(30.0, 500.0),
        )
        big = mileage_progression.get_peak_mileage(
            80.0,
            current_km=20,
            weeks=20,
            trail_profile=classify_trail(80.0, 500.0),
        )
        assert big > small

    def test_peak_scales_with_elevation(self):
        flat = mileage_progression.get_peak_mileage(
            50.0,
            current_km=30,
            weeks=16,
            trail_profile=classify_trail(50.0, 200.0),
        )
        mountain = mileage_progression.get_peak_mileage(
            50.0,
            current_km=30,
            weeks=16,
            trail_profile=classify_trail(50.0, 3000.0),
        )
        assert mountain >= flat  # mountain ceiling is higher

    def test_peak_clamps_at_140km(self):
        peak = mileage_progression.get_peak_mileage(
            163.0,
            current_km=80,
            weeks=32,
            trail_profile=classify_trail(163.0, 8000.0),
        )
        assert peak <= 140.0


class TestLongRunRatios:
    """Ultra brackets pull a higher long-run share."""

    def test_ultra_long_run_ratio_higher_than_standard(self):
        std_lo, std_hi = get_long_run_ratio_range(
            "build",
            30.0,
            14,
            trail_profile=classify_trail(30.0, 1000.0),
        )
        ultra_lo, ultra_hi = get_long_run_ratio_range(
            "build",
            50.0,
            20,
            trail_profile=classify_trail(50.0, 1500.0),
        )
        assert ultra_hi >= std_hi


class TestLongRunCap:
    """Long-run cap scales with race distance but stays within a sane ceiling."""

    def test_long_ultra_cap_scales_up_but_stays_bounded(self):
        # 100-mile prep gets a genuinely long peak run, but the continuous
        # curve is clamped at the absolute ceiling (48 km).
        profile = classify_trail(163.0, 6000.0)
        cap = _get_long_run_cap(
            163.0, "advanced", weekly_km=120.0, trail_profile=profile
        )
        assert 40.0 <= cap <= 48.0

    def test_cap_scales_continuously_with_distance(self):
        # A longer race earns a longer single-run cap, all else equal.
        short = _get_long_run_cap(
            30.0,
            "intermediate",
            weekly_km=60.0,
            trail_profile=classify_trail(30.0, 900.0),
        )
        ultra = _get_long_run_cap(
            70.0,
            "intermediate",
            weekly_km=60.0,
            trail_profile=classify_trail(70.0, 2100.0),
        )
        assert ultra > short

    def test_short_bracket_cap_is_modest(self):
        profile = classify_trail(15.0, 500.0)
        cap = _get_long_run_cap(
            15.0, "intermediate", weekly_km=30.0, trail_profile=profile
        )
        assert cap <= 18.0


class TestEndToEnd:
    """Full plan generation for representative trail scenarios."""

    def test_50km_flat_plan_generates_with_tempo(self):
        plan = _build_plan(50.0, 200.0, 16, 5, current_km=40.0)
        assert len(plan) == 16
        # Build/peak weeks contain at least one tempo session
        build_peak_workouts = [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
        ]
        assert any(w["type"] == "tempo" for w in build_peak_workouts), (
            "Flat 50k build/peak must include tempo sessions"
        )
        # And no hill repeats anywhere
        all_workouts = [w for week in plan for w in week["daily_workouts"]]
        assert not any(w["type"] == "hill" for w in all_workouts), (
            "Flat trail must not prescribe hill repeats"
        )

    def test_50km_flat_plan_includes_interval_stimulus(self):
        plan = _build_plan(50.0, 200.0, 16, 5, current_km=40.0)
        build_peak_workouts = [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
        ]
        assert any(w["type"] == "interval" for w in build_peak_workouts), (
            "Flat 50k build/peak should include interval stimulus"
        )

    def test_80km_mountain_plan_includes_hills(self):
        plan = _build_plan(80.0, 4500.0, 24, 6, current_km=50.0)
        all_workouts = [w for week in plan for w in week["daily_workouts"]]
        assert any(w["type"] == "hill" for w in all_workouts), (
            "Mountainous plan must include hill repeats"
        )

    def test_mountain_race_with_flat_training_substitutes_hills(self):
        plan = _build_plan(50.0, 2500.0, 16, 5, current_km=35.0, terrain="flat")
        build_peak = [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
        ]
        assert not any(w["type"] == "hill" for w in build_peak), (
            "Flat-access plans should substitute hill sessions"
        )
        assert any(w["type"] == "tempo" for w in build_peak)
        assert any(w["type"] == "interval" for w in build_peak)

    def test_mountain_race_with_flat_training_has_vertical_sim_targets(self):
        plan = _build_plan(50.0, 2500.0, 16, 5, current_km=35.0, terrain="flat")
        build_week = next(
            w for w in plan if w["phase"] == "build" and not w["is_recovery"]
        )
        targets = build_week.get("vertical_simulation")
        assert targets and targets.get("enabled")
        assert targets["simulated_uphill_m"] > 0
        assert targets["uphill_effort_min"] >= 15

    def test_non_flat_training_does_not_emit_vertical_sim_targets(self):
        plan = _build_plan(50.0, 2500.0, 16, 5, current_km=35.0, terrain="hilly")
        assert all(week.get("vertical_simulation") is None for week in plan)

    def test_100mi_plan_long_run_capped(self):
        plan = _build_plan(163.0, 6000.0, 32, 6, current_km=80.0)
        long_runs = [
            w for week in plan for w in week["daily_workouts"] if w["type"] == "long"
        ]
        max_long = max(w["distance"] for w in long_runs)
        # 100-mile prep earns a long peak run, but the continuous cap is
        # clamped at the 48 km absolute ceiling.
        assert max_long <= 48.0, f"Single long run was {max_long} km — cap blown"
        assert max_long >= 38.0, (
            f"Single long run was only {max_long} km — should scale up for 100mi"
        )

    def test_ultra_plan_has_3_week_taper(self):
        plan = _build_plan(50.0, 1500.0, 16, 5, current_km=30.0)
        taper_weeks = [w for w in plan if w["phase"] == "taper"]
        assert len(taper_weeks) == 3

    def test_flat_30k_long_run_ratio_capped_for_four_plus_runs(self):
        plan = _build_plan(30.0, 100.0, 14, 5, current_km=25.0)
        for week in plan:
            runs = [
                w
                for w in week["daily_workouts"]
                if w["type"] not in ("rest", "recovery") and w.get("distance", 0) > 0
            ]
            if len(runs) < 4:
                continue
            total = sum(w["distance"] for w in runs)
            if total <= 0:
                continue
            long_run = max(
                (w["distance"] for w in runs if w["type"] == "long"), default=0
            )
            ratio = long_run / total
            if week.get("phase") == "peak":
                assert ratio <= 0.65 + 0.01
            else:
                assert ratio <= 0.55 + 0.01

    def test_legacy_30km_plan_unchanged_structure(self):
        # No is_trail / no profile passed, but target=30.0 → back-compat path.
        plan = TrainingPlanGenerator().generate_plan(
            current_km=25.0,
            target_distance=30.0,
            weeks=12,
            max_runs_per_week=4,
        )
        assert len(plan) == 12
        # Should have hill repeats (legacy default elevation=1000m → hilly bucket).
        all_workouts = [w for week in plan for w in week["daily_workouts"]]
        assert any(w["type"] == "hill" for w in all_workouts)


class TestPeakLongRunRaceFraction:
    """Peak long run reaches a race-distance share, not just a weekly slice.

    Coaches prescribe trail long runs as a fraction of race distance (with
    bracket caps and a weekly safety cap). These regressions guard the floor.
    """

    def test_standard_30km_at_35wk_advanced_reaches_floor(self):
        profile = classify_trail(30.0, 1000.0)
        # Peak phase, mid-progression in a 12-week plan: phases pack peak
        # near the end, and the floor applies regardless of progression.
        peak_lr = calculate_long_run_distance(
            total_km=35,
            target_distance=30.0,
            weeks=12,
            week_number=10,
            phase="peak",
            is_recovery_week=False,
            experience_level="advanced",
            trail_profile=profile,
        )
        # Race floor: 30 * 0.72 = 21.6 km. Weekly cap: 35 * 0.55 = 19.25 km.
        # Continuous cap (30 km advanced): ~27.3 km. Weekly cap binds → ≥ 19 km.
        assert peak_lr >= 19.0, f"peak LR was {peak_lr} km — race floor not biting"

    def test_short_15km_at_25wk_intermediate(self):
        profile = classify_trail(15.0, 400.0)
        peak_lr = calculate_long_run_distance(
            total_km=25,
            target_distance=15.0,
            weeks=10,
            week_number=8,
            phase="peak",
            is_recovery_week=False,
            experience_level="intermediate",
            trail_profile=profile,
        )
        # Race floor: 15 * 0.65 = 9.75. Weekly cap: 25 * 0.55 = 13.75.
        # Bracket cap (short intermediate): 16. Final ≥ 9.75.
        assert peak_lr >= 9.5

    def test_ultra_50km_at_60wk_advanced(self):
        profile = classify_trail(50.0, 2000.0)
        peak_lr = calculate_long_run_distance(
            total_km=60,
            target_distance=50.0,
            weeks=20,
            week_number=16,
            phase="peak",
            is_recovery_week=False,
            experience_level="advanced",
            trail_profile=profile,
        )
        # Race floor: 50 * 0.60 = 30. Continuous cap (50 km advanced): ~34.4.
        # Weekly cap: 60 * 0.55 = 33. Final ≥ 30, ≤ 33.
        assert peak_lr >= 30.0, f"peak LR was {peak_lr} km — ultra floor missed"
        assert peak_lr <= 33.5, f"peak LR was {peak_lr} km — cap/weekly bound blown"

    def test_low_volume_runner_gets_safe_long_run(self):
        # 25 km/wk runner doing a 30 km race shouldn't be pushed past a
        # 55 % weekly slice even though the race floor is 21 km.
        profile = classify_trail(30.0, 1000.0)
        peak_lr = calculate_long_run_distance(
            total_km=25,
            target_distance=30.0,
            weeks=12,
            week_number=10,
            phase="peak",
            is_recovery_week=False,
            experience_level="intermediate",
            trail_profile=profile,
        )
        # Weekly safety cap is 25 × 0.55 = 13.75, rounded to 1dp → 13.8.
        assert peak_lr <= 13.8

    def test_long_ultra_cap_still_binds(self):
        profile = classify_trail(163.0, 6000.0)
        peak_lr = calculate_long_run_distance(
            total_km=120,
            target_distance=163.0,
            weeks=32,
            week_number=26,
            phase="peak",
            is_recovery_week=False,
            experience_level="advanced",
            trail_profile=profile,
        )
        # 100-mile prep: the continuous cap is clamped at 48 km, so even a
        # 120 km/wk runner's long run tops out at the ceiling.
        assert peak_lr <= 48.0

    def test_flat_training_peak_can_reach_85_percent_for_28k(self):
        profile = classify_trail(28.0, 1050.0)
        peak_lr = calculate_long_run_distance(
            total_km=38.0,
            target_distance=28.0,
            weeks=18,
            week_number=15,
            phase="peak",
            is_recovery_week=False,
            experience_level="intermediate",
            trail_profile=profile,
            training_terrain="flat",
        )
        # Flat-training peak floor: 28 * 0.85 = 23.8 km.
        # Weekly cap: 38 * 0.65 = 24.7 km. Standard cap: 25.5 km.
        assert peak_lr >= 23.8
        assert peak_lr <= 24.7 + 0.1


class TestKeyWorkoutDistanceMatchesSteps:
    """``workout['distance']`` matches the executable session blocks."""

    def _quality_workouts(self, plan):
        return [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
            if w["type"] in ("hill", "interval", "tempo") and w.get("steps")
        ]

    def test_trail_hilly_30km_quality_distances_reconcile(self):
        plan = _build_plan(30.0, 1200.0, 12, 5, current_km=35.0)
        for w in self._quality_workouts(plan):
            steps_total = _compute_distance_from_steps(w["steps"])
            # Allow rounding to 0.1 km — workout['distance'] is rounded to 1dp.
            assert abs(w["distance"] - steps_total) <= 0.5, (
                f"{w.get('key_workout_name', w['type'])}: "
                f"displayed {w['distance']} km vs steps sum {steps_total:.2f} km"
            )

    def test_trail_hill_workout_meets_min_floor(self):
        # Trail hill repeats need enough distance for warm-up + 6×3-min reps
        # + cool-down — the per-id floor enforces ≥ 5 km.
        plan = _build_plan(30.0, 1200.0, 12, 5, current_km=35.0)
        hills = [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
            if w["type"] == "hill"
            and w.get("key_workout_id") == "trail_elevation_repeats"
        ]
        # If selected, the floor must hold.
        for w in hills:
            assert w["distance"] >= 4.5, (
                f"trail_elevation_repeats was only {w['distance']} km — floor not applied"
            )

    def test_technical_terrain_step_has_distance(self):
        # Regression: trail_technical_terrain used to fall through to a
        # label-only step with no distance_m. New parser emits a
        # distance-bearing run step.
        plan = _build_plan(30.0, 1200.0, 14, 5, current_km=35.0)
        tech = [
            w
            for week in plan
            if week["phase"] in ("build", "peak")
            for w in week["daily_workouts"]
            if w.get("key_workout_id") == "trail_technical_terrain"
        ]
        for w in tech:
            run_steps = [s for s in w["steps"] if s["kind"] == "run"]
            assert run_steps, f"technical-terrain workout has no run step: {w['steps']}"
            assert any(s.get("distance_m") for s in run_steps), (
                f"technical-terrain main block has no distance_m: {run_steps}"
            )
