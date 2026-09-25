"""What the watch says about this morning, judged against the runner's own normal.

Absolute HRV and resting-HR values mean little across people — 45 ms is a
great morning for one runner and a warning sign for another — so every marker
here is *relative*: today against the median of the previous four weeks. That
is also why nothing is judged until a baseline exists (``MIN_BASELINE_DAYS``);
a new connection gets its first verdict about a week in, not a guess on day one.

Two consumers, two shapes:

* :func:`objective_delta` — a signed adjustment (in readiness points) plus the
  human drivers ("your HRV is 18% below your usual"). The check-in scorer
  folds it in at half weight on top of what the runner *said*, because a felt
  "legs are wrecked" should not be outvoted by a sensor.
* :func:`wearable_score` — a full 0–100 score for a morning the runner didn't
  check in at all. Centred on 65 ("good to go", just above the adaptation
  engine's neutral point of ~62), so a normal watch morning neither inflates
  nor deflates the plan; only a real deviation moves it.

Thresholds follow the HRV-guided-training literature's shape (a drop of ~5–10%
below the rolling baseline is within noise; beyond that it's meaningful;
resting HR ~5 bpm above baseline is the classic under-recovery flag), kept
deliberately coarse. Pure: no I/O, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import List, Optional, Sequence, Tuple

BASELINE_WINDOW_DAYS = 28
MIN_BASELINE_DAYS = 5
WEARABLE_NEUTRAL_SCORE = 65.0

# (date, hrv_ms, resting_hr) — any value may be None.
WellnessPoint = Tuple[date, Optional[float], Optional[float]]


@dataclass(frozen=True)
class WellnessBaseline:
    hrv: Optional[float]
    resting_hr: Optional[float]
    hrv_days: int = 0
    rhr_days: int = 0


@dataclass(frozen=True)
class ObjectiveMarkers:
    """This morning's markers, and how they sit against the baseline.

    ``hrv_ratio`` is today / baseline (1.0 = normal); ``rhr_delta`` is today
    minus baseline in bpm. Either is ``None`` without today's value or without
    enough history to judge it.
    """

    hrv: Optional[float] = None
    resting_hr: Optional[float] = None
    sleep_hours: Optional[float] = None
    hrv_ratio: Optional[float] = None
    rhr_delta: Optional[float] = None

    @property
    def has_signal(self) -> bool:
        return (
            self.hrv_ratio is not None
            or self.rhr_delta is not None
            or self.sleep_hours is not None
        )


@dataclass(frozen=True)
class ObjectiveVerdict:
    delta: float
    drivers: List[str] = field(default_factory=list)


def baseline(history: Sequence[WellnessPoint], today: date) -> WellnessBaseline:
    """Median HRV and resting HR over the window *before* ``today``.

    Today is excluded so a bad morning can't soften its own verdict.
    """
    start = today - timedelta(days=BASELINE_WINDOW_DAYS)
    hrvs: List[float] = []
    rhrs: List[float] = []
    for day, hrv, rhr in history:
        if not (start <= day < today):
            continue
        if hrv is not None and hrv > 0:
            hrvs.append(float(hrv))
        if rhr is not None and rhr > 0:
            rhrs.append(float(rhr))
    return WellnessBaseline(
        hrv=median(hrvs) if len(hrvs) >= MIN_BASELINE_DAYS else None,
        resting_hr=median(rhrs) if len(rhrs) >= MIN_BASELINE_DAYS else None,
        hrv_days=len(hrvs),
        rhr_days=len(rhrs),
    )


def markers(
    *,
    hrv: Optional[float],
    resting_hr: Optional[float],
    sleep_hours: Optional[float],
    base: WellnessBaseline,
) -> ObjectiveMarkers:
    """Place this morning's raw values against the baseline."""
    hrv_ratio = (
        round(float(hrv) / base.hrv, 3)
        if hrv is not None and hrv > 0 and base.hrv
        else None
    )
    rhr_delta = (
        round(float(resting_hr) - base.resting_hr, 1)
        if resting_hr is not None and resting_hr > 0 and base.resting_hr
        else None
    )
    return ObjectiveMarkers(
        hrv=hrv,
        resting_hr=resting_hr,
        sleep_hours=sleep_hours,
        hrv_ratio=hrv_ratio,
        rhr_delta=rhr_delta,
    )


def _hrv_points(ratio: float) -> float:
    if ratio >= 1.10:
        return 6.0
    if ratio >= 0.95:
        return 0.0
    if ratio >= 0.88:
        return -8.0
    if ratio >= 0.80:
        return -16.0
    return -25.0


def _rhr_points(delta: float) -> float:
    if delta <= -2:
        return 3.0
    if delta <= 3:
        return 0.0
    if delta <= 6:
        return -8.0
    if delta <= 10:
        return -14.0
    return -20.0


def _sleep_points(hours: float) -> float:
    if hours >= 7:
        return 4.0
    if hours >= 6:
        return 0.0
    if hours >= 5:
        return -8.0
    return -15.0


def objective_delta(m: ObjectiveMarkers, *, include_sleep: bool) -> ObjectiveVerdict:
    """Readiness points the markers add or remove, and the phrases for why.

    ``include_sleep`` is off when scoring a check-in, where hours slept is
    already one of the runner's own inputs (prefilled from the watch) and
    would otherwise count twice.
    """
    delta = 0.0
    drivers: List[str] = []
    if m.hrv_ratio is not None:
        delta += _hrv_points(m.hrv_ratio)
        if m.hrv_ratio < 0.88:
            pct = round((1 - m.hrv_ratio) * 100)
            drivers.append(f"your HRV is {pct}% below your usual")
    if m.rhr_delta is not None:
        delta += _rhr_points(m.rhr_delta)
        if m.rhr_delta > 3:
            drivers.append(f"your resting HR is up {round(m.rhr_delta)} bpm")
    if include_sleep and m.sleep_hours is not None:
        delta += _sleep_points(m.sleep_hours)
        if m.sleep_hours < 6:
            drivers.append(f"you slept {_fmt_hours(m.sleep_hours)}")
    return ObjectiveVerdict(delta=delta, drivers=drivers)


def wearable_score(m: ObjectiveMarkers) -> Optional[float]:
    """A whole-morning score from the watch alone, or ``None`` with no signal."""
    if not m.has_signal:
        return None
    verdict = objective_delta(m, include_sleep=True)
    return round(max(10.0, min(95.0, WEARABLE_NEUTRAL_SCORE + verdict.delta)), 1)


def sleep_hours_from_seconds(seconds: Optional[float]) -> Optional[float]:
    """Intervals' ``sleepSecs`` → hours to one decimal, ignoring junk."""
    if seconds is None:
        return None
    try:
        hours = float(seconds) / 3600.0
    except (TypeError, ValueError):
        return None
    return round(hours, 1) if 0.5 <= hours <= 16 else None


def _fmt_hours(hours: float) -> str:
    rounded = round(hours, 1)
    return f"{int(rounded)}h" if rounded == int(rounded) else f"{rounded}h"
