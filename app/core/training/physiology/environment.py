"""Environmental performance adjustments: heat/humidity and altitude.

Two distinct, independently-modeled mechanisms back the race-day and
prescribed-pace adjustments:

* **Heat & humidity** slow sustainable pace through thermoregulatory strain.
  We model this through the *dew point* -- the single number that best tracks
  how oppressive conditions feel to a runner because it folds air temperature
  and humidity into one figure. The penalty is a multiplicative factor on
  finish time / per-km pace, applied at the same seam as the elevation penalty
  in :mod:`app.core.training.race_predictor`.

* **Altitude** reduces the partial pressure of oxygen and therefore aerobic
  capacity. We model this as a reduction to VDOT applied *before* the time
  solve, because it is a capacity loss rather than a per-km pacing tax.

Keeping the two mechanisms separate is the physiologically correct split: a
hot day at sea level taxes pace without lowering VO2max, whereas a cool day at
altitude lowers VO2max without the thermoregulatory cost.

Pure functions -- no I/O. Constants are sourced from widely-used coaching
references (Jack Daniels' dew-point pace tables; the ~6% VO2max decline per
1000 m of altitude reported in the altitude-physiology literature). All inputs
are caller-supplied so the module stays offline and deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

# --- Heat / humidity -------------------------------------------------------

# Magnus-formula coefficients for dew-point derivation (Alduchov & Eskridge).
_MAGNUS_A = 17.625
_MAGNUS_B = 243.04

# Below this dew point conditions are effectively neutral for pacing.
HEAT_NEUTRAL_DEW_POINT_C = 10.0

# Piecewise-linear anchors mapping dew point (deg C) to a fractional pace
# slowdown. Interpolated linearly between anchors; clamped at both ends. These
# track the commonly cited dew-point pace tables (negligible below ~10 C,
# climbing through "uncomfortable" in the high teens to "dangerous" past ~24 C).
_HEAT_ANCHORS: Tuple[Tuple[float, float], ...] = (
    (10.0, 0.00),
    (15.5, 0.01),
    (18.0, 0.02),
    (21.0, 0.04),
    (24.0, 0.06),
    (27.0, 0.09),
    (30.0, 0.12),
)
# Never apply more than this fractional slowdown -- past it the sensible advice
# is to abandon time goals, not to model an ever-larger number.
MAX_HEAT_SLOWDOWN = 0.12

# --- Altitude --------------------------------------------------------------

# Aerobic capacity is essentially unaffected below this elevation.
ALTITUDE_NEUTRAL_M = 1000.0
# Fractional VO2max / VDOT decline per 1000 m climbed above the neutral band.
ALTITUDE_DECLINE_PER_1000M = 0.06
# Floor so extreme elevations don't drive VDOT to implausible lows; above this
# the prediction is already heavily caveated.
MIN_ALTITUDE_VDOT_FACTOR = 0.75


def dew_point_c(temp_c: float, humidity_pct: float) -> float:
    """Derive dew point (deg C) from air temperature and relative humidity.

    Uses the Magnus approximation. Humidity is clamped to a sensible (1, 100)
    range so a logged 0% doesn't blow up the logarithm.

    Args:
        temp_c: Air temperature in degrees Celsius.
        humidity_pct: Relative humidity as a percentage (0-100).

    Returns:
        Dew point in degrees Celsius.
    """
    rh = min(100.0, max(1.0, humidity_pct))
    gamma = math.log(rh / 100.0) + (_MAGNUS_A * temp_c) / (_MAGNUS_B + temp_c)
    return (_MAGNUS_B * gamma) / (_MAGNUS_A - gamma)


def heat_pace_factor(dew_point: float) -> float:
    """Multiplicative pace/time penalty (>= 1.0) for a given dew point.

    Returns 1.0 in neutral conditions and up to ``1 + MAX_HEAT_SLOWDOWN`` in
    oppressive heat, interpolating linearly between the documented anchors.
    """
    if dew_point <= _HEAT_ANCHORS[0][0]:
        return 1.0
    if dew_point >= _HEAT_ANCHORS[-1][0]:
        return 1.0 + MAX_HEAT_SLOWDOWN

    for (lo_dp, lo_frac), (hi_dp, hi_frac) in zip(_HEAT_ANCHORS, _HEAT_ANCHORS[1:]):
        if lo_dp <= dew_point <= hi_dp:
            span = hi_dp - lo_dp
            t = (dew_point - lo_dp) / span if span > 0 else 0.0
            frac = lo_frac + t * (hi_frac - lo_frac)
            return 1.0 + min(MAX_HEAT_SLOWDOWN, frac)
    return 1.0


def altitude_vdot_factor(altitude_m: float) -> float:
    """Multiplicative VDOT factor (<= 1.0) for racing at the given altitude.

    Aerobic capacity is unaffected up to ``ALTITUDE_NEUTRAL_M`` and then
    declines ~6% per 1000 m, floored at ``MIN_ALTITUDE_VDOT_FACTOR``.
    """
    if altitude_m <= ALTITUDE_NEUTRAL_M:
        return 1.0
    excess_km = (altitude_m - ALTITUDE_NEUTRAL_M) / 1000.0
    factor = 1.0 - ALTITUDE_DECLINE_PER_1000M * excess_km
    return max(MIN_ALTITUDE_VDOT_FACTOR, factor)


@dataclass(frozen=True)
class EnvironmentalConditions:
    """Race-day (or session) conditions and their derived adjustments.

    Construct via :meth:`from_inputs` so the dew point is computed from
    temperature + humidity when not supplied directly. An instance with no
    meaningful heat or altitude load is treated as :attr:`is_empty` and callers
    skip it entirely (zero behaviour change versus passing ``None``).
    """

    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    dew_point: Optional[float] = None
    altitude_m: Optional[float] = None

    @classmethod
    def from_inputs(
        cls,
        temp_c: Optional[float] = None,
        humidity_pct: Optional[float] = None,
        dew_point: Optional[float] = None,
        altitude_m: Optional[float] = None,
    ) -> Optional["EnvironmentalConditions"]:
        """Build conditions from any subset of inputs, or ``None`` if empty.

        Dew point is derived from ``temp_c`` + ``humidity_pct`` when not passed
        explicitly. Returns ``None`` when nothing actionable was supplied so
        callers can treat "no conditions" uniformly.
        """
        resolved_dp = dew_point
        if resolved_dp is None and temp_c is not None and humidity_pct is not None:
            resolved_dp = dew_point_c(temp_c, humidity_pct)

        if resolved_dp is None and altitude_m is None:
            return None

        conditions = cls(
            temp_c=temp_c,
            humidity_pct=humidity_pct,
            dew_point=resolved_dp,
            altitude_m=altitude_m,
        )
        return None if conditions.is_empty else conditions

    @property
    def has_heat(self) -> bool:
        return self.dew_point is not None and self.dew_point > HEAT_NEUTRAL_DEW_POINT_C

    @property
    def has_altitude(self) -> bool:
        return self.altitude_m is not None and self.altitude_m > ALTITUDE_NEUTRAL_M

    @property
    def is_empty(self) -> bool:
        """True when neither heat nor altitude moves any number."""
        return not self.has_heat and not self.has_altitude

    def pace_factor(self) -> float:
        """Heat-driven multiplicative slowdown applied to time/pace."""
        if self.dew_point is None:
            return 1.0
        return heat_pace_factor(self.dew_point)

    def vdot_factor(self) -> float:
        """Altitude-driven multiplicative VDOT reduction."""
        if self.altitude_m is None:
            return 1.0
        return altitude_vdot_factor(self.altitude_m)

    def coaching_note(self) -> Optional[str]:
        """Short runner-facing explanation, or ``None`` when nothing applies."""
        parts: List[str] = []
        if self.has_heat and self.dew_point is not None:
            slowdown_pct = (self.pace_factor() - 1.0) * 100.0
            parts.append(
                f"Heat & humidity (dew point {self.dew_point:.0f}°C): expect "
                f"~{slowdown_pct:.0f}% slower than your flat-cool time. Start "
                "conservatively, hydrate early, and add electrolytes."
            )
        if self.has_altitude and self.altitude_m is not None:
            loss_pct = (1.0 - self.vdot_factor()) * 100.0
            parts.append(
                f"Altitude ({self.altitude_m:.0f} m): aerobic capacity drops "
                f"~{loss_pct:.0f}%. Pace effort, not the clock, until acclimated."
            )
        return " ".join(parts) if parts else None


def adjust_vdot(vdot: float, conditions: Optional[EnvironmentalConditions]) -> float:
    """Apply the altitude VDOT reduction, if any."""
    if conditions is None:
        return vdot
    return vdot * conditions.vdot_factor()


def adjust_seconds(
    seconds: float, conditions: Optional[EnvironmentalConditions]
) -> float:
    """Apply the heat pace penalty to a predicted time, if any."""
    if conditions is None:
        return seconds
    return seconds * conditions.pace_factor()
