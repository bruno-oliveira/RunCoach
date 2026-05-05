# Investigation: "Use my running data" Button Impact on Plan Generation

## Overview

The "Use my running data" toggle (`use_profile` checkbox in `index.html:391`) gates whether a logged-in user's historical run data influences their generated training plan. When enabled, it builds a `RunnerProfile` from the last 12 weeks of run logs and passes it through the plan generation pipeline.

## Data Flow

```
index.html (use_profile checkbox)
  → POST /generate-plan (plan_generation.py:59)
    → build_profile(user_id, db) if use_profile == "on" (line 152-155)
      → RunnerProfile built from RunLog data (runner_profile.py:71-119)
        → profile.to_dict() passed to plan_service.create_plan()
          → plan_generator.generate_plan(..., profile=profile)
            → profile used in 4 downstream modules
```

## How Profile Affects Plan Generation

### 1. VDOT Override (`plan_generator.py:259-261`)
```python
if profile.get("current_vdot") and not vdot:
    vdot = profile["current_vdot"]
```
- Profile VDOT replaces form-entered race-time VDOT **only if** no race time was provided.
- Race-time VDOT takes precedence over profile VDOT.

### 2. Current KM Override (`plan_generator.py:262-264`)
```python
actual_km = profile.get("avg_weekly_km", 0)
if actual_km > current_km:
    current_km = actual_km
```
- Profile mileage **only increases** the user-entered `current_km`.
- If user enters 20 km/week but profile shows 30 km/week, plan uses 30 km/week.
- If user enters 30 km/week but profile shows 20 km/week, plan uses 30 km/week (user input wins).

### 3. Cascading Effects

The overridden `current_km` and `vdot` then flow through:

| Module | Effect |
|--------|--------|
| `mileage_progression.py` | Peak mileage, weekly progression, ACWR peak factor, volume trend cap |
| `long_run_calculator.py` | Week-1 gentle nudge based on `longest_run_km` |
| `workout_distribution.py` | Quality session count (hard_pct/easy_pct), workout type gap detection |
| `plan_generator.py` | Experience level derived from (possibly overridden) `current_km` |

---

## Fundamental Flaws Identified

### FLAW 1: Duplicate Plan Detection Ignores Profile

**Location:** `plan_service.py:53-88` (`find_duplicate`)

The duplicate check compares form fields (`current_km`, `target_distance`, `weeks`, etc.) but **does not compare profile-derived values**. Two plans with identical form inputs but different profile states (e.g., profile data changed between generations, or one with profile enabled and one without) would be treated as duplicates.

**Impact:** If a user generates a plan WITHOUT "Use my running data", then later generates the same plan WITH it enabled, they get the old plan back instead of a new profile-aware plan.

**Severity:** HIGH - silently returns stale/incorrect plan

---

### FLAW 2: Profile VDOT Override Race Condition with Form Race Time

**Location:** `plan_generator.py:259-261`

```python
if profile.get("current_vdot") and not vdot:
    vdot = profile["current_vdot"]
```

The profile VDOT is only used when `vdot` is not already set. But `vdot` is set by `PlanRequest.compute_vdot()` (in `plan_schemas.py:247-288`) when the user enters a recent race time. This means:

- If a user enters a **recent race time** AND enables "Use my running data", the **race-time VDOT wins**.
- But the race-time VDOT might be from a single race months ago, while the profile VDOT is a rolling 12-week best. The profile VDOT could be more representative of current fitness.

**Severity:** MEDIUM - user intent may not be honored

---

### FLAW 3: Experience Level Derived from Overridden `current_km`

**Location:** `plan_generator.py:268`

```python
experience_level = derive_experience_level(current_km)
```

After `current_km` is potentially overridden by `profile["avg_weekly_km"]`, the experience level is recalculated. This means a runner who self-reports as a beginner (low `current_km`) but has historically run more could be classified as intermediate/advanced, receiving harder workouts they may not be prepared for.

**Severity:** MEDIUM - could lead to injury if runner's historical high volume was from a different fitness era

---

### FLAW 4: ACWR Reduction Compounds with Other Safety Caps

**Location:** `mileage_progression.py:49-54`, `mileage_progression.py:57-62`

```python
def _acwr_peak_factor(profile):
    risk = profile.get("acwr_risk", "low")
    return {"low": 1.0, "optimal": 1.0, "high": 0.85, "very_high": 0.75}.get(risk, 1.0)

def _volume_trend_cap(profile):
    trend = profile.get("volume_trend", "stable")
    return {"decreasing": 1.05, "stable": WEEK_OVER_WEEK_CAP, "increasing": 1.12}.get(trend, ...)
```

A runner with `very_high` ACWR risk AND `decreasing` volume trend gets:
- 25% reduction in peak mileage
- 5% week-over-week cap (instead of 10%)

