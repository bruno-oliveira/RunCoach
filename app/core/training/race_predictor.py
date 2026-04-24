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


def predict_time_for_distance(vdot: float, distance_km: float) -> Optional[int]:
    """Predict race time for a given VDOT and distance.

    Uses binary search to solve: vo2(d/t) / pct_vo2max(t) = VDOT
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

    return int(round(mid * 60))


def get_confidence_range(vdot: float, distance_km: float,
                         target_distance: float = 0.0) -> Dict[str, int]:
    """Get optimistic and pessimistic time estimates.

    Uses +/-1.5 VDOT for road distances and +/-2.0 for trail (30km).
    """
    margin = 2.0 if target_distance == 30.0 else 1.5
    fast_vdot = min(85.0, vdot + margin)
    slow_vdot = max(25.0, vdot - margin)

    fast_time = predict_time_for_distance(fast_vdot, distance_km)
    slow_time = predict_time_for_distance(slow_vdot, distance_km)
    base_time = predict_time_for_distance(vdot, distance_km)

    return {
        "fast": fast_time or base_time,
        "slow": slow_time or base_time,
        "base": base_time,
    }


def predict_times(vdot: float) -> Dict[str, Dict]:
    """Get predicted times for all standard race distances."""
    from app.core.training.vdot_calculator import VDOTCalculator

    predictions = {}
    for name, distance in STANDARD_RACE_DISTANCES.items():
        seconds = predict_time_for_distance(vdot, distance)
        if seconds:
            predictions[name] = {
                "seconds": seconds,
                "formatted": VDOTCalculator.format_duration(seconds),
                "distance_km": distance,
            }
    return predictions
