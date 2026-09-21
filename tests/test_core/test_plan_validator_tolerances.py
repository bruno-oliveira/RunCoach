"""Tests for the configurable validator tolerance.

The weekly volume tolerance in ``validate_week_plan`` used to be a bare
``target * 0.05`` literal. It is now a frozen :class:`ValidatorTolerance`
with defaults that reproduce the old behaviour exactly, so future callers
(waves that clamp weekly targets to a capacity ceiling) can widen it
without the validator silently failing over-clamped weeks.
"""

import pytest

from app.contexts.plan.generators.plan_validator import (
    CLAMPED_TARGET_TOLERANCE,
    DEFAULT_TOLERANCE,
    ValidatorTolerance,
    validate_week_plan,
)


def _valid_week(total_km: float) -> tuple[list[dict], float]:
    """A structurally sound week whose delivered volume is ``total_km``.

    Long run + one easy run + two recovery days: enough to pass every
    structural check so the tests below exercise *only* the volume band.
    """
    return (
        [
            {
                "day": 1,
                "type": "recovery",
                "description": "Rest",
                "distance": 0.0,
            },
            {
                "day": 2,
                "type": "easy",
                "description": "Easy run",
                "distance": round(total_km * 0.2, 1),
            },
            {
                "day": 3,
                "type": "recovery",
                "description": "Rest",
                "distance": 0.0,
            },
            {
                "day": 6,
                "type": "long",
                "description": "Long run",
                "distance": round(total_km * 0.8, 1),
            },
        ],
        total_km,
    )


class TestAllowedDeviation:
    def test_default_is_five_percent_relative_only(self):
        assert DEFAULT_TOLERANCE.allowed_deviation_km(100.0) == pytest.approx(5.0)

    def test_absolute_band_adds_flat_km(self):
        t = ValidatorTolerance(absolute_km=2.0, relative=0.15)
        assert t.allowed_deviation_km(60.0) == pytest.approx(11.0)

    def test_absolute_band_dominates_on_tiny_targets(self):
        t = ValidatorTolerance(absolute_km=2.0, relative=0.15)
        assert t.allowed_deviation_km(0.0) == pytest.approx(2.0)

    def test_negative_target_uses_magnitude(self):
        assert DEFAULT_TOLERANCE.allowed_deviation_km(-100.0) == pytest.approx(5.0)


class TestDefaultBehaviourUnchanged:
    def test_within_five_percent_passes(self):
        workouts, delivered = _valid_week(96.0)
        ok, msg = validate_week_plan(workouts, delivered, 100.0, "base")
        assert ok, msg

    def test_beyond_five_percent_fails(self):
        workouts, delivered = _valid_week(94.0)
        ok, msg = validate_week_plan(workouts, delivered, 100.0, "base")
        assert not ok
        assert "Total distance mismatch" in msg

    def test_explicit_default_constant_matches_implicit_default(self):
        workouts, delivered = _valid_week(94.0)
        implicit = validate_week_plan(workouts, delivered, 100.0, "base")
        explicit = validate_week_plan(
            workouts, delivered, 100.0, "base", tolerance=DEFAULT_TOLERANCE
        )
        assert implicit == explicit

    def test_structural_checks_independent_of_tolerance(self):
        workouts, _ = _valid_week(100.0)
        workouts[0]["type"] = "recovery_rest"
        ok, msg = validate_week_plan(
            workouts, 100.0, 100.0, "base", tolerance=CLAMPED_TARGET_TOLERANCE
        )
        assert not ok
        assert "recovery_rest" in msg


class TestToleranceDirection:
    def test_looser_tolerance_passes_what_default_rejects(self):
        workouts, delivered = _valid_week(94.0)  # 6% off — default rejects
        loose = ValidatorTolerance(absolute_km=0.0, relative=0.10)
        ok, msg = validate_week_plan(
            workouts, delivered, 100.0, "base", tolerance=loose
        )
        assert ok, msg

    def test_tighter_tolerance_rejects_what_default_accepts(self):
        workouts, delivered = _valid_week(96.0)  # 4% off — default accepts
        tight = ValidatorTolerance(absolute_km=0.0, relative=0.01)
        ok, msg = validate_week_plan(
            workouts, delivered, 100.0, "base", tolerance=tight
        )
        assert not ok
        assert "Total distance mismatch" in msg

    def test_absolute_band_admits_proportionally_huge_gap(self):
        # 10% off on a small week: pure-relative default rejects, a flat
        # 5 km band accepts (the gap is rounding-scale in absolute terms).
        workouts, delivered = _valid_week(22.0)
        ok_default, _ = validate_week_plan(workouts, delivered, 20.0, "base")
        assert not ok_default
        flat = ValidatorTolerance(absolute_km=5.0, relative=0.0)
        ok_flat, msg = validate_week_plan(
            workouts, delivered, 20.0, "base", tolerance=flat
        )
        assert ok_flat, msg


class TestClampedTargetTolerance:
    def test_admits_week_clamped_well_below_model_target(self):
        # Capacity ceiling delivered 24 of the 30 km the model asked for
        # (20% short) — impossible by design, passes with the clamp-aware
        # band and fails with the default one.
        workouts, delivered = _valid_week(24.0)
        ok_default, _ = validate_week_plan(workouts, delivered, 30.0, "base")
        assert not ok_default
        ok_clamped, msg = validate_week_plan(
            workouts, delivered, 30.0, "base", tolerance=CLAMPED_TARGET_TOLERANCE
        )
        assert ok_clamped, msg

    def test_still_rejects_grossly_short_delivery(self):
        workouts, delivered = _valid_week(10.0)  # 67% short of 30 km
        ok, msg = validate_week_plan(
            workouts, delivered, 30.0, "base", tolerance=CLAMPED_TARGET_TOLERANCE
        )
        assert not ok
        assert "Total distance mismatch" in msg
