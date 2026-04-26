# RunCoach Plan Generation & Adaptation Quality Analysis

## Scoring Rubric

Each module scored on three dimensions (1-5 scale):

| Score | Correctness | Feasibility | Real-World Quality |
|-------|-------------|-------------|-------------------|
| 5 | Algorithms match published training science exactly | Works for all supported input combinations | Would produce plans comparable to a human coach |
| 4 | Minor deviations from literature, no safety impact | Handles most cases well, rare edge case gaps | Plans are solid for the target audience |
| 3 | Some formulas approximate or lack sourcing | Several edge cases produce suboptimal output | Usable but a coached runner would spot issues |
| 2 | Key calculations diverge from accepted practice | Common inputs trigger known problems | Plans need manual review before use |
| 1 | Fundamentally incorrect training science | Broken for significant input ranges | Unsafe to follow without expert intervention |

---

## Module Scores

### Plan Generators

| Module | Correctness | Feasibility | Quality | Notes |
|--------|:-----------:|:-----------:|:-------:|-------|
| `plan_generator.py` | 5 | 4 | 4 | Solid orchestrator. Daniels' VDOT, 10% rule, periodization, 80/20 all correctly implemented. Profile-aware ACWR adjustment is a strong differentiator. |
| `beginner_plan_generator.py` | 3 | 3 | 3 | C25K progression is well-structured but **distance estimation uses hardcoded 8 min/km pace** affecting all volume calculations. See HIGH-1. |
| `performance_plan_generator.py` | 4 | 4 | 4 | VDOT-based pace zones correctly derived from Daniels' formula. 15% improvement cap is reasonable. Fallback zone multipliers lack published source but produce sensible output. |
| `triathlon_plan_generator.py` | 3 | 2 | 2 | Static pre-defined plans with zero personalization. No periodization logic, no ACWR, no fitness-level adaptation. Acceptable as a v1 but not competitive. |

### Training Calculation Modules

| Module | Correctness | Feasibility | Quality | Notes |
|--------|:-----------:|:-----------:|:-------:|-------|
| `phase_calculator.py` | 5 | 4 | 4 | Distance-specific phase proportions follow Pfitzinger/Lydiard. Recovery every 4th week is standard. Short plans (6wk) get compressed phases which is the correct tradeoff. |
| `mileage_progression.py` | 5 | 5 | 5 | 10% rule enforcement, ACWR-aware peak reduction, recovery week 35% cut, peak oscillation, and taper curves all well-implemented. Constants are well-documented with rationale. |
| `workout_distribution.py` | 4 | 4 | 4 | 80/20 polarization validated. Race-specific emphasis (5K=intervals, marathon=tempo) is correct. Profile-aware adjustments for over/under-training are a nice touch. |
| `long_run_calculator.py` | 4 | 4 | 4 | Phase-based ratio progression with experience-based caps. Profile week-1 nudge prevents jarring jumps. Short-plan adjustment correctly ensures max >= min + 0.02. |
| `key_workout_library.py` | 4 | 4 | 5 | Curated workouts give plans a "coached" feel. VDOT pace injection makes descriptions actionable. Progressive structure within phases. |
| `vdot_calculator.py` | 5 | 5 | 5 | Direct Daniels' Running Formula implementation. Coefficients match 3rd edition. GPS glitch guard (reject < 2:30/km). Clamped to [25, 85] VDOT range. |
| `hr_zone_calculator.py` | 3 | 4 | 3 | 5-zone model is standard. Tanaka formula (208 - 0.7*age) for estimation is correct. **But tempo mapped to zone 3 (70-80%) contradicts VDOT tempo at ~86% VO2max.** See HIGH-2. |
| `quality_scorer.py` | 4 | 4 | 4 | Multi-component scoring (effort + pace). Hill runs correctly de-emphasize pace (GPS unreliable on hills). +-8% pace tolerance is reasonable. |
| `strength_plan.py` | 4 | 4 | 4 | Phase-periodized with experience scaling. Plyometric emphasis in peak phase aligns with literature. Taper correctly reduces volume. |