Combined with the existing 10% rule, recovery week cuts, and distance caps, this can produce plans that are **excessively conservative** -- potentially too easy to drive adaptation.

**Severity:** LOW-MEDIUM - over-correction may reduce training effectiveness

---

### FLAW 5: Workout Type Gap Detection Relies on Unstructured Labels

**Location:** `workout_distribution.py:224-237`

```python
counts = profile.get("workout_type_counts", {}) or {}
has_speed = counts.get("interval", 0) + counts.get("speed", 0) + counts.get("track", 0) > 0
has_tempo = counts.get("tempo", 0) + counts.get("threshold", 0) > 0
has_hills = counts.get("hill", 0) + counts.get("hill_repeats", 0) > 0
```

The gap detection checks for specific workout type strings in `RunLog.workout_type`. However:
- These strings depend on what the user selects when logging runs
- Strava-synced runs may have different or missing workout types
- The fallback logic (switching profile from `road_5k` to `road_half` if no speed work) is a blunt instrument

**Severity:** LOW - graceful degradation but imprecise

---

### FLAW 6: Time-Goal Plans Do NOT Use Profile at All

**Location:** `plan_generation.py:268-331` (`_generate_time_goal_plan`)

The time-goal plan mode (`plan_mode == "time"`) calls `PerformanceService.create_performance_plan()` which has its own `calculate_fitness_from_runs()` method. However, this is a **different calculation** from `RunnerProfile` -- it computes `avg_pace` and `avg_weekly_km` from a simple 8-week window, not the richer 12-week profile with VDOT, ACWR, efficiency, and pace zone distribution.

**Impact:** Time-goal plans miss out on all the profile-aware adjustments (ACWR caps, volume trend caps, workout type gap filling, long-run gentle nudges).

**Severity:** MEDIUM - inconsistent experience between plan modes

---

### FLAW 7: Profile `avg_weekly_km` Calculation Uses ISO Week Buckets

**Location:** `runner_profile.py:122-163` (`_compute_volume`)

```python
iso = r.date.isocalendar()
key = f"{iso[0]}-W{iso[1]:02d}"
week_buckets[key] = week_buckets.get(key, 0) + r.distance_km
```

The volume calculation buckets runs by ISO week. This means:
- Partial weeks at the edges of the 12-week window are counted as full weeks
- If a runner has runs in only 3 of the 12 weeks, `avg_weekly_km` is the average of those 3 weeks (not divided by 12), inflating the average
- The `weeks_of_data` field tracks span but is not used to normalize the average

**Example:** Runner logs 30km in week 1, nothing for 10 weeks, 30km in week 12. `avg_weekly_km = 30.0` (average of 2 weeks), not `5.0` (30+30/12).

**Severity:** HIGH - can dramatically overstate actual weekly volume for inconsistent loggers

---

### FLAW 8: Profile `has_sufficient_data` Threshold Too Low

**Location:** `runner_profile.py:85-89`

```python
if len(runs) < 3:
    return profile
profile.has_sufficient_data = True
```

Only 3 runs in 12 weeks is enough to activate the profile. This is insufficient to compute meaningful:
- VDOT trends (needs multiple race-quality efforts)
- Pace zone distributions (needs variety of paces)
- ACWR (needs consistent training load)
- Volume trends (needs multiple weeks of data)

**Severity:** MEDIUM - profile is activated with data too sparse to be reliable

---

## Summary Table

| # | Flaw | Severity | Module |
|---|------|----------|--------|
| 1 | Duplicate detection ignores profile | HIGH | plan_service.py |
| 2 | Profile VDOT loses to stale race-time VDOT | MEDIUM | plan_generator.py |
| 3 | Experience level from overridden current_km | MEDIUM | plan_generator.py |
| 4 | ACWR + volume trend caps compound excessively | LOW-MED | mileage_progression.py |
| 5 | Workout type gap detection on unstructured labels | LOW | workout_distribution.py |
| 6 | Time-goal plans don't use RunnerProfile | MEDIUM | plan_generation.py |
| 7 | avg_weekly_km inflated by sparse logging | HIGH | runner_profile.py |
| 8 | has_sufficient_data threshold too low (3 runs) | MEDIUM | runner_profile.py |

---

## Elevation & Trail Race Predictions — Root Cause Analysis

### Your Specific Case

You ran a 22.3 km trail with 1000m+ elevation. The app predicted **2h29min** but your actual time was **4h20min** — a **75% discrepancy**.

### Root Cause: Two Completely Separate Prediction Pipelines

The app has **two** race prediction systems that are **not connected**:

