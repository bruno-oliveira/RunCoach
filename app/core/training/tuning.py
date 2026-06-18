"""Centralized tuning surface for plan-generation constants.

Single home for the cross-cutting "magic numbers" that govern how training
plans are built — progression caps, recovery ratios, peak-mileage ceilings,
long-run ratios/caps, quality-workout caps, and the 80/20 polarization
targets. Individual ``core/training`` modules import their constants from here
so behavior can be tuned in one place rather than hunting literals across
files.

Values are deliberately unchanged from their previous in-module definitions;
this module is a relocation, not a re-tuning.
"""

# =============================================================================
# Mileage progression (see mileage_progression.py)
# =============================================================================

# Non-recovery weeks can increase at most this fraction above the previous
# non-recovery mileage. The classic "10% rule" that prevents overuse injuries.
WEEK_OVER_WEEK_CAP = 1.10

# Recovery weeks cut mileage to this fraction of the high-water mark.
# A ~15% reduction keeps recovery weeks genuinely restorative while preserving
# most of the aerobic stimulus from the preceding block — important on shorter
# plans where the older, deeper cuts (35%, then 20%) shaved meaningful volume
# off the total and pulled prescriptions below those of peer apps. The
# high-water mark is tracked separately, so the post-recovery ramp resumes from
# the pre-dip level rather than recalculating from the reduced week.
RECOVERY_WEEK_RATIO = 0.85

# Minimum bump to register a "progressed" non-recovery week — otherwise the
# week would be flat and look like a plateau.
MIN_NON_RECOVERY_BUMP = 1.01

# Week-over-week growth ceiling for the single *long run* (vs the previous
# loading week's long run, deloads skipped). The weekly 10% rule bounds total
# volume but says nothing about how fast the longest, highest-injury-risk
# session may grow. On trail plans the peak phase applies a race-distance floor
# (a fraction of race distance, not weekly volume) only once the peak phase
# starts, so the long run could jump ~30%+ in a single step at the build→peak
# boundary while the weekly total still looked smooth. The long run may grow by
# the larger of this percentage or a fixed absolute step, so short-race long
# runs ramp by a sensible few km while ultra long runs (large absolute values)
# can still step up proportionally. The race-distance floor is still reached —
# just ramped into over the peak weeks instead of cliff-jumped.
LONG_RUN_GROWTH_PCT = 1.18
LONG_RUN_GROWTH_ABS_KM = 3.0

# Base phase ends at this fraction of peak mileage; build phase ramps from
# here to full peak.
BASE_PHASE_END_FRACTION = 0.70

# Small oscillation within peak weeks so the body doesn't sit on an exact
# ceiling. Cycles 0.97 -> 0.98 -> 0.99 -> repeat.
PEAK_OSCILLATION_BASE = 0.97
PEAK_OSCILLATION_STEP = 0.01

# Absolute maximum weekly mileage per race distance. Raised toward the volume
# ceilings used by modern training apps (Runna et al.) and evidence-based
# coaching: weekly mileage is the single strongest predictor of endurance
# performance, so even sub-marathon runners chasing real improvement benefit
# from more aerobic volume than the old, very conservative caps allowed. The
# 10% week-over-week rule, ACWR injury-risk reductions, and per-run structural
# ceilings still bound how quickly and how high any individual plan ramps.
MAX_PEAK_MILEAGE = {
    5.0: 50.0,
    10.0: 64.0,
    21.1: 82.0,
    30.0: 90.0,
    42.2: 100.0,
}

# Peak-mileage multiplier keyed by ACWR injury-risk band.
ACWR_PEAK_FACTORS = {"low": 1.0, "optimal": 1.0, "high": 0.85, "very_high": 0.75}

# Effective week-over-week cap keyed by recent volume trend. "stable" tracks
# the global 10% rule; a decreasing trend ramps more gently, an increasing
# trend is allowed slightly more headroom.
VOLUME_TREND_CAPS = {
    "decreasing": 1.05,
    "stable": WEEK_OVER_WEEK_CAP,
    "increasing": 1.12,
}