### Adaptation & Feedback Modules

| Module | Correctness | Feasibility | Quality | Notes |
|--------|:-----------:|:-----------:|:-------:|-------|
| `signal_computer.py` | 4 | 4 | 4 | Phase-weighted signals (volume in base, HR in taper) are well-designed. Overreach detection dual-triggers (effort+volume, HR+inconsistency). Bayesian shrinkage for sparse per-type data. **But no VDOT trend signal.** See HIGH-3. |
| `plan_adjuster.py` | 4 | 4 | 4 | Recency weighting (half-life=3wk) correctly emphasizes recent data. Run mapping before adjustment ensures complete picture. VDOT recalibration check is good. |
| `week_adjuster.py` | 5 | 5 | 5 | Quality workouts dampened to 50% of multiplier (protecting physiological stimulus). Long runs protected from reduction. Annotations for transparency. |
| `run_mapper.py` | 4 | 3 | 4 | Greedy matching with scoring (3x date_penalty + distance_diff). 80% volume threshold for rescheduled vs skipped. Works well when runs roughly match plan structure. |
| `vdot_recalibrator.py` | 5 | 4 | 5 | Auto-updates pace zones when VDOT changes >= 1.0. Prevents stale pace targets. |
| `coaching_feedback_engine.py` | 4 | 4 | 4 | Multi-dimensional feedback (pace, HR, effort, volume, pattern). Quality score integration. |
| `gap_analysis_service.py` | 4 | 4 | 4 | Volume, long run, pace, consistency, and VDOT gap dimensions. Conservative thresholds (5% = on_track). |
| `race_predictor_service.py` | 5 | 4 | 5 | Median-of-top-3 VDOT is statistically robust. Confidence weighting by workout type and distance. Rolling 12-week window. |
| `readiness_service.py` | 4 | 4 | 4 | Sensible component weights (volume 25%, VDOT 25%, long run 20%, consistency 15%, taper 15%). |

---

## HIGH Priority Issues

### HIGH-1: Beginner Pace Hardcoded at 8 min/km

**File:** `app/core/generators/beginner_plan_generator.py:130`

**Current code:**
```python
assumed_pace_km_per_min = 1 / 8.0  # 8 min/km
estimated_km = round(
    week_config["total_min"] * assumed_pace_km_per_min
    * (week_config["run"] / (week_config["run"] + week_config["walk"]))
    * max_runs, 1
)
```

**Problem:** Every beginner plan's `total_km` is calculated assuming the runner covers 1 km every 8 minutes during running segments. This single hardcoded value propagates through the entire plan and affects:
- Weekly volume display (shows inflated/deflated km)
- Recovery week mileage (derived from total_km)
- 10K extension week distances (`_generate_10k_extension_week` inherits this base)

**Real-world impact:**
- A slower beginner running at 9:30/km (common for sedentary adults starting C25K) gets distance targets ~19% too high. Week 10's "30 min continuous run" would show as 3.75 km at the assumed pace, but the runner actually covers ~3.15 km. The plan reports they should be running more than they physically can at their pace.
- A naturally faster beginner at 6:30/km gets targets ~23% too low, making the plan feel unchallenging.

**Training science:** Beginner pace variance is enormous. Studies show C25K participants range from 6:00 to 12:00+ min/km. An 8 min/km assumption only fits the middle of this distribution.

**Fix:** Accept an optional `estimated_pace_min_km` parameter (default 8.0) that can be set from user input or inferred from age/fitness indicators. The beginner plan generator should use this throughout instead of the hardcoded constant:

```python
def generate(self, target_distance, weeks, max_runs_per_week=3,
             estimated_pace_min_km: float = 8.0):
    ...
    assumed_pace_km_per_min = 1 / estimated_pace_min_km
```

