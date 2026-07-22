"""Tests for the pure readiness check-in scorer (core/coaching/readiness_checkin)."""

from app.core.coaching.readiness_checkin import ReadinessAssessment, score_checkin


def test_empty_checkin_scores_nothing():
    a = score_checkin()
    assert a.score is None
    assert a.band == "unknown"
    assert a.is_low is False
    assert a.is_high is False


def test_great_morning_is_primed():
    a = score_checkin(sleep_hours=8, sleep_quality=5, energy=5, soreness=1, stress=1)
    assert a.score == 100.0
    assert a.band == "primed"
    assert a.is_high is True
    assert a.drivers == []


def test_wrecked_morning_is_low_with_drivers():
    a = score_checkin(sleep_hours=5, sleep_quality=2, energy=2, soreness=4, stress=3)
    assert a.is_low is True
    assert a.band in ("run_down", "depleted")
    # Concrete drivers the coaching voice can weave in.
    assert "you slept 5h" in a.drivers
    assert "your legs are heavy" in a.drivers
    assert "your energy is low" in a.drivers


def test_partial_capture_still_scores():
    # Just "slept badly, legs sore" — a 15-second capture.
    a = score_checkin(sleep_hours=4, soreness=5)
    assert a.score is not None
    assert a.is_low is True


def test_soreness_and_stress_are_inverted():
    fresh = score_checkin(soreness=1, stress=1)
    wrecked = score_checkin(soreness=5, stress=5)
    assert fresh.score is not None and wrecked.score is not None
    assert fresh.score > wrecked.score


def test_score_is_bounded_0_100():
    for a in (
        score_checkin(sleep_hours=0, sleep_quality=1, energy=1, soreness=5, stress=5),
        score_checkin(sleep_hours=12, sleep_quality=5, energy=5, soreness=1, stress=1),
    ):
        assert a.score is not None
        assert 0.0 <= a.score <= 100.0


def test_band_thresholds_are_monotonic():
    scores = [
        score_checkin(sleep_quality=q, energy=q, soreness=6 - q, stress=6 - q).score
        for q in (1, 2, 3, 4, 5)
    ]
    assert scores == sorted(scores)


def test_assessment_is_frozen_dataclass():
    a = score_checkin(energy=3)
    assert isinstance(a, ReadinessAssessment)
