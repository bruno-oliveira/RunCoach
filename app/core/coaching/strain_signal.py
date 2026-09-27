"""A run of bad mornings, told apart from a single bad morning.

:mod:`app.core.coaching.wellness` answers "how does *this* morning look?" — one
day judged against the runner's own 28-day median. That is the right unit for a
readiness score and the wrong one for deciding to change a plan: a single
suppressed-HRV morning is noise, and reacting to it would make the plan twitchy.

This module adds the one thing a single morning cannot report — whether the
deviation *persists*. It walks back from today while each morning's objective
delta stays at or below :data:`OFF_MORNING_DELTA`, and reports the length of
that run. Three in a row is a pattern; one is a bad night's sleep.

Two rules keep the verdict honest:

* **A gap is not evidence.** A morning with no wearable data — or one whose
  baseline does not exist yet — *ends* the run rather than being skipped over.
  Otherwise a runner who syncs every third day would look permanently strained.
* **A pattern, not a diagnosis.** A hard training block legitimately suppresses
  HRV, so three low mornings inside a peak week are expected. Callers must
  combine this with the load picture (TSB / CTL, ``training_load_service``)
  before treating it as a reason to ease a plan — which is why nothing in this
  module mutates, prescribes, or knows about plans at all.

Pure: no I/O, no ORM, no imports from ``contexts``/``infrastructure`` — so
``pyright`` type-checks it and the decision can be unit-tested without a
database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean
from typing import List, Optional, Sequence

from app.core.coaching import wellness

# How far back the run may extend before we stop looking. A streak longer than
# this is not more actionable than the cap, and the loop stays bounded whatever
# history the caller passes.
STRAIN_LOOKBACK_DAYS = 14

# Consecutive off-mornings that make a pattern rather than a bad night.
STRAIN_STREAK_DAYS = 3

# Per-morning objective delta (readiness points, from ``objective_delta``) at or
# below which a morning counts as *off*. -8.0 is the first negative band of both
# the HRV and resting-HR curves, so it is the smallest deviation the shared
# judgement already treats as meaningful — anything smaller is noise, and
# treating noise as evidence is how a detector starts crying wolf.
OFF_MORNING_DELTA = -8.0

# A run this far down on average, or this long, is worth more than a nudge.
SEVERE_MEAN_DELTA = -14.0

# How many "why" phrasings to carry out of the run.
MAX_DRIVERS = 3


@dataclass(frozen=True)
class StrainVerdict:
    """The run of off-mornings ending at the most recent morning, if any.

    ``drivers`` carries the phrasings the shared ``objective_delta`` vocabulary
    produced for those mornings. It is empty when every morning was off only
    *just*: a marker must be meaningfully off (HRV under 0.88, resting HR up
    more than 3 bpm) before that vocabulary names it. A caller holding a verdict
    with no drivers should speak from the run itself — its length and
    ``mean_delta`` — rather than expect prose to be invented here.
    """

    strain_days: int = 0
    mean_delta: float = 0.0
    drivers: List[str] = field(default_factory=list)

    @property
    def is_strain(self) -> bool:
        """Whether the run is long enough to be a pattern."""
        return self.strain_days >= STRAIN_STREAK_DAYS

    @property
    def severity(self) -> str:
        """``none`` / ``watch`` / ``ease`` — coarse by design.

        The bands exist so a caller can pick how loudly to speak, not to model a
        medical state: ``watch`` is "worth mentioning", ``ease`` is "this has
        gone on long enough to suggest backing off".
        """
        if not self.is_strain:
            return "none"
        if (
            self.strain_days > STRAIN_STREAK_DAYS
            or self.mean_delta <= SEVERE_MEAN_DELTA
        ):
            return "ease"
        return "watch"


def _morning_delta(
    day: date, hrv: Optional[float], resting_hr: Optional[float], history: Sequence
) -> Optional[float]:
    """This morning's objective delta, or ``None`` without a judgeable signal.

    ``None`` covers both "the watch sent nothing" and "there is not enough
    history behind this day to judge it" — the caller treats both as a gap.
    """
    base = wellness.baseline(history, day)
    markers = wellness.markers(
        hrv=hrv, resting_hr=resting_hr, sleep_hours=None, base=base
    )
    if not markers.has_signal:
        return None
    return wellness.objective_delta(markers, include_sleep=False).delta


def detect_strain(
    history: Sequence[wellness.WellnessPoint],
    today: date,
) -> StrainVerdict:
    """Walk back from ``today`` over consecutive off-mornings.

    ``history`` is the runner's ``(date, hrv, resting_hr)`` series in any order;
    only mornings at or before ``today`` are considered, and each is judged
    against the baseline built from the days *before* it, exactly as the
    readiness scorer judges a single morning.
    """
    by_day = {day: (hrv, rhr) for day, hrv, rhr in history if day <= today}

    strain_days = 0
    deltas: List[float] = []
    drivers: List[str] = []
    seen_drivers: set[str] = set()

    for offset in range(STRAIN_LOOKBACK_DAYS):
        day = today - timedelta(days=offset)
        point = by_day.get(day)
        if point is None:
            break  # a gap is not evidence — the run ends here
        hrv, resting_hr = point
        prior = [p for p in history if p[0] < day]
        delta = _morning_delta(day, hrv, resting_hr, prior)
        if delta is None or delta > OFF_MORNING_DELTA:
            break

        strain_days += 1
        deltas.append(delta)
        for driver in _drivers_for(hrv, resting_hr, prior, day):
            if driver not in seen_drivers:
                seen_drivers.add(driver)
                drivers.append(driver)

    if strain_days == 0:
        return StrainVerdict()

    return StrainVerdict(
        strain_days=strain_days,
        mean_delta=round(mean(deltas), 1),
        drivers=drivers[:MAX_DRIVERS],
    )


def _drivers_for(
    hrv: Optional[float],
    resting_hr: Optional[float],
    prior: Sequence,
    day: date,
) -> List[str]:
    """The human reasons this morning scored low, in the shared vocabulary."""
    base = wellness.baseline(prior, day)
    markers = wellness.markers(
        hrv=hrv, resting_hr=resting_hr, sleep_hours=None, base=base
    )
    return list(wellness.objective_delta(markers, include_sleep=False).drivers)