**Affected code paths:**
- `beginner_plan_generator.py:130` — C25K distance estimation
- `beginner_plan_generator.py:143-195` — 10K extension weeks (inherits same pace assumption)
- `plan_generator.py` — delegates to beginner generator for 0km base users

---

### HIGH-2: HR Zone Tempo Mapping Contradicts VDOT Tempo Zone

**Files:**
- `app/core/training/hr_zone_calculator.py:31-38` (WORKOUT_ZONE_MAP)
- `app/core/training/vdot_calculator.py:70` (ZONE_PCT)

**Current code in hr_zone_calculator.py:**
```python
WORKOUT_ZONE_MAP: dict[str, int] = {
    "easy": 2,       # Zone 2: 60-70% max HR
    "recovery": 1,   # Zone 1: 50-60% max HR
    "long": 2,       # Zone 2: 60-70% max HR
    "tempo": 3,      # Zone 3: 70-80% max HR  <-- PROBLEM
    "interval": 5,   # Zone 5: 90-100% max HR
    "hill": 5,       # Zone 5: 90-100% max HR
    "rest": 1,
}
```

**Current code in vdot_calculator.py:**
```python
ZONE_PCT = {
    "T": 0.86,   # Threshold / tempo pace = 86% VO2max
}
```

**The contradiction:** The VDOT calculator correctly defines tempo at 86% VO2max, which in Daniels' framework corresponds to approximately 88% of max HR. This falls squarely in Zone 4 (Threshold: 80-90% max HR). But the HR zone calculator maps tempo workouts to Zone 3 (70-80% max HR).

**Real-world impact:** A runner with max HR 190 receives conflicting guidance:
- VDOT-based coaching note: "Run tempo at 5:12/km" (which elicits ~167 BPM for this runner)
- HR zone prescription: "Stay in Zone 3: 133-152 BPM"
- These are **15 BPM apart**. The runner either ignores the HR guidance (making it useless) or slows to Zone 3 pace (undermining the tempo stimulus).

This affects:
- HR zone feedback scoring in `coaching_feedback_engine.py` — tempo runs at correct VDOT pace get flagged as "too high" in HR terms
- HR zone adherence in `adaptation/hr_zone_analyzer.py` — tempo adherence appears poor, which feeds into the adaptation signal_computer's `hr_zone_factor`, potentially triggering unnecessary plan reductions
- The `adaptation/signal_computer.py:139-148` deviation mapping could push `hr_zone_factor` to 0.90, reducing the plan when the runner is actually training correctly

**Training science:** Daniels' Running Formula (3rd ed.) defines tempo/threshold pace at 83-88% VO2max, which maps to approximately 85-92% of max HR depending on the individual. This is Zone 4 in the standard 5-zone model. The American College of Sports Medicine and most coaching literature agree that lactate threshold training occurs at 80-90% max HR.

**Fix:** Remap tempo to Zone 4:

```python
WORKOUT_ZONE_MAP: dict[str, int] = {
    "easy": 2,
    "recovery": 1,
    "long": 2,
    "tempo": 4,      # Zone 4 (Threshold): 80-90% max HR — aligns with Daniels' T pace
    "interval": 5,
    "hill": 5,
    "rest": 1,
}
```

**Affected code paths:**
- `hr_zone_calculator.py:35` — the mapping itself
- `coaching_feedback_engine.py` — HR zone feedback for tempo runs
- `adaptation/hr_zone_analyzer.py` — HR adherence scoring
- `adaptation/signal_computer.py:126-148` — downstream HR zone factor

---

### HIGH-3: No Handling for Declining Fitness in Adaptation Loop

**Files:**
- `app/services/adaptation/signal_computer.py:237-265` (multiplier computation)
- `app/services/adaptation/plan_adjuster.py:110-117` (signal consumption)
- `app/services/race_predictor_service.py:178-194` (VDOT trend calculation)