# Weekly volume scales with training frequency. Previously a 3-run and a 6-run
# plan for the same race and fitness targeted identical weekly km — forcing the
# low-frequency plan into oversized individual runs while the high-frequency
# plan was left under-loaded. The peak target is nudged around a reference
# frequency: ``RUNS_PER_WEEK_REFERENCE`` runs/week is the neutral anchor (the
# common default and the marathon minimum, so standard plans are unchanged),
# each run/week above it adds ``RUNS_PER_WEEK_VOLUME_STEP`` of headroom and each
# run below it trims the same amount. The factor is clamped to keep the swing
# modest, and the absolute MAX_PEAK_MILEAGE ceilings still cap the result so a
# high-frequency runner is never pushed past recreational safety limits.
RUNS_PER_WEEK_REFERENCE = 4
RUNS_PER_WEEK_VOLUME_STEP = 0.04
RUNS_PER_WEEK_FACTOR_MIN = 0.85
RUNS_PER_WEEK_FACTOR_MAX = 1.10

# Bracket-aware target peak weekly mileage for trail/ultra plans:
# (current_km multiplier, absolute floor km).
TRAIL_BRACKET_PEAK_TARGETS = {
    "short": (1.7, 38.0),
    "standard": (1.85, 48.0),
    "ultra": (1.9, 60.0),
    "long_ultra": (2.1, 82.0),
}

# =============================================================================
# Long-run ratios and caps (see long_run_calculator.py)
# =============================================================================

# Minimum long-run share of the week for low-frequency road plans, by phase.
#
# At 2-3 runs/week the non-long runs are each bounded relative to the long run
# (easy <= ~0.95x long, quality <= ~0.85x long), so the week's *structural*
# capacity is roughly ``ratio x (1 + 0.95 + 0.85)`` of the long run. With the
# standard 4+ run ratios (~0.31 in early build) three runs sum to only ~0.86 of
# the volume target, so the week craters below its target and then jumps as the
# long run grows through the block — breaking the 10% rule and detraining the
# runner. Anchoring the long run to a higher floor lets the few runs actually
# carry the prescribed volume. A 2-run week is one long + one quality, so it
# needs an even bigger long-run anchor. The weekly-share *cap*
# (get_weekly_long_run_ratio_cap) still bounds the top so the long run never
# dominates. Taper is excluded — volume is intentionally low there.
LOW_FREQ_LONG_RUN_RATIO_FLOOR = {
    2: {"base": 0.46, "build": 0.50, "peak": 0.52},
    3: {"base": 0.34, "build": 0.38, "peak": 0.40},
}

# Long run as a fraction of weekly volume, by road distance category and phase.
ROAD_LONG_RUN_RATIOS = {
    "5K": {
        "base": (0.25, 0.30),
        "build": (0.28, 0.32),
        "peak": (0.30, 0.35),
        "taper": (0.25, 0.30),
    },
    "10K": {
        "base": (0.28, 0.33),
        "build": (0.31, 0.36),
        "peak": (0.35, 0.40),
        "taper": (0.28, 0.33),
    },
    "Half": {
        "base": (0.30, 0.35),
        "build": (0.33, 0.38),
        "peak": (0.40, 0.48),
        "taper": (0.30, 0.35),
    },
    "Marathon": {
        "base": (0.32, 0.38),
        "build": (0.35, 0.42),
        "peak": (0.42, 0.50),
        "taper": (0.32, 0.38),
    },
}

# Long-run ratios for trail, scaling with bracket. Ultras pull more weekly
# volume into the long session; absolute caps below keep them sane.
TRAIL_LONG_RUN_RATIOS = {
    "short": {
        "base": (0.30, 0.35),
        "build": (0.35, 0.40),
        "peak": (0.40, 0.45),
        "taper": (0.30, 0.35),
    },
    "standard": {
        "base": (0.30, 0.35),
        "build": (0.40, 0.45),
        "peak": (0.50, 0.55),
        "taper": (0.35, 0.40),
    },
    "ultra": {
        "base": (0.32, 0.38),
        "build": (0.42, 0.50),
        "peak": (0.50, 0.58),
        "taper": (0.35, 0.40),
    },
    "long_ultra": {
        "base": (0.35, 0.40),
        "build": (0.45, 0.52),
        "peak": (0.45, 0.55),
        "taper": (0.35, 0.40),
    },
}

# Peak long run as a minimum fraction of race distance, by trail bracket.
# The fraction necessarily shrinks as race distance grows — nobody runs an
# entire 100-miler in training — but the longer brackets still need a far
# bigger absolute long run than the old 0.22 floor produced. The bracket caps
# below bound the result for the biggest races.
TRAIL_PEAK_RACE_FRACTION = {
    "short": 0.65,
    "standard": 0.72,
    "ultra": 0.60,
    "long_ultra": 0.30,
}

