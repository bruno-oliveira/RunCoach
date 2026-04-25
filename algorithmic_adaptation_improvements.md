# Algorithmic Adaptation Improvements

## Overview

This document details the analysis of the RunCoach plan adaptation algorithm and a prioritized roadmap for making it more robust across all distances, base weekly mileage, and number of runs per week.

---

## Architecture

The adaptation system uses a **modular facade pattern** with 14 focused modules:

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `__init__.py` | 66 | Facade class (`AdaptationService`) routing to sub-modules |
| `_helpers.py` | 83 | Shared utilities (baselines, plan_data parsing, batch queries) |
| `signal_computer.py` | 183 | Signal computation (volume, effort, completion, phase-aware weights, Bayesian shrinkage) |
| `plan_adjuster.py` | 297 | Orchestration: run mapping → signals → VDOT → week adjustment |
| `week_adjuster.py` | 131 | Apply multiplier to future weeks (per-type ratios, quality dampening, caps) |
| `vdot_recalibrator.py` | 108 | VDOT delta detection + pace zone updates |
| `recalibrator.py` | 146 | Strategy dispatch (`time_off`, `ahead`) + event recording |
| `missed_week_handler.py` | 144 | Missed week detection + phase-aware ease-in recalibration |
| `recovery_inserter.py` | 81 | Ad-hoc recovery week insertion (60% volume, max 2/plan) |
| `suggestion_generator.py` | 174 | Per-week suggestion cards for in-plan display |
| `performance_analyzer.py` | 196 | Read-only metrics (adherence, effort, pace CV) |
| `alert_checker.py` | 216 | Proactive alerts (missed workouts, fatigue) |
| `type_swapper.py` | 273 | Pattern-based workout type substitution |
| `run_mapper.py` | 247 | Greedy run-to-workout matching |
| `skipped_detector.py` | 123 | Skipped vs rescheduled classification |

---

## Current Algorithm Flow

```
Trigger (Strava sync / plan view / manual)
  → map_runs_to_plan() [greedy matching by week]          [run_mapper.py]
  → backfill_baselines()                                   [_helpers.py]
  → Check ≥3 logged runs (early exit if not)
  → compute_adjustment_signals():                          [signal_computer.py]
      • Phase-aware weights (base/build/peak/taper)
      • Volume ratio (weighted by phase) — exponential decay, half-life=3 weeks
      • Effort factor (weighted by phase) — continuous mapping effort 1→1.10, 10→0.85
      • Completion factor (weighted by phase) — step function at 90/70/50%
      • Effort trend modifier — first/second half split (±0.03)
      • Bayesian shrinkage for per-type ratios
      • Overreach override — volume>1.2x AND effort>8.0 → force ≤0.88
      • Final clamp: [0.85, 1.15]
  → VDOT recalibration (|Δ|≥1.0 → update pace zones)      [vdot_recalibrator.py]
  → apply_adjustment_to_future_weeks():                    [week_adjuster.py]
      • Per-type ratios when available
      • Long run protection (no reduction)
      • Quality workout dampening (50% of adjustment)
      • Quality caps enforcement (enforce_week_caps)
      • Step scaling for structured workouts
  → Record adaptation event in history
```

### Signal Computation Detail

**Phase-Aware Weights** (signal_computer.py:11-16)

| Phase | Volume | Effort | Completion | Rationale |
|-------|--------|--------|------------|-----------|
| Base | 55% | 25% | 20% | Building aerobic base is the primary focus |
| Build | 50% | 30% | 20% | Balanced approach (default) |
| Peak | 40% | 35% | 25% | Effort matters more at peak load; fatigue detection critical |
| Taper | 20% | 30% | 50% | Completing the taper correctly is key; volume less relevant |

**Volume Adherence (phase-weighted)**
- Exponential decay with half-life = 3 weeks
- `volume_ratio = max(0.5, min(1.5, actual_weighted / planned_weighted))`
- Per-type ratios computed for easy, long, tempo, interval, hill