**Current state:** The `race_predictor_service.py` correctly calculates VDOT trend as "improving", "stable", or "declining" by comparing first vs last VDOT in history (threshold: +/-0.5 VDOT units). However, the `signal_computer.py` does not use this trend at all. The `plan_adjuster.py` calls `compute_adjustment_signals()` without passing VDOT trend data, and the signal computation has no parameter or logic for it.

**Current overreach detection (signal_computer.py:247-255):**
```python
overreach_detected = False
if volume_ratio > 1.2 and avg_effort is not None and avg_effort > 8.0:
    raw_multiplier = min(raw_multiplier, 0.88)
    overreach_detected = True

if hr_zone_adherence < 0.3 and hr_result.get("avg_abs_deviation", 0) > 1.0:
    raw_multiplier = min(raw_multiplier, 0.85)
    overreach_detected = True
```

This only triggers when:
1. Volume exceeds plan by 20% AND perceived effort > 8.0/10, OR
2. HR zone adherence < 30% AND average zone deviation > 1.0

**What's missing:** A runner whose fitness is declining (VDOT dropping) but who still completes workouts at moderate effort (RPE 6-7) will never trigger overreach detection. The plan continues to ramp volume and intensity according to the original periodization schedule, despite the runner's decreasing capacity. This is a classic path to overtraining syndrome.

**Real-world scenario:**
1. Runner starts 16-week marathon plan at VDOT 42
2. Weeks 1-8: normal progression, VDOT stable at 42
3. Weeks 9-12 (build phase): life stress, poor sleep, or early illness causes VDOT to drop to 39
4. Runner still completes runs at RPE 6-7 (they're working harder for slower paces)
5. Adaptation system sees: volume ratio ~1.0, effort ~6.5, completion ~0.85
6. Multiplier stays ~1.0 — plan continues ramping as if nothing changed
7. Weeks 13-14 (peak): runner is now trying to hit peak mileage with VDOT 39 fitness, risking injury or DNF

**Training science:** The acute:chronic workload ratio (ACWR) research (Gabbett 2016, Blanch & Gabbett 2016) shows that internal load (how hard the body perceives the work) matters as much as external load (distance/pace). A declining VDOT with maintained external load means increasing internal load — exactly the pattern that precedes injury.

**Fix:** Add VDOT trend as a signal in `compute_adjustment_signals`:

1. **Pass VDOT trend to signal_computer:**
```python
# In plan_adjuster.py, before calling compute_adjustment_signals:
from app.services.race_predictor_service import RacePredictorService

vdot_trend = RacePredictorService.calculate_vdot_trend(
    RacePredictorService.get_vdot_history(user_id, weeks=8, db=db)
)

signals = compute_adjustment_signals(
    ...,
    vdot_trend=vdot_trend,
)
```

2. **Add declining fitness detection in signal_computer:**
```python
# After overreach detection block (line 255):
if vdot_trend == "declining":
    raw_multiplier = min(raw_multiplier, 0.92)
    # Don't set overreach_detected — this is a distinct signal
    # A declining VDOT warrants caution but not the same 
    # emergency reduction as acute overreach
```

3. **Include in return dict for transparency:**
```python
return {
    ...
    "vdot_trend": vdot_trend,
}
```

**Affected code paths:**
- `adaptation/signal_computer.py` — add `vdot_trend` parameter and declining-fitness guard
- `adaptation/plan_adjuster.py` — fetch VDOT trend before calling signal computation
- `race_predictor_service.py` — already has `calculate_vdot_trend()` and `get_vdot_history()`, no changes needed

---

## Summary

The plan generation system is well-engineered and grounded in established training science. The Daniels' VDOT implementation, 10% rule enforcement, periodization model, and adaptive feedback loop are all strong. The three HIGH issues above represent the most impactful improvements: correcting distance estimates for beginners, aligning HR zone guidance with pace-based coaching, and adding a safety net for declining fitness.
