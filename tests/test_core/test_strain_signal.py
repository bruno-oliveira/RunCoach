"""The multi-day wellness strain detector.

One morning judged against a 28-day median is a readiness reading; a *run* of
them is a pattern. These tests pin the difference, and the two honesty rules
that keep the run from overclaiming: a data gap ends it, and a verdict needs a
baseline to exist first.
"""

from datetime import date, timedelta
from typing import List, Optional, Tuple

import pytest

from app.core.coaching.strain_signal import (
    OFF_MORNING_DELTA,
    STRAIN_LOOKBACK_DAYS,
    STRAIN_STREAK_DAYS,
    StrainVerdict,
    detect_strain,
)

TODAY = date(2026, 6, 1)

NORMAL_HRV = 60.0
NORMAL_RHR = 50.0
# ratio 0.90 -> the first negative HRV band (-8.0): off, but only just.
MILD_HRV = 54.0
# ratio 0.80 -> the third band (-16.0).
SEVERE_HRV = 48.0

Point = Tuple[date, Optional[float], Optional[float]]


def _normal_block(end: date, days: int = 24) -> List[Point]:
    """``days`` consecutive unremarkable mornings ending at ``end``."""
    return [
        (end - timedelta(days=days - 1 - i), NORMAL_HRV, NORMAL_RHR)
        for i in range(days)
    ]


def _tail(days: int, hrv: float, rhr: float = NORMAL_RHR) -> List[Point]:
    """``days`` mornings ending today, all at the given values."""
    return [(TODAY - timedelta(days=days - 1 - i), hrv, rhr) for i in range(days)]


def _with_tail(tail_days: int, hrv: float, rhr: float = NORMAL_RHR) -> List[Point]:
    """A 24-day normal block followed by an off-tail ending today."""
    return _normal_block(TODAY - timedelta(days=tail_days)) + _tail(tail_days, hrv, rhr)


def test_a_three_morning_run_is_a_pattern_worth_watching():
    verdict = detect_strain(_with_tail(3, MILD_HRV), TODAY)

    assert verdict.strain_days == 3
    assert verdict.is_strain is True
    assert verdict.mean_delta == pytest.approx(-8.0)
    assert verdict.severity == "watch"


def test_two_mornings_are_not_yet_a_pattern():
    """Below the streak length the detector must stay silent — this is the whole
    reason it exists rather than acting on a single morning."""
    verdict = detect_strain(_with_tail(2, MILD_HRV), TODAY)

    assert verdict.strain_days == 2
    assert verdict.is_strain is False
    assert verdict.severity == "none"


def test_a_deeper_run_escalates_past_watch():
    verdict = detect_strain(_with_tail(3, SEVERE_HRV), TODAY)

    assert verdict.strain_days == 3
    assert verdict.mean_delta == pytest.approx(-16.0)
    assert verdict.severity == "ease"


def test_a_normal_morning_ends_the_run():
    """Recovery is the exit condition: a fine morning today means no verdict,
    however bad the preceding days were."""
    history = (
        _normal_block(TODAY - timedelta(days=3))
        + _tail(2, MILD_HRV)
        + [(TODAY, NORMAL_HRV, NORMAL_RHR)]
    )

    verdict = detect_strain(history, TODAY)

    assert verdict.strain_days == 0
    assert verdict.severity == "none"


def test_a_missing_morning_ends_the_run_rather_than_being_skipped():
    """A gap is not evidence. Were it skipped over, a runner who syncs every
    third day would look permanently strained."""
    history = _normal_block(TODAY - timedelta(days=4)) + [
        (TODAY - timedelta(days=3), MILD_HRV, NORMAL_RHR),
        (TODAY - timedelta(days=2), MILD_HRV, NORMAL_RHR),
        # TODAY - 1 deliberately absent: the run stops at the gap
        (TODAY, MILD_HRV, NORMAL_RHR),
    ]

    verdict = detect_strain(history, TODAY)

    assert verdict.strain_days == 1
    assert verdict.is_strain is False


def test_a_mild_run_carries_a_verdict_but_no_driver_text():
    """The shared vocabulary only names a marker once it is meaningfully off
    (HRV under 0.88, resting HR up more than 3 bpm). A run that is off but only
    just therefore arrives with a verdict and no phrasing, and the caller is
    expected to speak from the run rather than this module inventing prose."""
    verdict = detect_strain(_with_tail(3, MILD_HRV), TODAY)

    assert verdict.is_strain is True
    assert verdict.drivers == []


def test_a_streak_that_ended_days_ago_does_not_count():
    history = (
        _normal_block(TODAY - timedelta(days=6))
        + _tail(3, MILD_HRV)
        + [
            (TODAY - timedelta(days=2), NORMAL_HRV, NORMAL_RHR),
            (TODAY - timedelta(days=1), NORMAL_HRV, NORMAL_RHR),
            (TODAY, NORMAL_HRV, NORMAL_RHR),
        ]
    )

    verdict = detect_strain(history, TODAY)

    assert verdict.strain_days == 0


def test_a_resting_hr_only_run_is_detected():
    """HRV is not the only marker; a climbing resting HR is the classic
    under-recovery flag and must stand on its own."""
    verdict = detect_strain(_with_tail(3, NORMAL_HRV, rhr=58.0), TODAY)

    assert verdict.strain_days == 3
    assert verdict.is_strain is True
    assert verdict.mean_delta == pytest.approx(-14.0)


def test_the_run_length_is_bounded_by_the_lookback():
    verdict = detect_strain(_with_tail(STRAIN_LOOKBACK_DAYS, MILD_HRV), TODAY)

    assert verdict.strain_days == STRAIN_LOOKBACK_DAYS


def test_no_baseline_yet_is_not_a_verdict():
    """A new connection must get silence, not a guess on day one."""
    history: List[Point] = _tail(2, MILD_HRV)

    verdict = detect_strain(history, TODAY)

    assert verdict == StrainVerdict()
    assert verdict.severity == "none"


def test_empty_history_is_not_a_verdict():
    assert detect_strain([], TODAY) == StrainVerdict()


def test_drivers_say_why_in_the_shared_vocabulary():
    verdict = detect_strain(_with_tail(3, SEVERE_HRV), TODAY)

    assert verdict.drivers
    assert any("HRV" in driver for driver in verdict.drivers)


def test_off_morning_threshold_matches_the_shared_curves():
    """The threshold is the smallest deviation ``objective_delta`` already calls
    meaningful — if that curve moves, this detector must move with it."""
    assert OFF_MORNING_DELTA == -8.0
    assert STRAIN_STREAK_DAYS == 3
