"""Watch-based readiness: each morning judged against the runner's own normal."""

from datetime import date, timedelta

from app.core.coaching.readiness_checkin import score_checkin
from app.core.coaching.wellness import (
    MIN_BASELINE_DAYS,
    WEARABLE_NEUTRAL_SCORE,
    baseline,
    markers,
    objective_delta,
    sleep_hours_from_seconds,
    wearable_score,
)

TODAY = date(2026, 9, 24)


def _history(hrv: float, rhr: float, days: int = 14):
    return [(TODAY - timedelta(days=d), hrv, rhr) for d in range(1, days + 1)]


def test_no_baseline_until_enough_mornings():
    """A new connection gets its first verdict about a week in, not a guess."""
    short = _history(60, 50, days=MIN_BASELINE_DAYS - 1)
    base = baseline(short, TODAY)
    assert base.hrv is None and base.resting_hr is None
    assert baseline(_history(60, 50, days=MIN_BASELINE_DAYS), TODAY).hrv == 60


def test_today_never_softens_its_own_baseline():
    history = _history(60, 50) + [(TODAY, 20.0, 70.0)]
    assert baseline(history, TODAY).hrv == 60


def test_baseline_ignores_mornings_outside_the_window():
    old = [(TODAY - timedelta(days=40 + d), 20.0, 80.0) for d in range(10)]
    base = baseline(_history(60, 50) + old, TODAY)
    assert base.hrv == 60 and base.resting_hr == 50


def test_normal_morning_is_neutral():
    m = markers(
        hrv=61, resting_hr=50, sleep_hours=7.5, base=baseline(_history(60, 50), TODAY)
    )
    verdict = objective_delta(m, include_sleep=False)
    assert verdict.delta == 0
    assert verdict.drivers == []


def test_suppressed_hrv_and_raised_rhr_pull_readiness_down_with_reasons():
    m = markers(
        hrv=48, resting_hr=57, sleep_hours=7, base=baseline(_history(60, 50), TODAY)
    )
    verdict = objective_delta(m, include_sleep=False)
    assert verdict.delta < -20
    assert "your HRV is 20% below your usual" in verdict.drivers
    assert "your resting HR is up 7 bpm" in verdict.drivers


def test_wearable_only_score_is_centred_just_above_the_engine_neutral():
    """A normal watch morning must neither inflate nor deflate the plan."""
    m = markers(
        hrv=60, resting_hr=50, sleep_hours=6.5, base=baseline(_history(60, 50), TODAY)
    )
    assert wearable_score(m) == WEARABLE_NEUTRAL_SCORE


def test_wearable_score_is_none_without_any_signal():
    m = markers(hrv=None, resting_hr=None, sleep_hours=None, base=baseline([], TODAY))
    assert wearable_score(m) is None


def test_checkin_leads_and_the_watch_nudges_at_half_weight():
    base = baseline(_history(60, 50), TODAY)
    felt = score_checkin(energy=5, sleep_quality=5, soreness=1)
    rough_watch = markers(hrv=45, resting_hr=58, sleep_hours=None, base=base)
    blended = score_checkin(
        energy=5, sleep_quality=5, soreness=1, objective=rough_watch
    )
    full = objective_delta(rough_watch, include_sleep=False).delta
    assert blended.score == round(felt.score + 0.5 * full, 1)
    assert any("HRV" in d for d in blended.drivers)


def test_sleep_is_not_counted_twice_when_the_runner_reported_it():
    base = baseline(_history(60, 50), TODAY)
    watch = markers(hrv=60, resting_hr=50, sleep_hours=4.0, base=base)
    with_watch = score_checkin(sleep_hours=4.0, energy=3, objective=watch)
    without = score_checkin(sleep_hours=4.0, energy=3)
    assert with_watch.score == without.score


def test_watch_alone_scores_a_morning_with_no_checkin():
    base = baseline(_history(60, 50), TODAY)
    watch = markers(hrv=40, resting_hr=60, sleep_hours=4.5, base=base)
    assessment = score_checkin(objective=watch)
    assert assessment.score is not None and assessment.is_low
    assert "you slept 4.5h" in assessment.drivers


def test_sleep_seconds_conversion_drops_junk():
    assert sleep_hours_from_seconds(27000) == 7.5
    assert sleep_hours_from_seconds(0) is None
    assert sleep_hours_from_seconds("nope") is None
    assert sleep_hours_from_seconds(None) is None
