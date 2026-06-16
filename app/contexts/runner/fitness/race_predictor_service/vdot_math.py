"""Pure VDOT math helpers.

Rolling-window fitness baseline, predicted-vs-actual comparison, effort-
confidence weighting, and outlier thresholds. No DB access — operates on
primitives and lists so it stays trivially testable.
"""

import statistics
from typing import Any, Dict, List, Optional

from app.core.training.vdot_calculator import VDOTCalculator

# How many top VDOTs to consider when estimating current fitness.
# Using the median of the top N is robust to 1-2 outliers while
# still reflecting the user's best genuine efforts.
TOP_N_VDOTS = 3

# Trailing window (weeks) for the race-history rolling-VDOT baseline.
_VDOT_WINDOW_WEEKS = 12


def _rolling_window_vdot(run_ts: float, prior_vdots: List[tuple]) -> Optional[float]:
    """Median of the top-N prior VDOTs within the trailing window, or None.

    ``prior_vdots`` is a list of ``(timestamp, vdot)`` for runs before this one.
    """
    cutoff_ts = run_ts - _VDOT_WINDOW_WEEKS * 7 * 86400
    window_vdots = sorted((v for ts, v in prior_vdots if ts >= cutoff_ts), reverse=True)
    if not window_vdots:
        return None
    return statistics.median(window_vdots[:TOP_N_VDOTS])


def _prediction_comparison(
    actual_seconds: Optional[int], predicted_seconds: Optional[int]
) -> Optional[Dict[str, Any]]:
    """Compare an actual finish time against the predicted one, or None."""
    if not (actual_seconds and predicted_seconds):
        return None
    delta = actual_seconds - predicted_seconds
    return {
        "predicted_seconds": predicted_seconds,
        "predicted_formatted": VDOTCalculator.format_duration(predicted_seconds),
        "actual_seconds": actual_seconds,
        "actual_formatted": VDOTCalculator.format_duration(actual_seconds),
        "delta_seconds": delta,
        "delta_formatted": VDOTCalculator.format_duration(abs(delta)),
        "faster_than_predicted": delta < 0,
        "accuracy_pct": round((1 - abs(delta) / predicted_seconds) * 100, 1),
    }


# Confidence multiplier by user-tagged workout type. Higher = more reliable
# VDOT indicator. Used as a fallback when the derived effort_class is unset.
_EFFORT_TYPE_WEIGHT: dict[str, float] = {
    "race": 1.5,
    "interval": 1.3,
    "tempo": 1.2,
    "hill": 1.1,
    "long": 1.0,
    "easy": 0.7,
    "recovery": 0.5,
    "rest": 0.3,
}
_DEFAULT_EFFORT_WEIGHT = 0.8

# Multiplier by derived effort_class (see effort_classifier). The classifier
# infers race/tempo/easy from pace percentile and perceived effort because
# user-tagged workout_type is unreliable in practice (Strava defaults to easy).
_EFFORT_CLASS_WEIGHT: dict[str, float] = {
    "race_effort": 1.5,
    "tempo_effort": 1.2,
    "easy_effort": 0.7,
}


def _effort_weight(effort_class: Optional[str], workout_type: Optional[str]) -> float:
    """Resolve confidence weight, preferring derived class over the user tag."""
    if effort_class and effort_class in _EFFORT_CLASS_WEIGHT:
        return _EFFORT_CLASS_WEIGHT[effort_class]
    return _EFFORT_TYPE_WEIGHT.get(workout_type or "", _DEFAULT_EFFORT_WEIGHT)


# Extreme-outlier filter for VDOT aggregation. Tukey's IQR rule alone is too
# tight on tightly clustered training paces (a 3-point real PR can fall outside
# the bound when IQR is < 1). We pair it with a ratio-against-median bound so
# the filter only triggers when a value is BOTH statistically extreme AND large
# in absolute terms -- which is what GPS / auto-pause artifacts actually look
# like (typically >= 1.4x the cluster median). Genuine PBs are rarely > 1.2x.
_OUTLIER_IQR_K = 3.0
_OUTLIER_RATIO = 1.35
_OUTLIER_MIN_SAMPLE = 5


def _vdot_outlier_threshold(vdots: List[float]) -> Optional[float]:
    """Upper bound above which a VDOT is treated as an artifact, or None.

    Returns the larger of the Tukey IQR bound and a ratio-of-median bound so
    a single rule fits both tightly clustered training paces and high-variance
    samples. Returns None when the sample is too small to estimate either.
    """
    if len(vdots) < _OUTLIER_MIN_SAMPLE:
        return None
    sorted_vdots = sorted(vdots)
    n = len(sorted_vdots)
    q1 = sorted_vdots[n // 4]
    q3 = sorted_vdots[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return None
    iqr_bound = q3 + _OUTLIER_IQR_K * iqr
    ratio_bound = statistics.median(sorted_vdots) * _OUTLIER_RATIO
    return max(iqr_bound, ratio_bound)


# --- Prediction calibration (the predicted-vs-actual feedback loop) ----------
# VDOT estimated from training runs tends to over-predict race performance:
# training paces, GPS spikes, and downhill-aided segments inflate the estimate,
# and most runners don't sustain their best-effort VDOT across a full race. For
# runners who have actually raced we learn a correction from their own results --
# the median (actual / predicted) ratio over genuine maximal efforts -- and
# scale future predictions by it. Every race logged tightens the next
# prediction, so the loop self-corrects toward reality instead of staying
# optimistic. The clamp keeps one anomalous day (a blow-up or a perfect race)
# from distorting every future prediction.
_CALIBRATION_MIN_FACTOR = 0.95
_CALIBRATION_MAX_FACTOR = 1.30
_CALIBRATION_MIN_SAMPLE = 1


def calibration_factor_from_samples(samples: List[tuple]) -> float:
    """Median (actual / predicted) ratio over race efforts, clamped to a band.

    Args:
        samples: ``(predicted_seconds, actual_seconds)`` pairs from the runner's
            genuine maximal efforts, where ``predicted_seconds`` is the race
            prediction snapshotted from their fitness *before* that effort.

    Returns:
        A multiplier to apply to future predictions. ``> 1.0`` means past
        predictions ran optimistic (actual finishes were slower); ``< 1.0``
        means pessimistic. Returns ``1.0`` (no correction) when there isn't
        enough evidence yet.
    """
    ratios = [
        actual / predicted
        for predicted, actual in samples
        if predicted and predicted > 0 and actual and actual > 0
    ]
    if len(ratios) < _CALIBRATION_MIN_SAMPLE:
        return 1.0
    factor = statistics.median(ratios)
    return round(max(_CALIBRATION_MIN_FACTOR, min(factor, _CALIBRATION_MAX_FACTOR)), 3)
