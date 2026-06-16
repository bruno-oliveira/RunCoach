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

# Neutral "hold" deadband: a computed multiplier this close to 1.0 is snapped to
# exactly 1.0 (no change) unless a genuine overreach signal fired. A single
# skipped or short run nudges the volume/completion signals only slightly, which
# previously produced a ~3-5% cut applied across *every* remaining week — so one
# missed easy run quietly rewrote the whole plan. Treating small moves as "stay
# the course" keeps isolated blips from rippling, while real, sustained
# deviations (which push the multiplier well past the band) still adjust the plan.
HOLD_DEADBAND = 0.05

# =============================================================================
# Overreach + training-load clamps (see signal_computer._apply_clamps)
# =============================================================================

# High volume paired with high perceived effort = overreaching.
OVERREACH_VOLUME_RATIO = 1.2
OVERREACH_EFFORT_THRESHOLD = 8.0
OVERREACH_VOLUME_EFFORT_CLAMP = 0.88

# Sustained very-high perceived effort ALONE (even without excess volume) tempers
# the multiplier to a hold — don't pile load onto a runner who is consistently
# maxed out. Fires earlier than the volume+effort branch above (which needs the
# runner to also be over-distance) and only holds rather than forcing a cut.
OVERREACH_EFFORT_SOLO_THRESHOLD = 8.5
OVERREACH_EFFORT_SOLO_CLAMP = 1.0

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

# =============================================================================
# Readiness signal (see signal_computer.signals._readiness_signal)
# =============================================================================

# Self-reported readiness needs this many recent logs to drive the signal.
READINESS_MIN_LOGS = 3

# Fallback when too few readiness logs exist: derive a mild readiness factor
# from training-load form (TSB) so the signal contributes objective recovery
# information instead of folding to zero for the ~all users who never log
# readiness. Kept in a narrow band [0.95, 1.03] so it doesn't fight the
# extreme-TSB clamp in ``apply_clamps``.
READINESS_TSB_FRESH = 5.0
READINESS_TSB_LOADED = -10.0
READINESS_TSB_OVERLOADED = -25.0
READINESS_TSB_FRESH_FACTOR = 1.03
READINESS_TSB_LOADED_FACTOR = 0.97
READINESS_TSB_OVERLOADED_FACTOR = 0.95