| Pipeline | Location | Elevation-Aware? |
|----------|----------|------------------|
| **VDOT-based predictions** (general) | `vdot_calculator.py`, `race_predictor.py`, `race_predictor_service.py` | **NO** — assumes flat ground always |
| **GPX-based predictions** (race prep) | `race_pacing_service.py`, `routers/race_prep.py` | **YES** — uses grade per segment |

The VDOT-based pipeline is what powers:
- The "Predictions" section on the analytics page
- Race time predictions shown after logging a run
- The "trail" entry in `predict_times()` (30km flat-ground prediction)
- VDOT calculation from any logged run

The GPX-based pipeline is only triggered when you upload a GPX file via the race prep feature. It is **never** used for general predictions.

---

## Elevation-Related Flaws

### FLAW E1: VDOT Ignores Elevation Entirely

**Location:** `vdot_calculator.py:82-114` (`calculate_vdot`)

```python
def calculate_vdot(distance_km: float, time_seconds: int) -> Optional[float]:
    velocity = distance_m / time_min  # m/min — no elevation factor
    vo2 = _vo2_at_velocity(velocity)
    pct = _pct_vo2max_at_time(time_min)
    vdot = vo2 / pct
```

Daniels' VDOT formula assumes **flat ground**. When you log a trail run with 1000m elevation gain, the VDOT is calculated as if it were flat, producing an **artificially low VDOT** that doesn't reflect your true flat-ground fitness.

**Example:** If your flat-ground 10K VDOT is 45, but you log a hilly 10K that takes 50% longer, the calculated VDOT might drop to ~35. This then poisons all future predictions.

**Impact:** Trail runs drag down your VDOT estimate, making all future predictions too conservative. Conversely, flat-ground VDOT used for trail predictions is too optimistic.

**Severity:** HIGH — affects every trail run logged and every trail prediction made

---

### FLAW E2: Trail Race Predictions Have Zero Elevation Penalty

**Location:** `race_predictor.py:24-61` (`predict_time_for_distance`)

```python
def predict_time_for_distance(vdot: float, distance_km: float) -> Optional[int]:
    # Binary search: vo2(d/t) / pct_vo2max(t) = VDOT
    # No elevation parameter. No grade adjustment. Purely flat-ground physics.
```

When `predict_times()` is called, it predicts times for all standard distances including "trail" (30.0km). The trail prediction is **identical to a flat 30K road race**. There is no elevation penalty applied.

The elevation adjustment code **does exist** in `race_pacing_service.py:97-144`:

```python
UPHILL_PENALTY_SEC_PER_KM_PER_PCT = 12   # 12 sec/km per 1% grade
DOWNHILL_BONUS_SEC_PER_KM_PER_PCT = 5    # 5 sec/km per 1% grade
```

But this is **only used in the race prep GPX upload flow** (`routers/race_prep.py:86-90`), never in the general prediction pipeline.

**Your case mathematically:**
- Your flat-ground VDOT (from Amsterdam runs) predicted 2h29min for 22.3km
- With 1000m elevation over 22.3km, that's ~45m/km average climb, or ~4.5% average grade
- At 12 sec/km per 1% grade: 4.5 × 12 = 54 sec/km penalty
- Over 22.3km: 54 × 22.3 = ~1204 sec = ~20 min penalty
- Even this simple model gives 2h49min, still far from 4h20min

