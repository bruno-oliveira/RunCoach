"""Tests for environmental (heat/altitude) performance adjustments."""

import pytest

from app.core.training.environment import (
    EnvironmentalConditions,
    altitude_vdot_factor,
    dew_point_c,
    heat_pace_factor,
)
from app.core.training.race_predictor import predict_time_for_distance


class TestDewPoint:
    def test_saturated_air_equals_temperature(self):
        # At 100% humidity the dew point equals the air temperature.
        assert dew_point_c(20.0, 100.0) == pytest.approx(20.0, abs=0.2)

    def test_drier_air_lowers_dew_point(self):
        assert dew_point_c(25.0, 40.0) < dew_point_c(25.0, 90.0)

    def test_zero_humidity_is_clamped_not_crashing(self):
        # Humidity of 0 would blow up the logarithm; it must be clamped.
        value = dew_point_c(20.0, 0.0)
        assert value < 20.0


class TestHeatPaceFactor:
    def test_neutral_below_threshold(self):
        assert heat_pace_factor(5.0) == 1.0
        assert heat_pace_factor(10.0) == 1.0

    def test_monotonic_increase(self):
        factors = [heat_pace_factor(dp) for dp in (12, 16, 19, 22, 25, 28)]
        assert factors == sorted(factors)
        assert all(f >= 1.0 for f in factors)

    def test_capped_at_max(self):
        assert heat_pace_factor(40.0) == pytest.approx(1.12)

    def test_interpolates_between_anchors(self):
        # Halfway between the 18C (2%) and 21C (4%) anchors -> ~3%.
        assert heat_pace_factor(19.5) == pytest.approx(1.03, abs=0.005)


class TestAltitudeVdotFactor:
    def test_neutral_at_sea_level(self):
        assert altitude_vdot_factor(0.0) == 1.0
        assert altitude_vdot_factor(1000.0) == 1.0

    def test_declines_with_altitude(self):
        # 2000 m -> 1000 m above the neutral band -> ~6% loss.
        assert altitude_vdot_factor(2000.0) == pytest.approx(0.94)
        assert altitude_vdot_factor(3000.0) == pytest.approx(0.88)

    def test_floored(self):
        assert altitude_vdot_factor(9000.0) == pytest.approx(0.75)


class TestEnvironmentalConditions:
    def test_empty_inputs_return_none(self):
        assert EnvironmentalConditions.from_inputs() is None
        # Cool and at sea level moves nothing -> treated as empty.
        assert (
            EnvironmentalConditions.from_inputs(
                temp_c=8.0, humidity_pct=50.0, altitude_m=200.0
            )
            is None
        )

    def test_heat_only(self):
        cond = EnvironmentalConditions.from_inputs(temp_c=30.0, humidity_pct=80.0)
        assert cond is not None
        assert cond.has_heat
        assert not cond.has_altitude
        assert cond.pace_factor() > 1.0
        assert cond.vdot_factor() == 1.0

    def test_altitude_only(self):
        cond = EnvironmentalConditions.from_inputs(altitude_m=2500.0)
        assert cond is not None
        assert cond.has_altitude
        assert not cond.has_heat
        assert cond.vdot_factor() < 1.0
        assert cond.pace_factor() == 1.0

    def test_explicit_dew_point_overrides_derivation(self):
        cond = EnvironmentalConditions.from_inputs(dew_point=22.0)
        assert cond is not None
        assert cond.pace_factor() == pytest.approx(heat_pace_factor(22.0))

    def test_coaching_note_mentions_both(self):
        cond = EnvironmentalConditions.from_inputs(
            temp_c=30.0, humidity_pct=85.0, altitude_m=2500.0
        )
        assert cond is not None
        note = cond.coaching_note()
        assert note is not None
        assert "Heat" in note and "Altitude" in note


class TestPredictionIntegration:
    VDOT = 50.0
    DISTANCE = 21.0975  # half marathon

    def test_hot_race_is_slower(self):
        base = predict_time_for_distance(self.VDOT, self.DISTANCE)
        hot = predict_time_for_distance(
            self.VDOT,
            self.DISTANCE,
            conditions=EnvironmentalConditions.from_inputs(
                temp_c=30.0, humidity_pct=85.0
            ),
        )
        assert base is not None and hot is not None
        assert hot > base

    def test_altitude_race_is_slower(self):
        base = predict_time_for_distance(self.VDOT, self.DISTANCE)
        high = predict_time_for_distance(
            self.VDOT,
            self.DISTANCE,
            conditions=EnvironmentalConditions.from_inputs(altitude_m=2500.0),
        )
        assert base is not None and high is not None
        assert high > base

    def test_no_conditions_matches_baseline(self):
        base = predict_time_for_distance(self.VDOT, self.DISTANCE)
        explicit_none = predict_time_for_distance(
            self.VDOT, self.DISTANCE, conditions=None
        )
        assert base == explicit_none