# Flat-only trail prep can underdose long-run specificity; allow a higher
# share of race distance for short/standard brackets.
TRAIL_PEAK_RACE_FRACTION_FLAT = {
    "short": 0.85,
    "standard": 0.85,
}

# Experience-tiered single-long-run distance caps (km) for road races.
ROAD_LONG_RUN_CAPS = {
    5.0: {"beginner": 7.0, "intermediate": 8.0, "advanced": 10.0},
    10.0: {"beginner": 12.0, "intermediate": 15.0, "advanced": 16.0},
    21.1: {"beginner": 17.0, "intermediate": 18.0, "advanced": 19.0},
    30.0: {"beginner": 24.0, "intermediate": 25.5, "advanced": 27.0},
    42.2: {"beginner": 32.0, "intermediate": 34.0, "advanced": 36.0},
}

# Single-long-run distance cap (km) for trail/ultra, as a *continuous* function
# of race distance rather than coarse per-bracket tiers. Coarse brackets gave
# a 30 km race the same ~26 km cap as a 42 km race (so the long run sat at the
# full race distance), while a 160 km race was pinned to the same ceiling as a
# 50 km one. A log curve scales smoothly instead:
#
#     cap_km(d) = TRAIL_LR_CAP_LOG_A * ln(d) + TRAIL_LR_CAP_LOG_B
#
# tuned so an intermediate runner gets ~16 km @ 15 km, ~25 km @ 30 km,
# ~32 km @ 55 km, ~40 km @ 100 km, and ~46 km @ 160 km. The fraction of race
# distance necessarily falls as the race grows — nobody runs a whole 100-miler
# in training — and the remaining long-day load comes from back-to-back doubles
# (the Intensive Training Weekend), not one ever-bigger grind.
TRAIL_LR_CAP_LOG_A = 12.67
TRAIL_LR_CAP_LOG_B = -18.3

# Absolute clamp on the continuous cap (km), and per-experience multipliers
# applied to the curve so beginners stay conservative and advanced runners get
# a longer peak run.
TRAIL_LR_CAP_MIN_KM = 12.0
TRAIL_LR_CAP_MAX_KM = 48.0
TRAIL_LR_CAP_EXPERIENCE = {
    "beginner": 0.90,
    "intermediate": 1.0,
    "advanced": 1.10,
}

# Fallback long-run cap as a fraction of race distance when no tier matches.
FALLBACK_LONG_RUN_CAP_RATIO = 0.77

# Long run can absorb up to this fraction of weekly volume before the static
# cap scales up toward the hard ceiling.
LONG_RUN_VOLUME_RATIO = 0.30

# =============================================================================
# Quality-workout caps (see quality_caps.py)
# =============================================================================

# Quality workouts (tempo/interval/hill) may not exceed this fraction of the
# long run distance. Drives the per-week quality *budget* allocation.
MAX_QUALITY_VS_LONG_RUN = 0.85

# A prescriptive key workout (a fixed library session such as 8 × 500 m) is
# allowed a little more headroom than the budget allocation: its structure is
# the prescription, so it keeps its full prescribed length whenever that fits
# under this (higher) fraction of the long run, and is only trimmed — by
# dropping reps, never by rewriting them shorter — when it would otherwise
# approach the long run. This keeps real, recognizable sessions on low-mileage
# plans instead of collapsing them to a token budget-sized run, while still
# guaranteeing a quality day never reaches the long run itself.
MAX_KEY_WORKOUT_VS_LONG_RUN = 0.95

# Individual easy runs may not exceed this fraction of the long run distance.
MAX_EASY_VS_LONG_RUN = 0.95

# Tighter easy-vs-long fraction for low-frequency road plans (<= 3 runs/week).
# At low frequency the long run legitimately carries a large share of the
# week's volume (and on short races may exceed race distance — by design), but
# without a tighter easy ceiling the *single* easy slot absorbs the same
# leftover volume and becomes a near-equal second long effort (the documented
# 3-run artifact: a 5K week of long 14 km + "easy" 13 km + a token interval).
# Holding easy runs to ~two-thirds of the long run keeps one clear long run and
# one genuinely easier supporting run; the volume the tighter cap can't place is
# dropped (the week falls slightly short) rather than spawning a second long run.
LOW_FREQ_EASY_VS_LONG_RUN = 0.68

