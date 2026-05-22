"""Tests for the coaching feedback engine."""

from datetime import datetime
from unittest.mock import MagicMock

from app.core.coaching.coaching_feedback_engine import CoachingFeedbackEngine
from app.core.coaching.hr_feedback import hr_zone_feedback
from app.core.coaching.pace_feedback import pace_feedback
from app.core.coaching.sentiment_classifier import determine_sentiment
from app.core.training.hr_zone_calculator import HRZoneCalculator


def _make_run_log(**kwargs):
    """Create a mock RunLog with sensible defaults."""
    defaults = {
        "id": "run-1",
        "user_id": "user-1",
        "training_plan_id": None,
        "daily_workout_id": None,
        "date": datetime(2025, 6, 15, tzinfo=None),
        "distance_km": 10.0,
        "duration_minutes": 55.0,
        "avg_pace_min_km": 5.5,
        "avg_heart_rate": None,
        "max_heart_rate": None,
        "perceived_effort": None,
        "workout_type": "easy",
        "planned_pace_min_km": None,
    }
    defaults.update(kwargs)
    run = MagicMock()
    for k, v in defaults.items():
        setattr(run, k, v)
    return run


def _make_planned_workout(**kwargs):
    """Create a mock DailyWorkout."""
    defaults = {
        "id": "dw-1",
        "workout_type": "easy",
        "planned_pace_min_km": 5.5,
        "hr_zone_target": 2,
    }
    defaults.update(kwargs)
    workout = MagicMock()
    for k, v in defaults.items():
        setattr(workout, k, v)
    return workout


class TestPaceFeedback:
    def test_on_target(self):
        run = _make_run_log(avg_pace_min_km=5.5)
        planned = _make_planned_workout(planned_pace_min_km=5.5)
        fb = pace_feedback(run, planned)
        assert fb is not None
        assert "right on target" in fb.lower() or "on target" in fb.lower()

    def test_too_fast_easy_run(self):
        run = _make_run_log(avg_pace_min_km=4.8, workout_type="easy")
        planned = _make_planned_workout(planned_pace_min_km=5.5, workout_type="easy")
        fb = pace_feedback(run, planned)
        assert fb is not None
        assert "slow down" in fb.lower() or "faster" in fb.lower()

    def test_too_slow(self):
        run = _make_run_log(avg_pace_min_km=6.5)
        planned = _make_planned_workout(planned_pace_min_km=5.5)
        fb = pace_feedback(run, planned)
        assert fb is not None
        assert "slower" in fb.lower()

    def test_no_planned_pace_returns_none(self):
        run = _make_run_log(avg_pace_min_km=5.5)
        planned = _make_planned_workout(planned_pace_min_km=None)
        fb = pace_feedback(run, planned)
        assert fb is None

    def test_no_planned_workout_returns_none(self):
        run = _make_run_log(avg_pace_min_km=5.5)
        fb = pace_feedback(run, None)
        assert fb is None


class TestHRZoneFeedback:
    def setup_method(self):
        self.zones = HRZoneCalculator.calculate_zones(190)

    def test_in_target_zone(self):
        # Zone 2 for easy run: ~114-133 bpm (190 max)
        run = _make_run_log(avg_heart_rate=125, workout_type="easy")
        planned = _make_planned_workout(hr_zone_target=2)
        fb = hr_zone_feedback(run, planned, self.zones)
        assert fb is not None
        assert "target zone" in fb.lower() or "well paced" in fb.lower()

    def test_too_high(self):
        # HR 175 should be Zone 5 for a 190 max
        run = _make_run_log(avg_heart_rate=175, workout_type="easy")
        planned = _make_planned_workout(hr_zone_target=2)
        fb = hr_zone_feedback(run, planned, self.zones)
        assert fb is not None
        assert "above" in fb.lower() or "higher" in fb.lower() or "high" in fb.lower()

    def test_no_hr_data_returns_none(self):
        run = _make_run_log(avg_heart_rate=None)
        planned = _make_planned_workout(hr_zone_target=2)
        fb = hr_zone_feedback(run, planned, self.zones)
        assert fb is None


class TestEffortFeedback:
    def test_nailed_it(self):
        run = _make_run_log(perceived_effort=4, avg_pace_min_km=5.5)
        planned = _make_planned_workout(planned_pace_min_km=5.5, workout_type="easy")
        fb = CoachingFeedbackEngine._effort_feedback(run, planned)
        assert fb is not None
        assert "nailed" in fb.lower() or "on track" in fb.lower()

    def test_too_hard(self):
        run = _make_run_log(perceived_effort=9, avg_pace_min_km=5.5)
        planned = _make_planned_workout(planned_pace_min_km=5.5, workout_type="easy")
        fb = CoachingFeedbackEngine._effort_feedback(run, planned)
        assert fb is not None
        assert "hard" in fb.lower()

    def test_no_effort_returns_none(self):
        run = _make_run_log(perceived_effort=None)
        fb = CoachingFeedbackEngine._effort_feedback(run, None)
        assert fb is None


class TestSentiment:
    def test_positive_sentiment(self):
        fb = {
            "pace_feedback": "Pace was right on target. Great execution!",
            "hr_zone_feedback": None,
            "effort_feedback": "Nailed it!",
            "volume_feedback": None,
            "pattern_feedback": None,
        }
        assert determine_sentiment(fb) == "positive"

    def test_warning_sentiment(self):
        fb = {
            "pace_feedback": "Your easy run was faster than planned.",
            "hr_zone_feedback": None,
            "effort_feedback": None,
            "volume_feedback": None,
            "pattern_feedback": "Pattern detected: too fast",
        }
        assert determine_sentiment(fb) == "warning"

    def test_info_when_empty(self):
        fb = {
            "pace_feedback": None,
            "hr_zone_feedback": None,
            "effort_feedback": None,
            "volume_feedback": None,
            "pattern_feedback": None,
        }
        assert determine_sentiment(fb) == "info"


class TestFullFeedbackGeneration:
    def test_generates_without_crash(self):
        """Integration-style test: generate feedback with minimal data."""
        run = _make_run_log(
            avg_pace_min_km=5.5,
            perceived_effort=5,
            avg_heart_rate=130,
        )
        planned = _make_planned_workout(
            planned_pace_min_km=5.5,
            hr_zone_target=2,
        )
        zones = HRZoneCalculator.calculate_zones(190)
        db = MagicMock()

        fb = CoachingFeedbackEngine.generate_feedback(run, planned, zones, db)

        assert "pace_feedback" in fb
        assert "hr_zone_feedback" in fb
        assert "effort_feedback" in fb
        assert "overall_sentiment" in fb
        assert fb["overall_sentiment"] in ("positive", "warning", "info")
