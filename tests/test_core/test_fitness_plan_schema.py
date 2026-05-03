"""Tests for FitnessPlanRequest schema."""

import pytest
from pydantic import ValidationError

from app.schemas import FitnessPlanRequest


class TestFitnessPlanRequest:
    """Tests for FitnessPlanRequest validation."""

    def test_valid_request(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )
        assert req.current_km == 25.0
        assert req.weeks == 8
        assert req.runs_per_week == 4
        assert req.focus_area == "vo2max"

    def test_valid_threshold_focus(self):
        req = FitnessPlanRequest(
            current_km=30.0,
            weeks=10,
            runs_per_week=5,
            focus_area="threshold",
        )
        assert req.focus_area == "threshold"

    def test_valid_balanced_focus(self):
        req = FitnessPlanRequest(
            current_km=20.0,
            weeks=6,
            runs_per_week=3,
            focus_area="balanced",
        )
        assert req.focus_area == "balanced"

    def test_invalid_focus_area(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=4,
                focus_area="invalid",
            )

    def test_current_km_below_minimum(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=5.0,
                weeks=8,
                runs_per_week=4,
                focus_area="vo2max",
            )

    def test_weeks_below_minimum(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=4,
                runs_per_week=4,
                focus_area="vo2max",
            )

    def test_weeks_above_maximum(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=16,
                runs_per_week=4,
                focus_area="vo2max",
            )

    def test_runs_per_week_below_minimum(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=2,
                focus_area="vo2max",
            )

    def test_runs_per_week_above_maximum(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=7,
                focus_area="vo2max",
            )

    def test_valid_focus_distance(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            focus_distance=10.0,
        )
        assert req.focus_distance == 10.0

    def test_invalid_focus_distance(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=4,
                focus_area="vo2max",
                focus_distance=15.0,
            )

    def test_vdot_computed_from_race(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            recent_race_distance_km=10.0,
            recent_race_time="45:00",
        )
        assert req.vdot is not None
        assert req.vdot > 0

    def test_invalid_race_time_format(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=4,
                focus_area="vo2max",
                recent_race_distance_km=10.0,
                recent_race_time="invalid",
            )

    def test_max_heart_rate_valid(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            max_heart_rate=185,
        )
        assert req.max_heart_rate == 185

    def test_max_heart_rate_too_low(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=4,
                focus_area="vo2max",
                max_heart_rate=100,
            )

    def test_body_weight_valid(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
            body_weight_kg=80.0,
        )
        assert req.body_weight_kg == 80.0

    def test_body_weight_too_low(self):
        with pytest.raises(ValidationError):
            FitnessPlanRequest(
                current_km=25.0,
                weeks=8,
                runs_per_week=4,
                focus_area="vo2max",
                body_weight_kg=20.0,
            )

    def test_defaults(self):
        req = FitnessPlanRequest(
            current_km=25.0,
            weeks=8,
            runs_per_week=4,
            focus_area="vo2max",
        )
        assert req.body_weight_kg == 70.0
        assert req.focus_area == "vo2max"
        assert req.focus_distance is None
        assert req.max_heart_rate is None
