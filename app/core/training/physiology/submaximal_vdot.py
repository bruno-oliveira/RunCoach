"""Fitness shown by training runs that were never run flat out.

VDOT is a race index: Daniels reads it from how fast a runner covered a
distance at full effort. Every logged run is scored that way, and the
recent-fitness estimate blends the best of those scores — so a runner who has
not raced lately is rated on efforts they held back on and comes out low. How
low depends on the hardest thing they did: about three points when they train
up to threshold, nearer nine when they only jog.

Heart rate says how far back a run was held. The plan already prints the
correspondence used here — easy pace is Zone 2, threshold pace is where heart
rate reaches LTHR — so reading it backwards (this heart rate, therefore this
fraction of VDOT) asserts nothing the zone table does not.

It is trusted only so far. The mapping is stated in fractions of LTHR, so a
threshold heart rate set ten beats out moves the answer by three or four
points; the lift over what the runner has shown in pace is therefore capped,
and they earn the rest by running it. It can only raise an estimate: a run
cannot have been harder than flat out, so no reading comes out below the raw
score.

Pure: the caller gathers the runs and the measured threshold heart rate.
"""

import statistics
from dataclasses import dataclass
from itertools import pairwise
from typing import Iterable, Optional

from app.core.training.physiology.hr_zone_calculator import ZONE_DEFINITIONS
from app.core.training.physiology.vdot_calculator import (
    TRAIL_ELEVATION_M_PER_KM,
    VDOTCalculator,
    oxygen_cost_at_pace,
    sustainable_fraction,
)

# Fewer readings than this and the median is a handful of days' weather.
MIN_SUBMAXIMAL_RUNS = 5
# Heart rate lags the legs: over a short run its average sits well under the
# effort, which would read as fitness the runner does not have.
_MIN_DURATION_MINUTES = 20.0
# The most heart rate may add to what the runner has shown in pace, in VDOT
# points. The same bound a tagged race is held to, for the same reason: one
# mis-set number must not rewrite every pace in a plan.
MAX_HEART_RATE_LIFT = 4.0

_AEROBIC_ZONE = next(zone for zone in ZONE_DEFINITIONS if zone["zone"] == 2)
# (heart rate as a fraction of LTHR, fraction of VDOT run at). The zone table's
# own pairing: the easy band spans Zone 2, and threshold pace sits on LTHR.
# Outside these edges there is no reading — below Zone 2 a run is a shuffle,
# and above threshold the average says more about pacing than about fitness.
_INTENSITY_BY_LTHR_FRACTION = (
    (_AEROBIC_ZONE["lthr_min"], VDOTCalculator.ZONE_PCT["E_slow"]),
    (_AEROBIC_ZONE["lthr_max"], VDOTCalculator.ZONE_PCT["E_fast"]),
    (1.0, VDOTCalculator.ZONE_PCT["T"]),
)


@dataclass(frozen=True)
class TrainingRun:
    """The facts about a logged run that say how fit it shows the runner to be."""

    pace_min_km: Optional[float]
    avg_heart_rate: Optional[int]
    duration_minutes: Optional[float]
    distance_km: Optional[float]
    elevation_gain_m: Optional[float]


def intensity_at_heart_rate(avg_heart_rate: float, lthr: int) -> Optional[float]:
    """Fraction of VDOT a run at ``avg_heart_rate`` was held at, or ``None``.

    Interpolated between the zone edges; ``None`` outside the aerobic-to-
    threshold range the mapping covers.
    """
    fraction = avg_heart_rate / lthr
    for (low_hr, low_pct), (high_hr, high_pct) in pairwise(_INTENSITY_BY_LTHR_FRACTION):
        if low_hr <= fraction <= high_hr:
            span = (fraction - low_hr) / (high_hr - low_hr)
            return low_pct + span * (high_pct - low_pct)
    return None


def _is_readable(run: TrainingRun) -> bool:
    """Long enough and flat enough for pace and heart rate to describe it."""
    if not run.pace_min_km or run.pace_min_km <= 0 or not run.avg_heart_rate:
        return False
    if not run.duration_minutes or run.duration_minutes < _MIN_DURATION_MINUTES:
        return False
    if not run.distance_km or run.distance_km <= 0:
        return False
    return (run.elevation_gain_m or 0.0) / run.distance_km <= TRAIL_ELEVATION_M_PER_KM


def heart_rate_vdot(run: TrainingRun, lthr: int) -> Optional[float]:
    """The VDOT one run implies once its heart rate says how hard it was."""
    if not _is_readable(run) or not run.pace_min_km or not run.duration_minutes:
        return None
    intensity = intensity_at_heart_rate(run.avg_heart_rate or 0, lthr)
    if intensity is None:
        return None
    # Nobody holds more than flat-out for the time they ran: a long run at
    # threshold heart rate is drift, and is scored as the race it would be.
    intensity = min(intensity, sustainable_fraction(run.duration_minutes))
    return oxygen_cost_at_pace(run.pace_min_km) / intensity


def aerobic_vdot(runs: Iterable[TrainingRun], lthr: Optional[int]) -> Optional[float]:
    """Median heart-rate VDOT across ``runs``, or ``None`` with too few readings.

    The median, not the best: each reading is an estimate with weather and
    terrain in it, and the top of a noisy set is the noise.
    """
    if not lthr:
        return None
    readings = [
        reading for run in runs if (reading := heart_rate_vdot(run, lthr)) is not None
    ]
    if len(readings) < MIN_SUBMAXIMAL_RUNS:
        return None
    return round(statistics.median(readings), 1)


def lifted_for_held_back_training(
    best_efforts: Optional[float], aerobic: Optional[float]
) -> Optional[float]:
    """``best_efforts`` raised toward ``aerobic``, by no more than the cap.

    With nothing shown in pace there is nothing to bound a heart-rate reading
    against, so there is no estimate either.
    """
    if best_efforts is None or aerobic is None:
        return best_efforts
    ceiling = best_efforts + MAX_HEART_RATE_LIFT
    return round(min(max(best_efforts, aerobic), ceiling), 1)
