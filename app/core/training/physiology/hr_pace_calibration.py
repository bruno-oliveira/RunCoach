"""Pace<->heart-rate calibration.

The HR zone *bands* (BPM) are derived from a runner's max / resting HR
(`hr_zone_calculator.py`), and the pace zones are derived from VDOT
(`zone_calculator.py`). The two are computed independently and never checked
against each other, so a plan can claim "Zone 2 = 140-152 bpm" without ever
saying what *pace* a given runner actually runs at when their heart is in that
band -- the missing link between "plans and runs" and "HR zones in terms of
pace".

This module closes that gap with data the runner already produces: every
logged run (and every per-km split) is a ``(pace, heart rate)`` observation.
Fit the runner's personal pace->HR relationship from those observations and we
can express each HR zone as the *pace* it corresponds to for this runner,
specifically -- not from a population formula. As fitness changes the slope and
intercept move, so the mapping is recomputed from recent runs each time.

Pure module: no I/O, no ORM. Callers gather the samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.utils import format_pace_bare

# --- Plausibility filters -----------------------------------------------------

# Discard samples outside a sane human running band before fitting. Walking /
# GPS-paused splits (very slow) and sprint slivers (very fast) distort a linear
# fit, and HR sensor dropouts read implausibly low/high.
_MIN_PLAUSIBLE_HR = 70
_MAX_PLAUSIBLE_HR = 230
_MIN_PLAUSIBLE_PACE_MIN_KM = 2.5  # ~24 km/h, faster than any sustained running
_MAX_PLAUSIBLE_PACE_MIN_KM = 12.0  # 5 km/h, slower is walking, not running

# --- Fit-quality guards -------------------------------------------------------

# Below these the data can't support a trustworthy line; callers fall back to
# the formula zones rather than show a mapping the data doesn't justify.
MIN_CALIBRATION_SAMPLES = 8
# Require a real intensity spread (km/h between slowest and fastest sample);
# fitting a slope through points all at one effort is meaningless.
MIN_SPEED_SPREAD_KMH = 1.5
# Pearson correlation floor. HR-pace is strongly linear over the aerobic band
# for a given runner; a weak correlation means noise (cardiac drift, heat,
# fatigue, mislabelled walks) dominates and the slope can't be trusted.
MIN_CORRELATION = 0.55


def _pace_to_speed_kmh(pace_min_km: float) -> float:
    """Convert pace (min/km) to speed (km/h)."""
    return 60.0 / pace_min_km


def _speed_to_pace_min_km(speed_kmh: float) -> float:
    """Convert speed (km/h) to pace (min/km)."""
    return 60.0 / speed_kmh


@dataclass(frozen=True)
class PaceHRSample:
    """A single ``(pace, heart rate)`` observation from a run or split."""

    pace_min_km: float
    hr: float


@dataclass(frozen=True)
class PaceHRModel:
    """Linear fit of heart rate against running speed.

    HR is modelled against *speed* (km/h) rather than pace because the
    relationship is far more linear in that space over the aerobic-to-threshold
    range a runner spends most time in. ``hr = intercept + slope * speed``.

    Attributes:
        slope: BPM gained per km/h of speed (positive for a valid fit).
        intercept: Extrapolated BPM at zero speed (not physically meaningful
            on its own; only used to evaluate the line).
        r: Pearson correlation of the fit (0-1).
        n: Number of samples the fit was built from.
        speed_min_kmh: Slowest observed speed (mapping outside this is
            extrapolation).
        speed_max_kmh: Fastest observed speed.
    """

    slope: float
    intercept: float
    r: float
    n: int
    speed_min_kmh: float
    speed_max_kmh: float

    def predict_hr(self, pace_min_km: float) -> float:
        """Heart rate this runner would hold at ``pace_min_km``."""
        return self.intercept + self.slope * _pace_to_speed_kmh(pace_min_km)

    def predict_pace(self, hr: float) -> Optional[float]:
        """Pace (min/km) at which this runner's HR reaches ``hr``.

        Returns None when the implied speed is non-positive (an HR below the
        line's floor), which the caller treats as "off the bottom of the data".
        """
        speed = (hr - self.intercept) / self.slope
        if speed <= 0:
            return None
        return _speed_to_pace_min_km(speed)

    def hr_is_within_observed_range(self, hr: float) -> bool:
        """True when ``hr`` falls inside the observed speed span (not extrapolated)."""
        lo = self.predict_hr(_speed_to_pace_min_km(self.speed_min_kmh))
        hi = self.predict_hr(_speed_to_pace_min_km(self.speed_max_kmh))
        return lo <= hr <= hi


def _is_plausible(sample: PaceHRSample) -> bool:
    return (
        _MIN_PLAUSIBLE_HR <= sample.hr <= _MAX_PLAUSIBLE_HR
        and _MIN_PLAUSIBLE_PACE_MIN_KM
        <= sample.pace_min_km
        <= _MAX_PLAUSIBLE_PACE_MIN_KM
    )


def fit_pace_hr_model(
    samples: Sequence[PaceHRSample],
    *,
    min_samples: int = MIN_CALIBRATION_SAMPLES,
    min_speed_spread_kmh: float = MIN_SPEED_SPREAD_KMH,
    min_correlation: float = MIN_CORRELATION,
) -> Optional[PaceHRModel]:
    """Fit ``hr = intercept + slope * speed`` over plausible samples.

    Returns a ``PaceHRModel`` only when the data is rich and consistent enough
    to trust (enough points, real intensity spread, a positive and
    well-correlated slope). Returns None otherwise so callers fall back to the
    formula zones.
    """
    points = [
        (_pace_to_speed_kmh(s.pace_min_km), float(s.hr))
        for s in samples
        if _is_plausible(s)
    ]
    if len(points) < min_samples:
        return None

    speeds = [p[0] for p in points]
    hrs = [p[1] for p in points]
    if max(speeds) - min(speeds) < min_speed_spread_kmh:
        return None

    n = len(points)
    mean_x = sum(speeds) / n
    mean_y = sum(hrs) / n
    sxx = sum((x - mean_x) ** 2 for x in speeds)
    syy = sum((y - mean_y) ** 2 for y in hrs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    if sxx <= 0 or syy <= 0:
        return None

    slope = sxy / sxx
    if slope <= 0:
        return None  # faster should mean higher HR; a flat/negative line is noise

    intercept = mean_y - slope * mean_x
    r = sxy / (sxx * syy) ** 0.5
    if r < min_correlation:
        return None

    return PaceHRModel(
        slope=slope,
        intercept=intercept,
        r=r,
        n=n,
        speed_min_kmh=min(speeds),
        speed_max_kmh=max(speeds),
    )


def _format_pace_band(slow: Optional[float], fast: Optional[float]) -> Optional[str]:
    """Render a 'fast-slow/km' band, or a single pace, or None."""
    slow_str = format_pace_bare(slow) if slow else "--"
    fast_str = format_pace_bare(fast) if fast else "--"
    if slow_str == "--" and fast_str == "--":
        return None
    if slow_str == "--":
        return f"{fast_str}/km"
    if fast_str == "--":
        return f"{slow_str}/km"
    if slow_str == fast_str:
        return f"{slow_str}/km"
    return f"{fast_str}-{slow_str}/km"


def attach_calibrated_paces(
    zones: list[dict],
    model: PaceHRModel,
) -> list[dict]:
    """Annotate each HR zone with the pace this runner runs at that HR.

    For every zone, invert the model at its ``min_bpm`` / ``max_bpm`` to get the
    slow / fast edge of the pace band that produces that heart rate for this
    runner. Mutates and returns ``zones``. Each zone gains:

    - ``pace_min_km`` / ``pace_max_km``: slow / fast pace edge (min/km), or None.
    - ``pace_range_formatted``: display string like '5:10-4:45/km', or None.
    - ``pace_calibrated``: True.
    - ``pace_extrapolated``: True when the zone's BPM band lies wholly outside
      the observed data (the mapping is an extrapolation, shown with a caveat).

    A lower HR maps to a slower pace, so ``min_bpm`` gives the slow edge and
    ``max_bpm`` the fast edge.
    """
    for zone in zones:
        min_bpm = zone.get("min_bpm")
        max_bpm = zone.get("max_bpm")
        slow = model.predict_pace(min_bpm) if min_bpm is not None else None
        fast = model.predict_pace(max_bpm) if max_bpm is not None else None
        zone["pace_min_km"] = slow
        zone["pace_max_km"] = fast
        zone["pace_range_formatted"] = _format_pace_band(slow, fast)
        zone["pace_calibrated"] = True
        # Only "not extrapolated" when the whole band is backed by observed
        # data: if either edge falls beyond the runner's logged effort range,
        # part of the pace mapping is an extrapolation and is flagged as such.
        fully_observed = (
            min_bpm is not None
            and max_bpm is not None
            and model.hr_is_within_observed_range(min_bpm)
            and model.hr_is_within_observed_range(max_bpm)
        )
        zone["pace_extrapolated"] = not fully_observed
    return zones
