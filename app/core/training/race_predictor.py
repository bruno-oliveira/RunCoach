"""Race time prediction using VDOT.

Binary-search solver and confidence ranges extracted from VDOTCalculator.
"""

import logging
import math
from typing import Dict, Optional

from app.core.training.vdot_calculator import (
    STANDARD_RACE_DISTANCES,
    _vo2_at_velocity,
    _pct_vo2max_at_time,
)

logger = logging.getLogger(__name__)

_PREDICT_TIME_LO_MIN = 1.0
_PREDICT_TIME_HI_MIN = 600.0
_PREDICT_VDOT_EPSILON = 0.01
_PREDICT_MAX_ITERS = 100

# Piecewise grade penalty: sec/km cost per 1% grade, by grade band.
# Linear (12 sec/km/%) is fine for rolling courses but underestimates steep
# climbs because runners stop running and start power-hiking past ~8% grade --
# vertical speed roughly caps at 800-1000 m/h regardless of horizontal pace.
# Each tuple is (upper_bound_pct, rate_sec_per_km_per_pct).
_GRADE_PENALTY_TIERS: tuple[tuple[float, float], ...] = (
    (4.0, 12.0),
    (8.0, 16.0),
    (12.0, 24.0),
    (float("inf"), 35.0),
)


def _grade_penalty_rate(grade_pct: float) -> float:
    """Sec/km cost per 1% grade at the given grade."""
    for cap, rate in _GRADE_PENALTY_TIERS:
        if grade_pct < cap:
            return rate
    return _GRADE_PENALTY_TIERS[-1][1]


def _elevation_penalty_seconds(distance_km: float, elevation_gain_m: float) -> float:
    """Estimate uphill time cost from total gain when only the total is known.

    Path A approximation: real climbs aren't evenly distributed across a course --
    they concentrate in some fraction of the distance at a steeper effective grade.
    We assume the climb sits in 50% of the distance at 2x the average grade, then
    apply the piecewise rate at that effective grade. This matches the linear
    formula at low grades and compounds correctly when the average gain implies
    real steepness.
    """
    if distance_km <= 0 or elevation_gain_m <= 0:
        return 0.0
    avg_grade_pct = (elevation_gain_m / (distance_km * 1000.0)) * 100.0
    effective_grade_pct = 2.0 * avg_grade_pct
    effective_distance_km = distance_km / 2.0
    rate = _grade_penalty_rate(effective_grade_pct)
    return rate * effective_grade_pct * effective_distance_km


# Trail-experience penalty: a runner with no logged trail effort is missing
# stabilizer strength, descent technique, and pacing intuition. Apply a
# multiplicative penalty that decays linearly to 1.0 once the runner has
# enough trail volume to be considered experienced.
_TRAIL_INEXPERIENCE_RUNS_THRESHOLD = 8
_TRAIL_INEXPERIENCE_MAX_FACTOR = 1.50  # +50% for first trail race


def _trail_inexperience_factor(trail_runs_count: Optional[int]) -> float:
    """Multiplicative time penalty for runners with little trail experience."""
    if trail_runs_count is None:
        return 1.0
    if trail_runs_count >= _TRAIL_INEXPERIENCE_RUNS_THRESHOLD:
        return 1.0
    runs = max(0, trail_runs_count)
    progress = runs / _TRAIL_INEXPERIENCE_RUNS_THRESHOLD
    return _TRAIL_INEXPERIENCE_MAX_FACTOR - progress * (
        _TRAIL_INEXPERIENCE_MAX_FACTOR - 1.0
    )


# Ultra-endurance decay: VDOT's %VO2max model was validated for efforts up
# to ~3.5 hours (marathon). Beyond that, nutrition, fueling breakdown,
# muscular fatigue, and mental factors dominate. Apply a gradual multiplier.
_ULTRA_DECAY_ONSET_HOURS = 3.0
_ULTRA_DECAY_RATE_PER_HOUR = 0.05  # +5% per hour beyond onset
_ULTRA_DECAY_MAX_FACTOR = 1.20     # cap at +20%


def _ultra_endurance_decay(predicted_seconds: float) -> float:
    """Multiplier for events lasting >3 hours where VDOT loses fidelity."""
    time_hours = predicted_seconds / 3600.0
    if time_hours <= _ULTRA_DECAY_ONSET_HOURS:
        return 1.0
    excess = time_hours - _ULTRA_DECAY_ONSET_HOURS
    factor = 1.0 + excess * _ULTRA_DECAY_RATE_PER_HOUR
    return min(factor, _ULTRA_DECAY_MAX_FACTOR)