**Bayesian Shrinkage for Per-Type Ratios** (signal_computer.py:18-19, 59-74)

| Runs of Type | Confidence | Shrinkage | Behavior |
|--------------|------------|-----------|----------|
| 0 | 0% | 100% to global | Ratio = global volume_ratio |
| 1 | 30% | 70% to global | 30% raw + 70% global |
| 2 | 60% | 40% to global | 60% raw + 40% global |
| 3 | 90% | 10% to global | 90% raw + 10% global |
| 4+ | 100% | 0% to global | Full raw ratio used |

Formula: `ratio = confidence × raw_ratio + (1 - confidence) × volume_ratio`
Constants: `_MIN_RUNS_PER_TYPE = 3`, `_BAYESIAN_SHRINKAGE_PER_RUN = 0.30`

**Effort Signal (phase-weighted)**
- Continuous linear mapping: effort 1 → factor 1.10, effort 10 → factor 0.85
- `effort_factor = max(0.85, min(1.10, 1.10 - (avg_effort - 1.0) * (0.25 / 9.0)))`
- Recency-weighted average (same half-life as volume)

**Effort Trend Modifier**
- First-half vs second-half average comparison
- "increasing" (diff > 1.0): -0.03 modifier
- "decreasing" (diff < -1.0): +0.02 modifier
- Requires 4+ effort data points

**Completion Rate (phase-weighted)**
- Step function: ≥90% → 1.05, ≥70% → 1.00, ≥50% → 0.95, <50% → 0.90
- Weighted by recency (same half-life as volume)

**Overreach Detection (override)**
- If `volume_ratio > 1.2 AND avg_effort > 8.0`: force `multiplier ≤ 0.88`

**Final Clamping**
- `multiplier = round(max(0.85, min(1.15, raw_multiplier)), 2)`

### Recalibration Strategies

| Strategy | Module | Behavior |
|----------|--------|----------|
| `time_off` | `recalibrator.py` | Gentler ramp: factor ranges from 0.7 (immediate) to 1.0 (end of plan) |
| `ahead` | `recalibrator.py` | Bump all future weeks by 10% |
| `missed_week` | `missed_week_handler.py` | Phase-aware ease-in (base=80%, build=75%, peak=65%, taper=80%), shift weeks down |
| `recovery_insertion` | `recovery_inserter.py` | Convert next non-recovery week to 60% volume. Max 2 per plan |

---

## Identified Weaknesses

### CRITICAL — Algorithm Robustness

**1. No runs-per-week adaptation**
- The system scales distances but never adjusts the number of runs per week
- A runner consistently missing 2 of 4 scheduled runs gets distance reductions but still sees 4 days planned
- **Impact**: Structural mismatch persists across the entire plan lifecycle
- **Status**: Not addressed; `suggestion_generator.py` provides hints but no structural change

**2. Narrow multiplier range (0.85–1.15)**
- For runners significantly over/under-performing, convergence takes many cycles
- A runner doing 50% of planned volume needs ~5 adjustment cycles to reach the 0.85x floor
- **Impact**: Slow response to large fitness/lifestyle changes

**3. Effort trend is crude**
- Simple first-half vs second-half average comparison with ±1.0 threshold (`signal_computer.py:172-183`)
- No statistical significance testing, vulnerable to noise and outliers
- **Impact**: False trend signals from random effort variation

### IMPORTANT — Distance & Mileage Handling

**4. Quality caps don't scale with runner fitness**
- `enforce_week_caps` uses the target race distance, not the runner's actual fitness level
- A beginner marathoner (VDOT 30) gets the same caps as an advanced runner (VDOT 50)
- **Impact**: Caps may be too aggressive for beginners, too conservative for advanced runners

**5. Long run protection is one-sided**
- Long runs are protected from reduction (`week_adjuster.py:66-67`) but can still grow when multiplier > 1.0
- No maximum long run progression rate (the 10% rule applies to weekly total, not long run specifically)
- **Impact**: Aggressive long run growth when volume ratio is high

