"""End-to-end plan generation under the parameterized trail mode.

Verifies that distance + elevation produce structurally different plans:
* Flat trail gets tempo work and zero hill repeats.
* Mountainous gets hill repeats and trims interval/track work.
* Ultra brackets get a 3-week taper.
* Long-run cap stays sane for 100-mile prep.
* Peak weekly mileage scales continuously with distance and elevation.
"""

import pytest

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.training import mileage_progression, phase_calculator
from app.core.training.long_run_calculator import (
    _get_long_run_cap,
    get_long_run_ratio_range,
)
from app.core.training.trail_profile import classify_trail


def _build_plan(distance, elevation, weeks, runs, current_km):
    profile = classify_trail(distance, elevation)
    return TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
        trail_profile=profile,
    )


class TestPhaseDistribution:
    """PHASE_DISTRIBUTIONS keys are derived from elevation class."""

    @pytest.mark.parametrize("elevation_class", ["flat", "rolling", "hilly", "mountainous"])
    def test_all_trail_buckets_present_per_phase(self, elevation_class):
        key = f"Trail{elevation_class.capitalize()}"
        for phase in ("base", "build", "peak", "taper"):
            assert key in phase_calculator.PHASE_DISTRIBUTIONS[phase]

    def test_legacy_aliases_resolve(self):
        # 'Trail' and 'FlatTrail' are kept as aliases for unmigrated callsites.
        assert (phase_calculator.PHASE_DISTRIBUTIONS['build']['Trail'] ==
                phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailHilly'])
        assert (phase_calculator.PHASE_DISTRIBUTIONS['build']['FlatTrail'] ==
                phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailFlat'])

    def test_flat_trail_replaces_hills_with_tempo(self):
        flat = phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailFlat']
        hilly = phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailHilly']
        # Flat: zero hill stimulus, more tempo than hilly baseline.
        assert flat['hill'] == 0.0
        assert flat['tempo'] > hilly['tempo']
        assert flat['interval'] >= hilly['interval']

    def test_mountainous_intensifies_hill_work(self):
        mountain = phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailMountainous']
        hilly = phase_calculator.PHASE_DISTRIBUTIONS['build']['TrailHilly']
        assert mountain['hill'] > hilly['hill']
        # Track-style intervals are partly displaced by hill repeats.
        assert mountain['interval'] <= hilly['interval']

    @pytest.mark.parametrize("elevation_class", ["flat", "rolling", "hilly", "mountainous"])
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
        assert phases['taper'] == 2

    def test_standard_bracket_2_week_taper(self):
        profile = classify_trail(30.0, 1000.0)
        phases = phase_calculator.calculate_phases(14, 30.0, trail_profile=profile)
        assert phases['taper'] == 2

    def test_ultra_bracket_3_week_taper(self):
        profile = classify_trail(50.0, 2000.0)
        phases = phase_calculator.calculate_phases(20, 50.0, trail_profile=profile)
        assert phases['taper'] == 3

    def test_long_ultra_bracket_3_week_taper(self):
        profile = classify_trail(100.0, 4000.0)
        phases = phase_calculator.calculate_phases(28, 100.0, trail_profile=profile)
        assert phases['taper'] == 3


class TestTaperCurve:
    """Ultra taper drops sharper than marathon."""

    def test_ultra_3_week_taper_more_aggressive_than_marathon(self):
        ultra_profile = classify_trail(80.0, 3000.0)
        ultra_curve = mileage_progression._get_taper_curve(3, 80.0, trail_profile=ultra_profile)
        marathon_curve = mileage_progression._get_taper_curve(3, 42.2)
        # First and last weeks: ultra trims further from peak than marathon.
        assert ultra_curve[0] <= marathon_curve[0]
        assert ultra_curve[-1] < marathon_curve[-1]


class TestPeakMileage:
    """Trail peak is continuous in distance × elevation."""

    def test_peak_scales_continuously_with_distance(self):
        # Larger distance → larger peak ceiling, all else equal.
        small = mileage_progression.get_peak_mileage(
            30.0, current_km=20, weeks=12,
            trail_profile=classify_trail(30.0, 500.0),
        )
        big = mileage_progression.get_peak_mileage(
            80.0, current_km=20, weeks=20,
            trail_profile=classify_trail(80.0, 500.0),
        )
        assert big > small

    def test_peak_scales_with_elevation(self):
        flat = mileage_progression.get_peak_mileage(
            50.0, current_km=30, weeks=16,
            trail_profile=classify_trail(50.0, 200.0),
        )
        mountain = mileage_progression.get_peak_mileage(
            50.0, current_km=30, weeks=16,
            trail_profile=classify_trail(50.0, 3000.0),
        )
        assert mountain >= flat  # mountain ceiling is higher

    def test_peak_clamps_at_140km(self):
        peak = mileage_progression.get_peak_mileage(
            163.0, current_km=80, weeks=32,
            trail_profile=classify_trail(163.0, 8000.0),
        )
        assert peak <= 140.0


class TestLongRunRatios:
    """Ultra brackets pull a higher long-run share."""

    def test_ultra_long_run_ratio_higher_than_standard(self):
        std_lo, std_hi = get_long_run_ratio_range(
            'build', 30.0, 14, trail_profile=classify_trail(30.0, 1000.0),
        )
        ultra_lo, ultra_hi = get_long_run_ratio_range(
            'build', 50.0, 20, trail_profile=classify_trail(50.0, 1500.0),
        )
        assert ultra_hi >= std_hi


class TestLongRunCap:
    """Long-run cap stays sane for ultras (≤ 35 km even for 100mi)."""

    def test_long_ultra_cap_does_not_blow_past_35km(self):
        profile = classify_trail(163.0, 6000.0)
        cap = _get_long_run_cap(163.0, 'advanced', weekly_km=120.0, trail_profile=profile)
        assert cap <= 35.0

    def test_short_bracket_cap_is_modest(self):
        profile = classify_trail(15.0, 500.0)
        cap = _get_long_run_cap(15.0, 'intermediate', weekly_km=30.0, trail_profile=profile)
        assert cap <= 18.0


class TestEndToEnd:
    """Full plan generation for representative trail scenarios."""

    def test_50km_flat_plan_generates_with_tempo(self):
        plan = _build_plan(50.0, 200.0, 16, 5, current_km=40.0)
        assert len(plan) == 16
        # Build/peak weeks contain at least one tempo session
        build_peak_workouts = [
            w for week in plan
            if week['phase'] in ('build', 'peak')
            for w in week['daily_workouts']
        ]
        assert any(w['type'] == 'tempo' for w in build_peak_workouts), \
            "Flat 50k build/peak must include tempo sessions"
        # And no hill repeats anywhere
        all_workouts = [w for week in plan for w in week['daily_workouts']]
        assert not any(w['type'] == 'hill' for w in all_workouts), \
            "Flat trail must not prescribe hill repeats"

    def test_80km_mountain_plan_includes_hills(self):
        plan = _build_plan(80.0, 4500.0, 24, 6, current_km=50.0)
        all_workouts = [w for week in plan for w in week['daily_workouts']]
        assert any(w['type'] == 'hill' for w in all_workouts), \
            "Mountainous plan must include hill repeats"

    def test_100mi_plan_long_run_capped(self):
        plan = _build_plan(163.0, 6000.0, 32, 6, current_km=80.0)
        long_runs = [w for week in plan for w in week['daily_workouts'] if w['type'] == 'long']
        max_long = max(w['distance'] for w in long_runs)
        # Long-run cap should keep individual sessions under ~35 km.
        assert max_long <= 36.0, f"Single long run was {max_long} km — cap blown"

    def test_ultra_plan_has_3_week_taper(self):
        plan = _build_plan(50.0, 1500.0, 16, 5, current_km=30.0)
        taper_weeks = [w for w in plan if w['phase'] == 'taper']
        assert len(taper_weeks) == 3

    def test_legacy_30km_plan_unchanged_structure(self):
        # No is_trail / no profile passed, but target=30.0 → back-compat path.
        plan = TrainingPlanGenerator().generate_plan(
            current_km=25.0, target_distance=30.0, weeks=12, max_runs_per_week=4,
        )
        assert len(plan) == 12
        # Should have hill repeats (legacy default elevation=1000m → hilly bucket).
        all_workouts = [w for week in plan for w in week['daily_workouts']]
        assert any(w['type'] == 'hill' for w in all_workouts)