# Absolute ceiling on a single easy run (km), ~70-80 min of easy running.
# This is the primary lever for keeping plans polarized (80/20): a fraction of
# the long run alone can't stop a 30 km long run from spawning an 18 km "easy"
# run on low-run-count plans, but an absolute ceiling can. Applied to road
# plans only (trail back-to-back long days are intentional). When the weekly
# volume won't fit under this cap, the week intentionally falls short rather
# than prescribing a second long effort (audit G3).
MAX_EASY_RUN_KM = 14.0

# Base phase reduces quality caps by this factor.
BASE_PHASE_QUALITY_REDUCTION = 0.80

# Distance-scaled physiological quality caps (km).
QUALITY_CAPS_BY_DISTANCE = {
    5.0: {"tempo": 6.0, "interval": 5.0, "hill": 5.0},
    10.0: {"tempo": 10.0, "interval": 8.0, "hill": 6.0},
    21.1: {"tempo": 14.0, "interval": 10.0, "hill": 8.0},
    30.0: {"tempo": 12.0, "interval": 8.0, "hill": 12.0},
    42.2: {"tempo": 18.0, "interval": 12.0, "hill": 10.0},
}

DEFAULT_QUALITY_CAPS = {"tempo": 12.0, "interval": 10.0, "hill": 8.0}

# Minimum *meaningful* dose for a quality slot (km) in build/peak — the phases
# whose quality work is meant to be substantial. The session total has to clear
# this so that, after the warm-up + cool-down bookends, the working set is a
# real stimulus. Tempo floors at ~6 km, leaving ~4 km of continuous threshold
# (~20 min) — Daniels' threshold floor and the low end of Runna's 20-40 min
# tempo progression. Interval / hill floors stay lower: VO2max work is more
# taxing and is prescribed in short, fast reps, so a ~3 km slot (≈2 km of work,
# e.g. 5 × 400 m) is a complete session even on low-volume weeks — the working
# set still grows with the lighter warm-up/cool-down split and with budget on
# higher-volume plans. An under-dose slot is floored up to its dose when the
# week can afford it (borrowing from the easy budget), otherwise demoted to an
# easy run — never scheduled as a token quality session. See
# weekly_plan_builder.resolve_low_budget_quality.
QUALITY_MIN_DOSE_KM = {"tempo": 6.0, "interval": 3.0, "hill": 3.0}

# Base phase keeps a deliberately lighter threshold dose: base tempo is an
# introductory stimulus, not a peak-grade session, so it floors only to a level
# that guarantees a meaningful-but-modest continuous block (~6 km would push it
# to a build-grade 20-min effort, which is too hard for base). Base interval /
# hill slots are intentionally left untouched (light strides / short sprints),
# so only the tempo dose is overridden here.
BASE_QUALITY_MIN_DOSE_KM = {"tempo": 4.0}

# Floor a quality slot only if each easy run would still clear this length after
# the floored km is borrowed from the easy budget; otherwise demote to easy.
MIN_EASY_PER_RUN_KM = 3.0

# =============================================================================
# 80/20 polarization (see distribution_validator.py)
# =============================================================================

# Target fraction of weekly runs that are "hard" (interval/tempo/hill), by
# phase. Trail gets slightly easier targets because terrain supplies intensity.
HARD_TARGETS_ROAD = {"base": 0.10, "build": 0.20, "peak": 0.25, "taper": 0.10}
HARD_TARGETS_TRAIL = {"base": 0.10, "build": 0.15, "peak": 0.20, "taper": 0.10}

# Correction thresholds: shed one quality slot if hard% exceeds target by more
# than the excess threshold; add one if it falls short by more than the deficit
# threshold (build/peak only).
POLARIZED_EXCESS_THRESHOLD = 0.05
POLARIZED_DEFICIT_THRESHOLD = 0.10

# Minimum weekly volume for a second quality slot. Below this, two floored
# quality sessions plus easy-run minimums oversubscribe the week: quality is
# protected during scale-down, so the overage lands on the weekly total and
# breaks the ~10% progression rule (observed on 26-31 km trail weeks). One
# quality session is standard coaching at these volumes regardless of run
# frequency.
SECOND_QUALITY_MIN_WEEK_KM = 40.0