**6. Per-type ratios have sparse data problem**
- ✅ **Partially addressed**: Bayesian shrinkage applied in `signal_computer.py:59-74`
- Still relies on `_MIN_RUNS_PER_TYPE = 3` threshold; types below this get shrunk toward global ratio
- **Residual impact**: Early in a plan, type-specific signals are still weak

**7. Base weekly mileage not directly used in adaptation signals**
- The initial `current_km` used for plan generation is never revisited
- A runner whose actual weekly mileage diverges significantly from the plan's progression gets no structural adjustment
- **Impact**: Plans don't recalibrate to the runner's true baseline

### MODERATE — Signal Quality

**8. Completion rate uses step function**
- Discontinuous jumps at 90/70/50% thresholds (`signal_computer.py:127-134`)
- A runner at 89% completion gets penalized identically to one at 51%
- **Impact**: Unfair and non-smooth adjustments

**9. Volume ratio treats all distance equally**
- Running 1km extra on an easy day weighs the same as completing a missed tempo run
- **Impact**: Volume signal doesn't reflect workout importance

**10. No heart rate data in signals**
- Despite HR zones being computed, adaptation ignores `avg_heart_rate`, `max_heart_rate`, time-in-zone
- **Impact**: Missing objective fatigue indicator

**11. Feedback not wired to adaptation**
- `RunFeedback` and `quality_label` exist but only `type_swapper` uses `quality_label`
- Rich feedback like "pace too fast" or "HR zone exceeded" is ignored
- **Impact**: Lost coaching signal from user-reported experience

### MINOR — Edge Cases & Consistency

**12. VDOT recalibration updates `plan_data` JSON but not ORM `DailyWorkout` pace fields**
- `vdot_recalibrator.py` updates `plan_data` JSON pace fields but ORM objects are not refreshed
- **Impact**: Potential data drift between JSON and ORM representations

**13. No cross-plan learning**
- Each plan adapts independently; sequential plans don't benefit from prior learnings
- **Impact**: New plans start from scratch, repeating known adjustment patterns

**14. Adaptation history not analyzed**
- Last 20 events stored but never examined for patterns
- **Impact**: Missed opportunity to detect "plan reduced 4 times in a row" patterns

---

### ✅ Resolved Since Last Review

| # | Weakness | Resolution |
|---|----------|-----------|
| — | No phase-aware adaptation | Phase-aware weights implemented in `signal_computer.py` (P0) |
| — | Sparse per-type ratios | Bayesian shrinkage implemented in `signal_computer.py` (P0) |
| — | Monolithic plan_adjuster.py | Refactored into 14 focused modules (see Architecture table) |
| — | No missed week handling | `missed_week_handler.py` with phase-aware ease-in |
| — | No recovery insertion | `recovery_inserter.py` with max-2-per-plan guard |
| — | No in-plan suggestions | `suggestion_generator.py` provides per-week cards |

---

## Improvement Roadmap

### P0 — Phase-Aware Weights + Bayesian Shrinkage ✅ Implemented

**Phase-Aware Signal Weights** (`signal_computer.py:11-16`)

Different training phases have different priorities. The signal weights now adapt:

| Phase | Volume | Effort | Completion | Rationale |
|-------|--------|--------|------------|-----------|
| Base | 55% | 25% | 20% | Building aerobic base is the primary focus |
| Build | 50% | 30% | 20% | Balanced approach (previous default) |
| Peak | 40% | 35% | 25% | Effort matters more at peak load; fatigue detection critical |
| Taper | 20% | 30% | 50% | Completing the taper correctly is key; volume less relevant |

**Bayesian Shrinkage for Per-Type Ratios** (`signal_computer.py:18-19, 59-74`)

Per-type volume ratios now use Bayesian shrinkage to handle sparse data:

| Runs of Type | Confidence | Shrinkage | Behavior |
|--------------|------------|-----------|----------|
| 0 | 0% | 100% to global | Ratio = global volume_ratio |
| 1 | 30% | 70% to global | 30% raw + 70% global |
| 2 | 60% | 40% to global | 60% raw + 40% global |
| 3 | 90% | 10% to global | 90% raw + 10% global |
| 4+ | 100% | 0% to global | Full raw ratio used |

Formula: `ratio = confidence × raw_ratio + (1 - confidence) × volume_ratio`

Constants: `_MIN_RUNS_PER_TYPE = 3`, `_BAYESIAN_SHRINKAGE_PER_RUN = 0.30`

**Files**: `signal_computer.py`, `plan_adjuster.py` (orchestration)
**Tests**: 874 lines in `tests/test_adaptation_p0_improvements.py`

---

### P1 — Smoother & More Responsive Signals

**1. Dynamic Multiplier Range**

Expand the multiplier range based on consistency of adjustment direction:

```python
# In signal_computer.py, after computing raw_multiplier:
if consecutive_same_direction >= 3:
    multiplier = round(max(0.70, min(1.25, raw_multiplier)), 2)
else:
    multiplier = round(max(0.85, min(1.15, raw_multiplier)), 2)
```

Would require reading `adaptation_history` to count consecutive same-direction adjustments.

**2. Continuous Completion Factor**

Replace the step function (`signal_computer.py:127-134`) with a smooth linear mapping:

```python
# Before (step function):
# ≥90% → 1.05, ≥70% → 1.00, ≥50% → 0.95, <50% → 0.90

# After (continuous):
completion_factor = 0.90 + 0.15 * completion_rate
# 0% → 0.90, 50% → 0.975, 100% → 1.05
```

**3. Importance-Weighted Volume Ratio**

Weight volume by workout importance instead of treating all distance equally:

```python
_IMPORTANCE_WEIGHTS = {
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
```

Apply in `signal_computer.py` when computing `actual_weighted` and `planned_weighted`.

---

### P2 — Structural & Physiological Improvements

**1. Runs-Per-Week Adaptation Signal**

Add a frequency signal that detects consistent missed days and suggests structural changes:

```python
# If runner consistently completes only 3 of 4 scheduled runs:
if completion_rate < 0.75 and skipped_days_pattern_is_consistent:
    # Trigger recalibrate strategy that redistributes workouts
    # Or suggest reducing max_runs_per_week by 1
```

This would integrate with a new recalibration strategy `"frequency_adjust"` that redistributes the same weekly volume across fewer days, or removes a low-value run day.

Note: `suggestion_generator.py` already provides hints about volume deficits, but no structural change is made.

**2. Long Run Increase Cap**

Cap long run increases at 10% per week regardless of multiplier:

```python
# In week_adjuster.py, after computing type_mult:
if workout.workout_type == "long" and type_mult > 1.0:
    max_increase = 1.10
    long_mult = min(type_mult, max_increase)
    new_distance = max(1.0, round(base_distance * long_mult, 1))
```

**3. Heart Rate Drift Signal**

Add HR drift as an objective fatigue indicator:

```python
# If avg HR for the same pace is increasing over time:
# HR drift = (recent_avg_hr / recent_pace) / (baseline_avg_hr / baseline_pace)
# If drift > 1.05, suggest reduction
```

Would be computed in `signal_computer.py` as an additional modifier.

---

### P3 — Personalization & Learning

**1. VDOT-Scaled Quality Caps**

Scale quality caps by VDOT percentile rather than using fixed distance-based ceilings:

```python
# In week_adjuster.py, before enforce_week_caps:
# VDOT 30 → 0.7x caps, VDOT 45 → 1.0x caps, VDOT 60 → 1.2x caps
vdot_factor = 0.7 + min(0.5, (vdot - 30) / 100)
scaled_caps = {k: round(v * vdot_factor, 1) for k, v in base_caps.items()}
```

**2. Cross-Plan Learning Priors**

Store user-level adaptation patterns and use as prior for new plans:

```python
# In user profile or separate table:
user_adaptation_prior = {
    "avg_multiplier": 0.92,  # This runner consistently needs 8% less
    "preferred_runs_per_week": 3,
    "long_run_max_km": 18,
}

# Use as starting point for new plan generation
```

**3. Adaptation History Pattern Detection**

Analyze the last 20 events for patterns:

```python
# In plan_adjuster.py or a new module:
recent_events = history[-5:]
if all(e["direction"] == "reduced" for e in recent_events):
    # Suggest regenerating plan with lower base mileage
    alert = {
        "type": "persistent_reduction",
        "message": "Plan has been reduced multiple times. Consider regenerating with a lower base.",
        "suggestion": "regenerate_plan",
    }
```

Could integrate with `alert_checker.py` or `suggestion_generator.py`.

---

## Implementation Priority Matrix

| Priority | Change | Impact | Complexity | Status |
|----------|--------|--------|------------|--------|
| **P0** | Phase-aware adaptation weights | High | Low | ✅ Done |
| **P0** | Bayesian shrinkage for per-type ratios | High | Low | ✅ Done |
| **P0** | Refactor monolithic modules | High | Medium | ✅ Done (14 modules) |
| **P0** | Missed week detection + recalibration | High | Medium | ✅ Done |
| **P0** | Recovery week insertion | Medium | Low | ✅ Done |
| **P0** | Weekly suggestion cards | Medium | Low | ✅ Done |
| **P1** | Continuous completion factor mapping | Medium | Low | Planned |
| **P1** | Importance-weighted volume ratio | Medium | Low | Planned |
| **P1** | Dynamic multiplier range based on consistency | Medium | Medium | Planned |
| **P2** | Long run increase cap (10%/week) | Medium | Low | Planned |
| **P2** | Runs-per-week adaptation signal | High | High | Planned |
| **P2** | HR drift signal | Medium | Medium | Planned |
| **P3** | VDOT-scaled quality caps | Medium | Medium | Planned |
| **P3** | Adaptation history pattern detection | Low-Medium | Low | Planned |
| **P3** | Cross-plan learning priors | Low-Medium | High | Planned |

---

## Distance-Specific Considerations

The adaptation algorithm must account for physiological differences across distances:

| Distance | Peak Mileage | Long Run Max | Key Workout | Adaptation Focus |
|----------|-------------|--------------|-------------|------------------|
| 5K | 40 km | 14 km | Intervals/VO2max | Speed maintenance, low volume sensitivity |
| 10K | 50 km | 22 km | Tempo runs | Threshold pace consistency |
| Half Marathon | 65 km | 24 km | Long runs + tempo | Long run completion critical |
| Trail 30K | 75 km | 30 km | Long runs + hills | Elevation tolerance, recovery |
| Marathon | 85 km | 40 km | Long runs | Volume adherence, fatigue management |

### Base Weekly Mileage Handling

The initial `current_km` drives the entire plan's progression via `mileage_progression.py`. During adaptation:

- **Low base runners** (< 20 km/wk): More sensitive to volume changes; the 10% rule is critical
- **Medium base runners** (20-40 km/wk): Standard adaptation behavior applies
- **High base runners** (> 40 km/wk): May already be at or above peak; adaptation should focus on quality workout distribution rather than volume increases

### Runs-Per-Week Handling

The number of runs per week is determined at plan generation by `workout_distribution.get_workout_distribution()` based on `max_runs_per_week`, phase, and target distance. Currently:

- **3 runs/wk**: Long + tempo + easy (minimal flexibility)
- **4 runs/wk**: Long + tempo + interval + easy (standard)
- **5 runs/wk**: Long + tempo + 2x easy + interval/recovery (advanced)

The adaptation system should eventually signal when the chosen frequency doesn't match the runner's actual behavior, triggering a structural recalibration rather than just distance scaling.

### Quality Caps

Quality caps are enforced per-week via `enforce_week_caps()` in `week_adjuster.py:115`, using the target race distance. These caps are **not** VDOT-scaled (see P3).
