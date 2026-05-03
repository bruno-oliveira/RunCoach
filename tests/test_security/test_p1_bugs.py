"""Regression tests for P1 critical bug fixes.

P1-A: Phase collapse on short plans (< 6 weeks now raises InsufficientTimeException)
P1-B: Detraining for high-base runners (peak never forced > 10% below current base)
P1-C: Recovery-week assignment uses week-in-phase, not global week number
P1-D: 1000m repeats require 50 km/week base, not 40 km/week
"""

import pytest

from app.exceptions import InsufficientTimeException
from app.core.training.phase_calculator import (
    MIN_WEEKS_FOR_PHASES,
    calculate_phases,
    is_recovery_week,
)
from app.core.training.mileage_progression import get_peak_mileage
from app.core.training.workout_builders import generate_interval_run


# ---------------------------------------------------------------------------
# P1-A: Phase collapse on short plans
# ---------------------------------------------------------------------------

class TestPhaseCollapseGuard:
    def test_raises_for_plans_below_minimum(self):
        for weeks in range(1, MIN_WEEKS_FOR_PHASES):
            with pytest.raises(InsufficientTimeException):
                calculate_phases(weeks, target_distance=10.0)

    def test_raises_at_exactly_five_weeks(self):
        with pytest.raises(InsufficientTimeException):
            calculate_phases(5, target_distance=42.2)

    def test_succeeds_at_minimum_boundary(self):
        phases = calculate_phases(MIN_WEEKS_FOR_PHASES, target_distance=10.0)
        assert sum(phases.values()) == MIN_WEEKS_FOR_PHASES
        assert phases["peak"] >= 1
        assert phases["taper"] >= 1

    def test_all_phases_positive_at_minimum(self):
        phases = calculate_phases(MIN_WEEKS_FOR_PHASES, target_distance=21.1)
        for name, weeks in phases.items():
            assert weeks >= 1, f"Phase '{name}' collapsed to {weeks} at minimum plan length"

    def test_exception_carries_suggestion(self):
        with pytest.raises(InsufficientTimeException) as exc_info:
            calculate_phases(4, target_distance=5.0)
        assert exc_info.value.suggestion is not None
        assert str(MIN_WEEKS_FOR_PHASES) in exc_info.value.suggestion


# ---------------------------------------------------------------------------
# P1-B: Detraining for high-base runners
# ---------------------------------------------------------------------------

class TestHighBaseDetraining:
    def test_5k_high_base_not_detrained_beyond_10pct(self):
        """A 70 km/week runner targeting 5K should not be assigned < 63 km peak."""
        current_km = 70.0
        peak = get_peak_mileage(target_distance=5.0, current_km=current_km, weeks=8)
        assert peak >= current_km * 0.90, (
            f"Peak {peak:.1f} km is more than 10% below current base {current_km} km"
        )

    def test_10k_high_base_not_detrained_beyond_10pct(self):
        current_km = 60.0
        peak = get_peak_mileage(target_distance=10.0, current_km=current_km, weeks=8)
        assert peak >= current_km * 0.90

    def test_half_high_base_peak_not_forced_below_90pct(self):
        current_km = 80.0
        peak = get_peak_mileage(target_distance=21.1, current_km=current_km, weeks=12)
        assert peak >= current_km * 0.90

    def test_normal_base_unaffected(self):
        """Runners with normal base (below ideal peak) should still ramp up."""
        current_km = 20.0
        peak = get_peak_mileage(target_distance=10.0, current_km=current_km, weeks=12)
        assert peak > current_km, "Normal-base runner should ramp up, not detrain"

    def test_peak_never_below_90pct_regardless_of_distance(self):
        for dist in [5.0, 10.0, 21.1, 42.2]:
            current_km = 100.0
            peak = get_peak_mileage(target_distance=dist, current_km=current_km, weeks=16)
            assert peak >= current_km * 0.90, (
                f"dist={dist}: peak {peak:.1f} is more than 10% below base {current_km}"
            )


# ---------------------------------------------------------------------------
# P1-C: Recovery-week uses week-in-phase, not global week number
# ---------------------------------------------------------------------------

