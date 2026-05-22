"""Centralized tuning surface for plan-adaptation constants.

Single home for the thresholds and weights that govern how logged-run signals
translate into plan adjustments — phase weights, multiplier ranges, overreach
and training-load (TSB) clamps, per-workout scaling limits, the recency decay
window, and the recommendation hysteresis band. The adaptation modules import
their constants from here so behavior can be tuned in one place.

Formula-internal coefficients (e.g. the effort/HR/feedback/readiness factor
curves) intentionally remain inline in ``signal_computer`` where they read as
part of the math; this module holds the discrete, standalone knobs.

Values are unchanged from their previous in-module definitions; this is a
relocation, not a re-tuning.
"""

# =============================================================================
# Signal weighting (see signal_computer.py)
# =============================================================================

# Per-phase signal weights: (volume, effort, completion, HR, feedback,
# readiness). Volume dominates early; effort/HR/feedback/readiness gain
# influence toward peak and taper.
PHASE_WEIGHTS = {
    "base": (0.38, 0.18, 0.18, 0.11, 0.07, 0.08),
    "build": (0.33, 0.20, 0.16, 0.14, 0.09, 0.08),
    "peak": (0.28, 0.20, 0.16, 0.16, 0.10, 0.10),
    "taper": (0.10, 0.20, 0.22, 0.22, 0.14, 0.12),
}

# Bayesian shrinkage for per-workout-type volume ratios: require this many runs
# of a type before its per-type ratio carries full confidence.
MIN_RUNS_PER_TYPE = 3
BAYESIAN_SHRINKAGE_PER_RUN = 0.30

# How much each workout type counts toward the volume signal.
IMPORTANCE_WEIGHTS = {
    "long": 1.5,
    "tempo": 1.3,
    "interval": 1.3,
    "vo2max": 1.3,
    "race_pace": 1.3,
    "hill": 1.2,
    "fartlek": 1.1,
    "easy": 1.0,
    "recovery": 0.5,
}

# =============================================================================
# Multiplier range + hysteresis (see signal_computer.py, recommendation_evaluator.py)
# =============================================================================

# Consecutive same-direction adjustments needed to unlock the expanded range.
CONSECUTIVE_THRESHOLD = 3

# Standard multiplier clamp (+/-15%); expanded clamp (+/-25/-30%) unlocked after
# sustained same-direction adjustments or a "primed" peak-phase TSB.
EXPANDED_MIN = 0.70
EXPANDED_MAX = 1.25
STANDARD_MIN = 0.85
STANDARD_MAX = 1.15

# Recommendation is skipped if the proposed multiplier sits within this band of
# 1.0 and would only reverse a recent change (anti-wobble hysteresis).
HYSTERESIS_BAND = 0.05

# =============================================================================
# Overreach + training-load clamps (see signal_computer._apply_clamps)
# =============================================================================

# High volume paired with high perceived effort = overreaching.
OVERREACH_VOLUME_RATIO = 1.2
OVERREACH_EFFORT_THRESHOLD = 8.0
OVERREACH_VOLUME_EFFORT_CLAMP = 0.88

# Poor HR-zone adherence with large deviation = running too hard.
HR_OVERREACH_ADHERENCE = 0.3
HR_OVERREACH_DEVIATION = 1.0
HR_OVERREACH_CLAMP = 0.85

# Recent race efforts cap the multiplier (accumulated race fatigue).
RACE_EFFORT_COUNT_THRESHOLD = 2
RACE_EFFORT_CLAMP = 0.95

# Declining VDOT trend caps the multiplier.
VDOT_DECLINE_CLAMP = 0.92

# When any overreach branch fires, force the multiplier into "reduce or hold".
OVERREACH_OVERRIDE_CLAMP = 0.95

# Training Stress Balance (form) boundaries and the deep-fatigue clamp.
TSB_OVERREACHED = -25.0
TSB_OVERREACHED_CLAMP = 0.92
TSB_PRIMED = 10.0
TSB_FRESH = 5.0
TSB_LOADED = -10.0

# =============================================================================
# Per-workout scaling (see week_adjuster.py)
# =============================================================================

# Per-workout-type ratios are clamped to this range even inside the expanded
# overall range, so a single type can't run away.
PER_TYPE_MIN = 0.85
PER_TYPE_MAX = 1.15

# Quality workouts are scaled at half strength relative to the overall move.
QUALITY_HALF_SCALE = 0.5

# No single workout may exceed this multiple of its baseline distance.
WORKOUT_CEILING = 1.25

# =============================================================================
# Recency weighting (see plan_adjuster.py)
# =============================================================================

# Exponential decay half-life (weeks) for weighting recent runs more heavily.
RECENCY_HALF_LIFE_WEEKS = 3.0
