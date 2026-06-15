"""Tests for the pace<->heart-rate calibration."""

from app.core.training.hr_pace_calibration import (
    PaceHRModel,
    PaceHRSample,
    attach_calibrated_paces,
    fit_pace_hr_model,
)


def _linear_samples(intercept: float, slope: float, paces: list[float]):
    """Build samples lying exactly on hr = intercept + slope * speed(km/h)."""
    samples = []
    for pace in paces:
        speed = 60.0 / pace
        samples.append(PaceHRSample(pace_min_km=pace, hr=intercept + slope * speed))
    return samples


# A spread of paces from easy (6:00/km) to fast (3:30/km).
_PACE_SPREAD = [6.0, 5.5, 5.0, 4.5, 4.0, 3.75, 3.5, 3.4]


class TestFit:
    def test_fits_clean_linear_data(self):
        samples = _linear_samples(intercept=60.0, slope=8.0, paces=_PACE_SPREAD)
        model = fit_pace_hr_model(samples)
        assert model is not None
        assert abs(model.slope - 8.0) < 1e-6
        assert abs(model.intercept - 60.0) < 1e-6
        assert model.r > 0.99
        assert model.n == len(_PACE_SPREAD)

    def test_too_few_samples_returns_none(self):
        samples = _linear_samples(60.0, 8.0, [6.0, 5.0, 4.0])
        assert fit_pace_hr_model(samples) is None

    def test_no_intensity_spread_returns_none(self):
        # All samples at ~the same pace: no slope can be trusted.
        samples = _linear_samples(60.0, 8.0, [5.0] * 10)
        assert fit_pace_hr_model(samples) is None

    def test_flat_relationship_returns_none(self):
        # HR identical regardless of pace -> non-positive slope, rejected.
        samples = [PaceHRSample(pace_min_km=p, hr=150) for p in _PACE_SPREAD]
        assert fit_pace_hr_model(samples) is None

    def test_noisy_uncorrelated_returns_none(self):
        # HR unrelated to pace (alternating high/low) -> low correlation.
        samples = [
            PaceHRSample(pace_min_km=p, hr=130 if i % 2 == 0 else 170)
            for i, p in enumerate(_PACE_SPREAD * 2)
        ]
        assert fit_pace_hr_model(samples) is None

    def test_implausible_samples_filtered_out(self):
        good = _linear_samples(60.0, 8.0, _PACE_SPREAD)
        junk = [
            PaceHRSample(pace_min_km=20.0, hr=150),  # walking pace
            PaceHRSample(pace_min_km=1.0, hr=150),  # impossibly fast
            PaceHRSample(pace_min_km=5.0, hr=10),  # sensor dropout
            PaceHRSample(pace_min_km=5.0, hr=300),  # sensor spike
        ]
        model = fit_pace_hr_model(good + junk)
        assert model is not None
        assert model.n == len(good)  # junk excluded


class TestPredict:
    def test_predict_hr_and_pace_are_inverses(self):
        model = fit_pace_hr_model(_linear_samples(60.0, 8.0, _PACE_SPREAD))
        assert model is not None
        hr = model.predict_hr(5.0)
        assert abs(model.predict_pace(hr) - 5.0) < 1e-6

    def test_faster_pace_predicts_higher_hr(self):
        model = fit_pace_hr_model(_linear_samples(60.0, 8.0, _PACE_SPREAD))
        assert model is not None
        assert model.predict_hr(4.0) > model.predict_hr(6.0)

    def test_predict_pace_below_floor_returns_none(self):
        model = PaceHRModel(
            slope=8.0,
            intercept=60.0,
            r=0.99,
            n=10,
            speed_min_kmh=10.0,
            speed_max_kmh=17.0,
        )
        # HR below the intercept implies non-positive speed.
        assert model.predict_pace(50.0) is None


class TestAttachCalibratedPaces:
    def _zones(self):
        # A simplified 3-zone shape mirroring HRZoneCalculator output.
        return [
            {"zone": 1, "name": "Recovery", "min_bpm": 120, "max_bpm": 140},
            {"zone": 2, "name": "Aerobic", "min_bpm": 140, "max_bpm": 160},
            {"zone": 3, "name": "Tempo", "min_bpm": 160, "max_bpm": 175},
        ]

    def test_attaches_pace_band_per_zone(self):
        model = fit_pace_hr_model(_linear_samples(60.0, 8.0, _PACE_SPREAD))
        assert model is not None
        zones = attach_calibrated_paces(self._zones(), model)
        for z in zones:
            assert z["pace_calibrated"] is True
            assert z["pace_min_km"] is not None
            assert z["pace_max_km"] is not None
            assert z["pace_range_formatted"]

    def test_higher_zone_maps_to_faster_pace(self):
        model = fit_pace_hr_model(_linear_samples(60.0, 8.0, _PACE_SPREAD))
        assert model is not None
        zones = attach_calibrated_paces(self._zones(), model)
        # Higher zone -> higher HR -> faster pace -> lower min/km number.
        assert zones[0]["pace_max_km"] > zones[2]["pace_max_km"]

    def test_extrapolation_flagged_outside_observed_range(self):
        # Observed HR span is narrow; a zone well above it is extrapolated.
        model = PaceHRModel(
            slope=8.0,
            intercept=60.0,
            r=0.99,
            n=10,
            speed_min_kmh=10.0,  # hr 140
            speed_max_kmh=12.5,  # hr 160
        )
        zones = attach_calibrated_paces(self._zones(), model)
        z_high = next(z for z in zones if z["zone"] == 3)  # 160-175, above span
        assert z_high["pace_extrapolated"] is True
        z_mid = next(z for z in zones if z["zone"] == 2)  # 140-160, within span
        assert z_mid["pace_extrapolated"] is False
