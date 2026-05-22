"""Unit tests for pure adaptation-signal math (E2 extraction).

These run with no DB — the functions take plain values / duck-typed runs.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.core.coaching.adaptation_math import (
    compute_effort_trend,
    compute_quality_drift,
    count_consecutive_direction,
    count_recent_race_efforts,
)


@dataclass
class FakeRun:
    date: Optional[datetime] = None
    effort_quality_score: Optional[float] = None
    effort_class: Optional[str] = None


TODAY = date(2026, 5, 22)


# -- compute_effort_trend ---------------------------------------------------


def test_effort_trend_insufficient_data():
    assert compute_effort_trend([5.0, 6.0, 7.0]) == "insufficient_data"


def test_effort_trend_increasing():
    assert compute_effort_trend([4, 4, 7, 8]) == "increasing"


def test_effort_trend_decreasing():
    assert compute_effort_trend([8, 8, 4, 4]) == "decreasing"


def test_effort_trend_stable():
    assert compute_effort_trend([6, 6, 6, 6]) == "stable"


# -- count_consecutive_direction --------------------------------------------


def test_consecutive_direction_empty():
    assert count_consecutive_direction(None) == 0
    assert count_consecutive_direction([]) == 0


def test_consecutive_direction_counts_until_break():
    history = [
        {"direction": "increased"},
        {"direction": "increased"},
        {"direction": "increased"},
    ]
    assert count_consecutive_direction(history) == 3


def test_consecutive_direction_stops_on_opposite():
    history = [
        {"direction": "reduced"},
        {"direction": "increased"},
        {"direction": "increased"},
    ]
    # reversed: increased, increased, reduced(break) -> 2
    assert count_consecutive_direction(history) == 2


def test_consecutive_direction_kept_breaks():
    history = [{"direction": "increased"}, {"direction": "kept"}]
    assert count_consecutive_direction(history) == 0


# -- compute_quality_drift --------------------------------------------------


def test_quality_drift_too_few_runs():
    runs = [FakeRun(date=datetime(2026, 5, 1), effort_quality_score=80)]
    assert compute_quality_drift(runs, TODAY) == (None, 0.0)


def test_quality_drift_improvement_positive_modifier():
    runs = [
        FakeRun(date=datetime(2026, 5, 1), effort_quality_score=50),
        FakeRun(date=datetime(2026, 5, 2), effort_quality_score=50),
        FakeRun(date=datetime(2026, 5, 3), effort_quality_score=80),
        FakeRun(date=datetime(2026, 5, 4), effort_quality_score=80),
    ]
    delta, modifier = compute_quality_drift(runs, TODAY)
    assert delta == 30.0
    assert modifier == 0.02


def test_quality_drift_decline_negative_modifier():
    runs = [
        FakeRun(date=datetime(2026, 5, 1), effort_quality_score=80),
        FakeRun(date=datetime(2026, 5, 2), effort_quality_score=80),
        FakeRun(date=datetime(2026, 5, 3), effort_quality_score=50),
        FakeRun(date=datetime(2026, 5, 4), effort_quality_score=50),
    ]
    delta, modifier = compute_quality_drift(runs, TODAY)
    assert delta == -30.0
    assert modifier == -0.02


# -- count_recent_race_efforts ----------------------------------------------


def test_recent_race_efforts_within_window():
    runs = [
        FakeRun(date=datetime(2026, 5, 20), effort_class="race_effort"),
        FakeRun(date=datetime(2026, 5, 1), effort_class="race_effort"),  # >14d ago
        FakeRun(date=datetime(2026, 5, 21), effort_class="easy"),
    ]
    assert count_recent_race_efforts(runs, TODAY) == 1