def predict_time_for_distance(
    vdot: float,
    distance_km: float,
    elevation_gain_m: Optional[float] = None,
    trail_runs_count: Optional[int] = None,
    endurance_factor: Optional[float] = None,
) -> Optional[int]:
    """Predict race time for a given VDOT and distance.

    Uses binary search to solve: vo2(d/t) / pct_vo2max(t) = VDOT

    Args:
        vdot: Runner's VDOT.
        distance_km: Race distance in km.
        elevation_gain_m: Optional total elevation gain. If provided, adds an
            uphill penalty using a piecewise grade rate (steeper grades cost
            disproportionately more time per km than rolling terrain).
        trail_runs_count: If provided AND elevation_gain_m indicates a trail
            (>=20m/km on average), apply a trail-inexperience multiplier.
        endurance_factor: Multiplier (>= 1.0) for runners whose long-run
            performance lags their VDOT prediction (see
            RacePredictorService.compute_endurance_factor). Applied after
            the elevation penalty and before the trail-inexperience factor.
    """
    if vdot < 25 or vdot > 85:
        return None
    if distance_km <= 0:
        return None

    distance_m = distance_km * 1000.0
    lo, hi = _PREDICT_TIME_LO_MIN, _PREDICT_TIME_HI_MIN

    converged = False
    mid = (lo + hi) / 2.0
    for _ in range(_PREDICT_MAX_ITERS):
        mid = (lo + hi) / 2.0
        velocity = distance_m / mid
        vo2 = _vo2_at_velocity(velocity)
        pct = _pct_vo2max_at_time(mid)
        if pct <= 0:
            lo = mid
            continue
        calc_vdot = vo2 / pct
        if abs(calc_vdot - vdot) < _PREDICT_VDOT_EPSILON:
            converged = True
            break
        if calc_vdot > vdot:
            lo = mid
        else:
            hi = mid

    if not converged:
        logger.warning(
            f"VDOT binary search did not converge for vdot={vdot}, distance={distance_km}km"
        )

    flat_seconds = mid * 60
    elevation_penalty_sec = 0.0
    is_trail = False
    if elevation_gain_m and elevation_gain_m > 0:
        elevation_penalty_sec = _elevation_penalty_seconds(distance_km, elevation_gain_m)
        if elevation_gain_m / max(distance_km, 0.001) >= 20.0:
            is_trail = True

    total_seconds = flat_seconds + elevation_penalty_sec
    total_seconds *= _ultra_endurance_decay(total_seconds)
    if endurance_factor and endurance_factor > 1.0:
        total_seconds *= endurance_factor
    if is_trail:
        total_seconds *= _trail_inexperience_factor(trail_runs_count)

    return int(round(total_seconds))


def get_confidence_range(
    vdot: float,
    distance_km: float,
    target_distance: float = 0.0,
    elevation_gain_m: Optional[float] = None,
    trail_runs_count: Optional[int] = None,
    endurance_factor: Optional[float] = None,
) -> Dict[str, int]:
    """Get optimistic and pessimistic time estimates.

    Uses +/-1.5 VDOT for road distances and +/-5.0 for trail (30km or any
    distance with notable elevation gain). Trail outcomes vary much more
    than road outcomes -- a tight band gives false confidence.
    """
    is_trail = target_distance == 30.0 or (
        elevation_gain_m is not None
        and distance_km > 0
        and elevation_gain_m / distance_km >= 20.0
    )
    margin = 5.0 if is_trail else 1.5
    fast_vdot = min(85.0, vdot + margin)
    slow_vdot = max(25.0, vdot - margin)

    fast_time = predict_time_for_distance(
        fast_vdot, distance_km, elevation_gain_m, trail_runs_count, endurance_factor
    )
    slow_time = predict_time_for_distance(
        slow_vdot, distance_km, elevation_gain_m, trail_runs_count, endurance_factor
    )
    base_time = predict_time_for_distance(
        vdot, distance_km, elevation_gain_m, trail_runs_count, endurance_factor
    )

    return {
        "fast": fast_time or base_time,
        "slow": slow_time or base_time,
        "base": base_time,
    }


def predict_times(
    vdot: float,
    trail_runs_count: Optional[int] = None,
    elevation_map: Optional[Dict[str, float]] = None,
    endurance_factor: Optional[float] = None,
) -> Dict[str, Dict]:
    """Get predicted times for all standard race distances.

    The "trail" entry remains a flat-ground equivalent unless the caller
    provides an elevation_map with per-distance elevation gains.
    """
    from app.core.training.vdot_calculator import VDOTCalculator

    predictions = {}
    for name, distance in STANDARD_RACE_DISTANCES.items():
        elev = None
        if elevation_map and name in elevation_map:
            elev = elevation_map[name]
        seconds = predict_time_for_distance(
            vdot, distance,
            elevation_gain_m=elev,
            trail_runs_count=trail_runs_count,
            endurance_factor=endurance_factor,
        )
        if seconds:
            predictions[name] = {
                "seconds": seconds,
                "formatted": VDOTCalculator.format_duration(seconds),
                "distance_km": distance,
            }
    return predictions