class TestRecoveryWeekPhaseRelative:
    def test_first_week_of_build_is_not_recovery(self):
        """Build starting at week 4 should not have its first week be a recovery week."""
        phases = {"base": 3, "build": 6, "peak": 2, "taper": 1}
        build_start = phases["base"] + 1  # week 4
        assert not is_recovery_week(build_start, "build", phases), (
            "First week of build phase should never be a recovery week"
        )

    def test_recovery_falls_at_4th_week_within_phase(self):
        """Recovery should occur at week_in_phase==4, i.e. the 5th week of a phase."""
        phases = {"base": 6, "build": 6, "peak": 2, "taper": 2}
        # Base starts at week 1; week_in_phase = week_number - 1
        # week_in_phase == 4 → week_number == 5
        assert is_recovery_week(5, "base", phases), "Week 5 should be recovery (4th step in base)"
        assert not is_recovery_week(4, "base", phases), "Week 4 should NOT be recovery"

    def test_build_recovery_independent_of_base_length(self):
        """Build recovery week is at 4th step into build, regardless of base length."""
        # Base=5 means build starts at week 6; recovery in build at week 6+4=10
        phases = {"base": 5, "build": 6, "peak": 2, "taper": 1}
        build_start = phases["base"] + 1  # 6
        recovery_in_build = build_start + 4  # week 10

        assert not is_recovery_week(build_start, "build", phases), \
            "Build week 1 should not be recovery"
        assert not is_recovery_week(build_start + 1, "build", phases), \
            "Build week 2 should not be recovery"
        assert not is_recovery_week(build_start + 3, "build", phases), \
            "Build week 4 should not be recovery"
        assert is_recovery_week(recovery_in_build, "build", phases), \
            f"Week {recovery_in_build} (4th step into build) should be recovery"

    def test_global_week_4_not_forced_as_build_recovery(self):
        """If build starts at week 3, global week 4 (build week 2) should not be recovery."""
        phases = {"base": 2, "build": 7, "peak": 2, "taper": 1}
        # Build starts at week 3; week 4 is build week 2 (week_in_phase=1) → not recovery
        assert not is_recovery_week(4, "build", phases), (
            "Build week 2 (global week 4) should not be recovery just because 4 % 4 == 0"
        )

    def test_short_phase_has_no_recovery(self):
        """Phases shorter than 4 weeks should have no recovery weeks."""
        phases = {"base": 3, "build": 3, "peak": 1, "taper": 1}
        for week_number in range(1, 8):
            phase = "base" if week_number <= 3 else "build"
            assert not is_recovery_week(week_number, phase, phases), (
                f"Week {week_number}: phase with <4 weeks should have no recovery"
            )

    def test_taper_never_has_recovery(self):
        phases = {"base": 4, "build": 4, "peak": 2, "taper": 2}
        for week_number in range(11, 13):
            assert not is_recovery_week(week_number, "taper", phases)


# ---------------------------------------------------------------------------
# P1-D: 1000m repeat threshold raised from 40 to 50 km/week
# ---------------------------------------------------------------------------

class TestIntervalThreshold:
    def _get_description(self, total_km: float) -> str:
        workout = generate_interval_run(day=2, distance=8.0, total_km=total_km)
        return workout["description"].lower()

    def test_40km_runner_does_not_get_1000m_repeats(self):
        """A runner at exactly 40 km/week should not receive 1000 m repeats."""
        desc = self._get_description(40.0)
        assert "1000m" not in desc, "40 km/week runner should not get 1000 m repeats"

    def test_49km_runner_does_not_get_1000m_repeats(self):
        desc = self._get_description(49.0)
        assert "1000m" not in desc, "49 km/week runner should not get 1000 m repeats"

    def test_50km_runner_gets_1000m_repeats_available(self):
        """A runner at 50 km/week crosses the threshold — 1000 m is now in the pool."""
        found_1000m = False
        for day in range(1, 8):
            desc = generate_interval_run(day=day, distance=8.0, total_km=50.0)["description"].lower()
            if "1000m" in desc:
                found_1000m = True
                break
        assert found_1000m, "At 50 km/week, 1000 m repeats should appear in the interval pool"

    def test_60km_runner_gets_harder_intervals(self):
        """High-mileage runners should get the more demanding interval menu (all 7 day variants)."""
        demanding_keywords = ["400m", "800m", "1000m", "pyramid", "yasso", "hill"]
        found = False
        for day in range(1, 8):
            desc = generate_interval_run(day=day, distance=8.0, total_km=60.0)["description"].lower()
            if any(kw in desc for kw in demanding_keywords):
                found = True
                break
        assert found, "60 km/week runner should get demanding interval formats across day variants"

    def test_low_mileage_runner_gets_shorter_intervals(self):
        """Runners below threshold get 400 m and shorter formats."""
        desc = self._get_description(30.0)
        assert "1000m" not in desc, "Low-mileage runner should not get 1000 m repeats"
        has_short = any(kw in desc for kw in ["200m", "400m", "800m", "hill"])
        assert has_short, "Low-mileage runner should get shorter interval formats"