The real-world penalty is much larger because:
1. The linear model underestimates steep climb penalties (>8% grade)
2. Technical trail terrain (not just elevation) slows you significantly
3. Downhill bonus is capped at 15 sec/km (you can't fully recover on descents)
4. First trail race means no trail-specific fitness (muscles, technique, pacing)

**Severity:** CRITICAL — predictions are off by 75% for trail races

---

### FLAW E3: Confidence Range for Trail Is Inadequate

**Location:** `race_predictor.py:64-82` (`get_confidence_range`)

```python
def get_confidence_range(vdot, distance_km, target_distance=0.0):
    margin = 2.0 if target_distance == 30.0 else 1.5  # Only +2/-2 VDOT for trail
```

The confidence range for trail uses ±2.0 VDOT (vs ±1.5 for road). But ±2 VDOT at typical recreational fitness levels only produces a ~5-8% time range. For a 2h29min prediction, the "slow" range might be ~2h40min — nowhere near the actual 4h20min.

**Severity:** MEDIUM — gives false confidence in inaccurate predictions

---

### FLAW E4: No Trail Experience Factor

The system has no concept of "trail experience." A runner who has never done a trail race but has a strong road VDOT gets the same trail prediction as an experienced trail runner with the same VDOT.

Trail running requires different:
- Muscle recruitment (stabilizers, eccentric loading on descents)
- Pacing strategy (power-hiking steep sections)
- Technical skills (foot placement, terrain reading)
- Nutrition/hydration (longer time on feet)

**Severity:** MEDIUM — first-time trail runners will be severely misled

---

### FLAW E5: `avg_weekly_km` from Profile Doesn't Differentiate Terrain

**Location:** `runner_profile.py:122-163`

The profile's volume stats don't distinguish between flat road km and trail km. A runner doing 30km/week on flat roads has very different trail readiness than a runner doing 30km/week on hilly trails, but the profile treats them identically.

**Severity:** LOW — contributes to poor trail plan generation

---

## Summary of All Flaws (Updated)

| # | Flaw | Severity | Module |
|---|------|----------|--------|
| E2 | Trail predictions have zero elevation penalty | CRITICAL | race_predictor.py |
| 1 | Duplicate detection ignores profile | HIGH | plan_service.py |
| 7 | avg_weekly_km inflated by sparse logging | HIGH | runner_profile.py |
| E1 | VDOT ignores elevation entirely | HIGH | vdot_calculator.py |
| 2 | Profile VDOT loses to stale race-time VDOT | MEDIUM | plan_generator.py |
| 3 | Experience level from overridden current_km | MEDIUM | plan_generator.py |
| 6 | Time-goal plans don't use RunnerProfile | MEDIUM | plan_generation.py |
| 8 | has_sufficient_data threshold too low | MEDIUM | runner_profile.py |
| E3 | Trail confidence range inadequate | MEDIUM | race_predictor.py |
| E4 | No trail experience factor | MEDIUM | (missing) |
| 4 | ACWR + volume trend caps compound | LOW-MED | mileage_progression.py |
| 5 | Workout type gap detection imprecise | LOW | workout_distribution.py |
| E5 | Profile volume doesn't differentiate terrain | LOW | runner_profile.py |

---

## Recommended Fixes for Elevation Issues (Priority Order)

### Immediate (Critical Path)

1. **Fix E2 — Connect elevation adjustment to trail predictions:**
   - When predicting trail (30.0km) times, apply an elevation penalty
   - Minimum: ask for total elevation gain in the plan form for trail races
   - Apply a simple formula: `flat_time + (elevation_m / 100) * minutes_per_100m`
   - A reasonable starting value: ~8-12 min per 100m of elevation for recreational runners

2. **Fix E1 — Exclude elevation from VDOT calculation or flag trail runs:**
   - When a run has significant elevation (>20m/km), either:
     - a) Exclude it from VDOT calculation entirely, OR
     - b) Apply an elevation correction before calculating VDOT, OR
     - c) Calculate a separate "flat VDOT" and "trail VDOT"
   - Simplest: runs with elevation_gain_m / distance_km > 20 are excluded from VDOT

3. **Fix E4 — Add trail experience tracking:**
   - Track number of trail runs and total trail km in RunnerProfile
   - Apply a "trail inexperience penalty" to trail predictions for users with <5 trail runs
   - Penalty could be 15-30% for first trail race, diminishing with experience

### Short-term

4. **Fix E3 — Widen trail confidence ranges:**
   - Use ±5 VDOT for trail predictions (not ±2)
   - Or use a multiplicative range: 0.7x to 1.3x of predicted time

5. **Fix E5 — Separate trail vs road volume in profile:**
   - Track `road_weekly_km` and `trail_weekly_km` separately
   - Use trail volume when generating trail plans

### Longer-term

6. **Unify the two prediction pipelines:**
   - `RacePacingService` should be the single prediction engine
   - VDOT-based predictions should delegate to it with optional elevation profile
   - Remove duplicate prediction logic from `race_predictor.py`

7. **Add terrain difficulty factor:**
   - Technical trails (single track, rocks, roots) add time beyond just elevation
   - Could use a "terrain factor" multiplier (1.0 = paved, 1.3 = smooth trail, 1.6 = technical)

---

## Recommended Fixes (All, Priority Order)

1. **Fix E2** — Trail predictions need elevation penalty (CRITICAL)
2. **Fix 7** — avg_weekly_km inflation (HIGH)
3. **Fix 1** — Duplicate detection ignores profile (HIGH)
4. **Fix E1** — VDOT ignores elevation (HIGH)
5. **Fix E4** — No trail experience factor (MEDIUM)
6. **Fix 8** — has_sufficient_data threshold (MEDIUM)
7. **Fix 2** — Profile VDOT precedence (MEDIUM)
8. **Fix 3** — Experience level derivation (MEDIUM)
9. **Fix 6** — Time-goal plans don't use profile (MEDIUM)
10. **Fix E3** — Trail confidence ranges (MEDIUM)
11. **Fix 4** — ACWR cap compounding (LOW-MED)
12. **Fix E5** — Trail vs road volume (LOW)
13. **Fix 5** — Workout type labels (LOW)
