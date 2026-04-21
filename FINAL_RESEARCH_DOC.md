# RunCoach: Complete Plan Generation Research Document

**Date:** 2026-04-21
**Scope:** All three generators (Standard, Performance, Beginner), mileage progression, workout allocation, quality caps, adaptation, and validation

---

## 1. System Architecture Overview

RunCoach generates training plans through three distinct generators, each targeting a different runner profile:

| Generator | Entry Point | Target Runner | Key Differentiator |
|-----------|------------|---------------|-------------------|
| `TrainingPlanGenerator` | `plan_generator.py` | Runners with existing mileage base | Distance-based periodization with quality caps |
| `PerformancePlanGenerator` | `performance_plan_generator.py` | Experienced runners targeting race times | VDOT pace zones with segment-based workouts |
| `BeginnerPlanGenerator` | `beginner_plan_generator.py` | Zero-mileage runners (5K/10K only) | Run/walk progression (Couch-to-5K) |

All three generators share core infrastructure:
- `phase_calculator.py` — training phase distribution
- `mileage_progression.py` — weekly volume progression with 10% rule
- `quality_caps.py` — structural and physiological workout limits
- `key_workout_library.py` — curated race-specific workout descriptions

**Routing logic:** When `current_km == 0` and `target_distance ∈ {5.0, 10.0}`, the standard generator delegates to `BeginnerPlanGenerator`. Zero-mileage requests for longer distances raise `ZeroMileageUnsupportedException`.

---

## 2. Input Parameters and Constraints

### 2.1 User-Provided Inputs

| Parameter | Range | Used By |
|-----------|-------|---------|
| `current_km` | 0–100 km/week | All generators |
| `target_distance` | 5.0, 10.0, 21.1, 30.0, 42.2 km | All generators |
| `weeks` | 4–24 (distance-dependent) | All generators |
| `max_runs_per_week` | 2–6 | Standard, Performance |
| `current_pace` | min/km | Performance only |
| `goal_pace` | min/km (must be faster than current) | Performance only |
| `max_heart_rate` | BPM (optional) | Performance only |
| `vdot` | 25–85 (optional, or derived) | Standard, Performance |
| `terrain` | `'flat'` or `None` | Standard (trail plans) |

### 2.2 Validation Constraints

**Week limits by distance:**

| Distance | Min Weeks | Max Weeks |
|----------|----------|----------|
| 5K | 4 | 16 |
| 10K | 6 | 16 |
| Half Marathon | 8 | 20 |
| Trail (30K) | 6 | 20 |
| Marathon | 12 | 24 |

**Mileage minimums (standard plans):**

| Distance | Min km/week |
|----------|------------|
| 5K | 5 |
| 10K | 10 |
| Half Marathon | 15 |
| Trail | 8 |
| Marathon | 25 |

**Mileage minimums (performance plans):**

| Distance | Min km/week |
|----------|------------|
| 5K | 20 |
| 10K | 25 |
| Half Marathon | 35 |
| Marathon | 50 |

**Performance plan pace validation:**
- Goal pace must be faster than current pace
- Improvement capped at 15% (rejects unrealistic goals)

---

## 3. VDOT System

### 3.1 VDOT Calculation

VDOT is derived from a race result using two physiological equations from Daniels' *Running Formula*:

**Oxygen cost at velocity v (m/min):**
```
VO₂ = -4.60 + 0.182258 × v + 0.000104 × v²
```

**Fraction of VO₂max sustainable for time t (minutes):**
```
%VO₂max = 0.8 + 0.1894393 × e^(-0.012778 × t) + 0.2989558 × e^(-0.1932605 × t)
```

**VDOT:**
```
VDOT = VO₂(race_velocity) / %VO₂max(race_time)
```

Result is clamped to [25, 85]. Paces faster than 2:30/km are rejected as GPS artifacts. A binary search converges to ±0.01 VDOT precision.

### 3.2 Training Pace Zones from VDOT

Six zones are derived by solving the quadratic for velocity at specific %VO₂max fractions:

| Zone | Key | %VO₂max | Purpose |
|------|-----|---------|---------|
| Easy (slow) | E_slow | 65% | Recovery runs |
| Easy (fast) | E_fast | 75% | Standard easy runs |
| Marathon | M | 79% | Marathon goal pace |
| Threshold | T | 86% | Tempo / lactate threshold |
| Interval | I | 98% | VO₂max intervals |
| Repetition | R | 105% | Speed / running economy |

**Easy sub-zones:**
- Recovery: 59–65% VO₂max
- Easy: 65–72% VO₂max
- Long Run: 72–76% VO₂max

### 3.3 Performance Generator Zone System

The performance generator uses a 5-zone model. When VDOT zones are available, they map directly:
- Zone 1 (Recovery): E_slow pace
- Zone 2 (Easy): E_fast pace
- Zone 3 (Tempo): T pace
- Zone 4 (VO₂max): I pace
- Zone 5 (Race): M or R pace (distance-dependent)

**Fallback (no VDOT):** Zones are derived from goal pace:
- Zone 1: goal_pace × 1.30
- Zone 2: goal_pace × 1.15
- Zone 3: goal_pace × 1.05
- Zone 4: goal_pace × 0.95
- Zone 5: goal_pace × 1.00

When `max_heart_rate` is provided, HR percentage ranges are attached to each zone.

### 3.4 Race Time Prediction

Binary search solves `VO₂(d/t) / %VO₂max(t) = VDOT` over a 1–600 minute window. Confidence ranges: ±1.5 VDOT for road races, ±2.0 for trail.

---

## 4. Four-Phase Periodization

### 4.1 Phase Distribution

Taper weeks are prescribed as fixed counts, then remaining weeks are split proportionally among base/build/peak:

| Distance | Base % | Build % | Peak % | Taper (weeks) |
|----------|--------|---------|--------|---------------|
| 5K | 35% | 30% | 20% | 1 |
| 10K | 35% | 30% | 15% | 1 |
| Half Marathon | 35% | 35% | 10% | 2 |
| Trail (30K) | 35% | 35% | 10% | 2 |
| Marathon | 30% | 35% | 5% | 3 |

**Rounding rules:**
- Minimums enforced: base ≥ 2, build ≥ 2, peak ≥ 1
- Overages trimmed from the largest non-taper phase
- Shortfalls added to build

**Example: 12-week 10K plan**
- Taper = 1 week, remaining = 11
- Base = round(11 × 0.35/0.80) = 5, Build = round(11 × 0.30/0.80) = 4, Peak = 11 - 5 - 4 = 2

### 4.2 Phase Objectives

**Base Phase** — Builds aerobic foundation to 70% of peak mileage. Introduces one light quality session per week (if ≥4 runs/week): strides for 5K/10K, short threshold for half/marathon, easy hills for trail. Recovery every 4th week if phase ≥ 4 weeks.

**Build Phase** — Ramps from 70% to 100% of peak mileage. Quality sessions increase from 1 to 2 per week (at 5+ runs) after the first 2 build weeks. Recovery every 4th week.

**Peak Phase** — Maintains near-peak mileage with slight oscillation (97% → 98% → 99% of peak, cycling). Maximum quality load. 4+ week peaks include a recovery week at week 3.

**Taper Phase** — Progressive volume reduction. No quality workouts. Distance-appropriate curves:

| Distance | Taper Length | Week-by-Week (% of peak) |
|----------|-------------|--------------------------|
| 5K | 1 week | 55% |
| 10K | 1 week | 55% |
| Half Marathon | 2 weeks | 75% → 55% |
| Trail (30K) | 2 weeks | 72% → 50% |
| Marathon | 3 weeks | 85% → 70% → 50% |

Trail tapers more aggressively than half marathon because eccentric downhill damage requires extra recovery.

### 4.3 Recovery Weeks

| Phase | Frequency | Trigger | Reduction |
|-------|-----------|---------|-----------|
| Base | Every 4th week | Phase ≥ 4 weeks | 65% of high-water mark |
| Build | Every 4th week | Phase ≥ 4 weeks | 65% of high-water mark |
| Peak | Week 3 only | Phase ≥ 4 weeks | 65% of high-water mark |
| Taper | Never | — | Taper itself is recovery |

Recovery weeks do NOT reset the high-water mark — the post-recovery ramp resumes from the pre-recovery level.

---

## 5. Weekly Mileage Progression

### 5.1 Peak Mileage Calculation

Peak mileage is determined by:

**Step 1: Duration-based multiplier**
```
peak_multiplier = 1 + (1.5 × weeks / 16)    # capped at 2.6
```

**Step 2: Distance-based ideal peak**

| Distance | Formula |
|----------|---------|
| 5K | max(25, current × 2.0) |
| 10K | max(30, current × 2.2) |
| Half | max(40, current × 2.3) |
| Trail | max(45, current × 2.0) |
| Marathon | max(50, current × 2.0) |

**Step 3: VDOT adjustment** (when VDOT is available)
```
vdot_factor = 0.95 + min(0.13, (vdot - 30) / 350)
ideal_peak = ideal_peak × vdot_factor
```
This yields: VDOT 30 → 0.95×, VDOT 50 → 1.01×, VDOT 65+ → 1.08×

**Step 4: Final peak**
```
peak = min(current_km × peak_multiplier, ideal_peak)
peak = max(peak, current_km × 1.2)    # at least 20% increase
```

For zero-mileage runners (beginner plans), peak = ideal_peak directly.

### 5.2 The 10% Rule — Core Safety Invariant

**No non-recovery week may increase more than 10% over the previous non-recovery week's mileage.**

Implementation uses a high-water mark system:

```
WEEK_OVER_WEEK_CAP = 1.10
RECOVERY_WEEK_RATIO = 0.65
MIN_NON_RECOVERY_BUMP = 1.01
BASE_PHASE_END_FRACTION = 0.70
```

For each non-recovery week:
```
ideal = start_km + (end_km - start_km) × ((step_idx + 1) / total_steps)
capped = min(ideal, high_water × 1.10)
week_km = max(capped, high_water × 1.01)
high_water = week_km
```

For recovery weeks:
```
week_km = high_water × 0.65
# high_water is NOT updated
```

### 5.3 Phase-by-Phase Progression

**Base phase:** Linear ramp from `current_km` → `peak × 0.70`, under 10% cap per week.

**Build phase:** Linear ramp from `max(high_water, peak × 0.70)` → `peak`, under 10% cap per week.

**Peak phase:** Oscillates around peak:
- Week offset 0 mod 3: peak × 0.97
- Week offset 1 mod 3: peak × 0.98
- Week offset 2 mod 3: peak × 0.99
- First peak week capped to `high_water × 1.10` to prevent abrupt jump from build

**Taper phase:** Direct percentage of peak (see §4.2 table), independent of high-water mark.

### 5.4 Known Edge Cases

**Phase-transition jumps (12-15%):** When the build phase has very few weeks and the 10% cap is applied to a slightly different number than what the workout allocation produces, marginal overages of 12-15% can appear at phase boundaries. These are acceptable and occur only at transitions.

**Very low volume + trail:** With starting mileage ≤10 km/week and 4-5 runs, the long run minimum (≥7.5 km for trail) naturally dominates the weekly distribution. This is structurally expected — the long run must maintain a floor for race-specific endurance even when total volume is low.

---

## 6. Workout Type Distribution

### 6.1 Polarized Training Model (80/20)

RunCoach enforces approximately 80% easy / 20% hard training across the plan:

| Phase | Target Hard % | Trail Target |
|-------|--------------|-------------|
| Base | 10% | 10% |
| Build | 20% | 15% |
| Peak | 25% | 20% |
| Taper | 10% | 10% |

Trail gets easier targets because terrain naturally provides intensity through elevation.

**Auto-correction:**
- If hard % exceeds target + 5%: convert one quality session to easy
- If hard % is below target - 10% in build/peak (and ≥3 runs): convert one easy to interval
- 2-run weeks are exempt from upward correction (no room for quality without displacing the only easy run)

### 6.2 Quality Workout Count

| Phase | ≤2 runs | 3 runs | 4 runs | 5+ runs |
|-------|---------|--------|--------|---------|
| Base | 0 | 0 | 1 | 1 |
| Build (weeks 1-2) | 0 | 0 | 1 | 1 |
| Build (weeks 3+) | 0 | 1 | 1 | 2 |
| Peak | 0 | 1 | 1 | 2 |
| Recovery | 0 | 0 | 0 | 0 |
| Taper | 0 | 0 | 0 | 0 |

### 6.3 Quality Type Selection by Distance Profile

Each race distance has a distinct quality workout pattern:

**5K** — VO₂max emphasis: intervals dominate (2 intervals when 2 quality slots)

**10K** — Balanced: 1 interval + optional tempo

**Half Marathon** — Balanced: 1 interval + optional tempo

**Marathon** — Tempo/MP emphasis: peak phase drops intervals entirely for double tempo

**Trail (hilly)** — Hills dominant: 2 quality = hills every week + rotating second (intervals weeks 1-2, tempo weeks 3-4 in a 4-week cycle); 1 quality = hills 2/3 of weeks, interval on the off week (3-week cycle)

**Trail (flat)** — Tempo replaces hills: 2 quality = weeks 1-2 tempo+interval, weeks 3-4 double tempo; 1 quality = tempo only

**Base phase override:** Regardless of distance, base phase always gets exactly one light quality session — strides/interval for 5K/10K, short threshold for half/marathon, hills for trail.

### 6.4 Performance Generator Quality Distribution

The performance generator uses a different quality allocation model based on quality percentages:

| Phase | Quality % | Description |
|-------|-----------|-------------|
| Base | 30% | 1 quality session |
| Build | 50% | 1-2 quality sessions |
| Peak | 60% | 1-2 quality sessions |
| Taper | 40% | 1 quality session |

Quality sessions for performance plans rotate by phase priority:
- Base: tempo, fartlek
- Build: tempo, vo2max
- Peak: vo2max, race_pace
- Taper: race_pace, tempo

The specific workout type cycles weekly: `quality_types[(week_number - 1 + i) % len(quality_types)]`

---

## 7. Distance Allocation Pipeline

### 7.1 Standard Generator Pipeline

For each week, the standard generator follows this pipeline:

```
1. Calculate long run distance (§8)
2. Calculate quality workout distances from phase distribution
3. Apply quality caps (structural + physiological)
4. Allocate remaining km to easy runs
5. Build individual workouts
6. Scale if actual ≠ target (±3% tolerance)
7. Validate
```

**Step 2: Quality distance calculation**

Quality distances are derived from phase distribution percentages applied to remaining km after the long run:

```
remaining_km = total_km - long_run_distance
tempo_km = remaining_km × (tempo_pct / non_long_pct)
interval_km = remaining_km × (interval_pct / non_long_pct)
hill_km = remaining_km × (hill_pct / non_long_pct)
```

Where `non_long_pct = 1 - long_pct` normalizes the remaining workout types.

Recovery weeks get zero quality distances.

### 7.2 Phase Distribution Percentages

**Base Phase:**

| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 35% | 0% | 5% | 0% | 60% |
| 10K | 40% | 0% | 5% | 0% | 55% |
| Half | 45% | 5% | 0% | 0% | 50% |
| Trail | 45% | 0% | 0% | 5% | 50% |
| Marathon | 45% | 5% | 0% | 0% | 50% |

**Build Phase:**

| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 35% | 12% | 10% | 5% | 38% |
| 10K | 40% | 12% | 10% | 5% | 33% |
| Half | 45% | 10% | 8% | 4% | 33% |
| Trail | 45% | 6% | 6% | 8% | 35% |
| Flat Trail | 45% | 14% | 6% | 0% | 35% |
| Marathon | 45% | 10% | 8% | 4% | 33% |

**Peak Phase:**

| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 33% | 12% | 10% | 5% | 40% |
| 10K | 38% | 12% | 10% | 5% | 35% |
| Half | 43% | 10% | 8% | 4% | 35% |
| Trail | 43% | 6% | 6% | 8% | 37% |
| Flat Trail | 43% | 14% | 6% | 0% | 37% |
| Marathon | 43% | 10% | 8% | 4% | 35% |

**Taper Phase:**

| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 30% | 12% | 0% | 0% | 58% |
| 10K | 35% | 12% | 0% | 0% | 53% |
| Half | 40% | 10% | 0% | 0% | 50% |
| Trail | 40% | 6% | 0% | 4% | 50% |
| Marathon | 40% | 10% | 0% | 0% | 50% |

### 7.3 Performance Generator Pipeline

The performance generator uses a different allocation approach:

```
1. Generate long run (30% of weekly_km, capped by race distance)
2. Generate quality workouts (scaled to weekly_km by phase percentages)
3. Apply enforce_week_caps() from quality_caps.py
4. Calculate remaining_km = weekly_km - total_assigned_km
5. Distribute remaining to easy runs (with min floor)
6. Validate
```

**Quality workout scaling (performance generator):**

| Workout Type | Base | Build | Peak | Taper |
|-------------|------|-------|------|-------|
| Tempo | min(6, weekly_km × 0.20) | min(10, weekly_km × 0.25) | min(12, weekly_km × 0.30) | min(5, weekly_km × 0.15) |
| VO₂max | weekly_km × 0.15 | weekly_km × 0.20 | weekly_km × 0.18 | weekly_km × 0.12 |
| Race Pace | min(4, weekly_km × 0.15) | min(8, weekly_km × 0.20) | min(12, weekly_km × 0.25) | min(3, weekly_km × 0.10) |
| Fartlek | weekly_km × 0.20 | weekly_km × 0.25 | weekly_km × 0.28 | weekly_km × 0.15 |

Fartlek distances are additionally clamped to [5, 14] km.

All performance quality workouts include 2 km warmup + main effort + 2 km cooldown.

**VO₂max interval auto-selection:**
- Total interval km ≤ 3: 400m intervals
- ≤ 5: 600m
- ≤ 8: 800m
- > 8: 1000m
- Reps: max(3, min(8, total_interval_km / interval_km))

---

## 8. Long Run Calculation

### 8.1 Long Run Ratio

The long run's share of weekly mileage is determined by race distance and phase, with linear progression within each phase from min to max ratio:

| Distance | Base | Build | Peak | Taper |
|----------|------|-------|------|-------|
| 5K | 25–30% | 28–32% | 30–35% | 25–30% |
| 10K | 28–33% | 31–36% | 35–40% | 28–33% |
| Half | 30–35% | 33–38% | 38–43% | 30–35% |
| Trail | 30–35% | 35–40% | 40–45% | 35–40% |
| Marathon | 32–38% | 35–42% | 40–45% | 32–38% |

**Short plan adjustment:** Plans ≤ 10 weeks reduce both min and max ratios by 0.03 (floored at 0.25 minimum).

**Within-phase progression:**
```
progression = week_in_phase / (total_in_phase - 1)
ratio = min_ratio + (max_ratio - min_ratio) × progression
```

**Recovery week adjustment:** 15% reduction, floored at max(0.20, min_ratio - 0.05).

### 8.2 Long Run Distance Caps

Experience-tiered caps prevent oversized long runs:

| Distance | Beginner | Intermediate | Advanced | Hard Ceiling |
|----------|----------|-------------|----------|-------------|
| 5K | 7 km | 8 km | 10 km | 14 km |
| 10K | 12 km | 15 km | 16 km | 22 km |
| Half | 18 km | 20 km | 22 km | 28 km |
| Trail | 20 km | 24 km | 28 km | 32 km |
| Marathon | 28 km | 32 km | 35 km | 38 km |

**Volume-aware scaling:** When `weekly_km × 0.30 > base_cap`, the cap scales up to `min(weekly_km × 0.30, hard_ceiling)`. This prevents high-volume runners from being artificially constrained.

**Experience level derivation** (from weekly mileage):
- Beginner: < 20 km/week
- Intermediate: 20–40 km/week
- Advanced: 40+ km/week

### 8.3 Long Run Floor

```
min_long_run = min(target_distance × 0.25, total_km)
# Recovery weeks:
min_long_run = min(target_distance × 0.20, total_km)
```

The final long run distance: `max(min_long_run, min(ratio × total_km, cap))`

### 8.4 Performance Generator Long Run

The performance generator uses a simpler calculation:
```
long_run_km = weekly_km × 0.30
```

Capped by race distance:
- ≤ 10K: max 15 km
- ≤ Half: max 22 km
- > Half: max 32 km

Build/peak phases with long runs ≥ 12 km add a race-pace finish segment: `min(4, distance × 0.3)` km at race pace.

---

## 9. Quality Caps

### 9.1 Two-Layer Cap System

Every quality workout is capped by the **minimum** of two limits:

**Layer 1 — Structural cap:** Quality workouts may not exceed 85% of the long run distance.
```
MAX_QUALITY_VS_LONG_RUN = 0.85
```

**Layer 2 — Physiological caps** (distance-specific, in km):

| Distance | Tempo | Interval | Hill |
|----------|-------|----------|------|
| 5K | 6.0 | 5.0 | 5.0 |
| 10K | 10.0 | 8.0 | 6.0 |
| Half | 14.0 | 10.0 | 8.0 |
| Trail | 12.0 | 8.0 | 12.0 |
| Marathon | 18.0 | 12.0 | 10.0 |

**Base phase reduction:** All physiological caps are multiplied by 0.80 during the base phase.

### 9.2 Easy Run Caps

```
MAX_EASY_VS_LONG_RUN = 0.95
```

Individual easy runs may not exceed 95% of the long run distance.

### 9.3 Shortfall Recovery

When quality caps reduce workout distances below target, easy runs are expanded:

**Standard generator:** If the easy budget after capping leaves a shortfall > 0.5 km, easy runs are expanded up to `long_run × 1.20` (120% of long run):
```
relaxed_max = long_run_distance × 1.20
extra_per = shortfall / easy_runs
capped = min(d + extra_per, relaxed_max) for each easy run
```

**Standard generator weekly scaling:** After all workouts are assembled:
- If actual total > target × 1.03: scale all distances down proportionally
- If actual total < target × 0.97: expand easy and long runs to fill the gap

### 9.4 Unified Cap Enforcement

`enforce_week_caps()` in `quality_caps.py` is used by both the standard and performance generators. It operates on workout lists in-place and handles both dict-style and ORM-style workout objects. Quality types recognized: `tempo`, `interval`, `hill`, `vo2max`, `race_pace`, `fartlek`.

### 9.5 Performance Generator Minimum Easy Run Floor

After quality caps and easy allocation, the performance generator enforces:
```
min_easy_km = max(3.0, long_dist × 0.20)
easy_run_km = max(easy_run_km, min_easy_km)
```

This prevents sub-1 km easy runs that would occur when quality workouts consume most of the weekly volume.

---

## 10. Workout Scheduling

### 10.1 Weekly Day Assignment (Standard Generator)

| Day | Index | Assignment |
|-----|-------|-----------|
| Sunday | 0 | Easy or rest |
| Monday | 1 | Recovery (active recovery — swimming/walking, 0 km) |
| Tuesday | 2 | Quality slot 1 (hill > interval > tempo) |
| Wednesday | 3 | Quality slot 2 or easy |
| Thursday | 4 | Quality slot 3 or easy |
| Friday | 5 | Easy or rest |
| Saturday | 6 | Long run |

**Quality slot priority order:** hill → interval → tempo (ensures harder sessions get earlier midweek slots for maximum recovery before the weekend long run).

**2-run week spacing:** When only 1 easy + 1 long, the easy run is anchored on Wednesday (day index 2) to maintain ~3-day spacing from the Saturday long run on either side. Default left-to-right fill would place it Monday, creating a lopsided 5-day gap.

### 10.2 Weekly Day Assignment (Performance Generator)

| Day | Assignment |
|-----|-----------|
| 1 (Mon) | Easy or rest |
| 2 (Tue) | Quality slot 1 |
| 3 (Wed) | Easy or rest |
| 4 (Thu) | Easy or rest |
| 5 (Fri) | Quality slot 2 |
| 6 (Sat) | Easy or rest |
| 7 (Sun) | Long run |

Quality slots use phase-prioritized types, cycling weekly.

---

## 11. Workout Construction

### 11.1 Standard Generator Workouts

**Long run** — Rotates through variants:
1. Steady easy (E zone, upper range)
2. Marathon-pace finish (80% easy, 20% at M pace)
3. Conversational (steady easy)

Key workouts override with specialized structures in build/peak phases.

**Easy run** — Variants cycle through:
1. Recovery pace
2. With strides (4-6 × 100m strides at the end)
3. Conversational

**Tempo run** — Structure: 2 km warmup + tempo effort + 2 km cooldown. Variations: continuous, cruise intervals, tempo with surges.

**Interval run** — Gated by base mileage:
- < 40 km/week: 400m reps (6×400m, pyramid, hill repeats)
- ≥ 40 km/week: Full suite (Yasso 800s, 5×1000m, 1200m repeats)

**Hill workout** — Variations: 10×30s steep repeats, 5×2min long climbs, 8×20s bounds.

### 11.2 Performance Generator Workouts

All performance workouts are segment-based with explicit warmup/main/cooldown structure:

**Tempo** — 2 km warmup → tempo_km at Zone 3 → 2 km cooldown

**VO₂max** — 2 km warmup → N × Xm intervals at Zone 4 (with recovery) → 2 km cooldown

**Race Pace** — 2 km warmup → race_km at Zone 5 → 2 km cooldown

**Fartlek** — 2 km warmup → N surges of 1-3 min at Zone 4 with easy recovery → 2 km cooldown. Surges: `max(4, min(10, (total_km - 4) × 1.5))`

**Long Run** — Easy pace, with optional race-pace finish (build/peak, ≥12 km): last `min(4, distance × 0.3)` km at race pace

**Easy** — Single segment at Zone 1

### 11.3 Key Workout Library Overlay

During build and peak phases, generic workout descriptions are replaced with curated, race-specific key workouts. Selection:

1. Filter by target distance, phase, and workout type
2. Filter by terrain (flat vs hilly for trail)
3. Rotate through candidates: `candidates[week_in_phase % len(candidates)]`

When VDOT zones are available, generic cues in descriptions are replaced with specific paces (e.g., "threshold pace" → "5:45/km (T-pace)").

Steps are resolved in order: explicit steps → steps_builder → parse structure string.

---

## 12. Strength Training Integration

### 12.1 Attachment Rules

Strength sessions attach to easy runs only. Taper phase limits to the first easy run per week (one session total).

### 12.2 Phase Focus Rotations

| Phase | Standard Rotation | Trail Rotation |
|-------|------------------|----------------|
| Base | Lower body → Core | Lower body → Trail stability → Core |
| Build | Lower body → Core → Plyometric | Lower body → Trail stability → Plyometric |
| Peak | Lower body → Plyometric → Core | Lower body → Plyometric → Trail stability |
| Taper | Core only | Core only |

### 12.3 Phase Modifiers

| Phase | Sets | Duration | Note |
|-------|------|----------|------|
| Base | Baseline | Baseline | Foundation |
| Build | Baseline | +5 min | Volume increase |
| Peak | Baseline | Baseline | Explosive tempo |
| Taper | -1 set | -10 min | Maintenance |

### 12.4 Experience Scaling

- Beginner (< 20 km/week): Bodyweight exercises, higher reps
- Intermediate (20-40 km/week): Single-leg work, moderate complexity
- Advanced (40+ km/week): Plyometric progressions, higher intensity

---

## 13. Beginner Plans (Couch to 5K)

### 13.1 Eligibility

- `current_km == 0` and `target_distance ∈ {5.0, 10.0}`
- `max_runs_per_week` capped at 3
- Minimum 8 weeks

### 13.2 C25K Progression

| Week | Run | Walk | Repeats | Total |
|------|-----|------|---------|-------|
| 1 | 1 min | 1.5 min | 8× | 20 min |
| 2 | 1.5 min | 2 min | 6× | 21 min |
| 3 | 3 min | 3 min | 4× | 24 min |
| 4 | 5 min | 3 min | 4× | 32 min |
| 5 | 8 min | 5 min | 3× | 39 min |
| 6 | 10 min | 3 min | 3× | 39 min |
| 7 | 15 min | 3 min | 2× | 36 min |
| 8 | 20 min | 2 min | 1× | 30 min |
| 9 | 25 min | 0 | 1× | 25 min |
| 10 | 30 min | 0 | 1× | 30 min |

Distance estimates use an assumed 8 min/km beginner pace.

### 13.3 Plan Compression

- 8-week plan: skips weeks 2 and 9; merges early weeks, preserves run/walk-to-continuous transition
- 9-week plan: skips week 2; keeps full transition

### 13.4 10K Extension

Weeks beyond C25K (weeks 11+) introduce:
- Long run: `base_duration × 0.10` km (where `base_duration = 25 + (week - 1) × 5 min`)
- Easy run: `base_duration × 0.06` km
- Tempo run: `base_duration × 0.07` km

Extension phases progress through build → peak → taper.

---

## 14. Heart Rate Zone System

A 5-zone model based on percentage of maximum heart rate:

| Zone | Name | % Max HR | Purpose |
|------|------|----------|---------|
| 1 | Recovery | 50–60% | Active recovery, warm-up |
| 2 | Aerobic | 60–70% | Conversational, aerobic base |
| 3 | Tempo | 70–80% | Lactate clearance, stamina |
| 4 | Threshold | 80–90% | Lactate threshold |
| 5 | VO₂max | 90–100% | Peak oxygen uptake |

Workout-to-zone mapping: Easy/Long → Zone 2, Recovery → Zone 1, Tempo → Zone 3, Interval/Hill → Zone 5.

Max HR estimation: derived from run data when available, default 190 BPM. Values below 140 BPM rejected as sensor errors.

---

## 15. Effort Quality Scoring

Logged runs are scored 0–100 against the planned workout:

**Effort component** (40% weight, 50% for hills): Compares perceived effort (1–10) against expected ranges:

| Workout Type | Expected PE |
|-------------|------------|
| Easy | 3–5 |
| Recovery | 1–3 |
| Long | 5–7 |
| Tempo | 6–7 |
| Interval | 7–9 |
| Hill | 7–8 |

**Pace component** (60% weight, 50% for hills): Compares actual pace against VDOT target with ±8% tolerance.

**Labels:** "Nailed it" (90+), "On track" (70–89), "Too easy" (<70, effort low), "Too hard" (<70, effort high).

---

## 16. Adaptive Plan Adjustment

### 16.1 Trigger

Adaptation activates when ≥3 runs are logged.

### 16.2 Signal Composition

A composite multiplier combines three signals with weights:

| Signal | Weight | What It Measures |
|--------|--------|-----------------|
| Volume adherence | 50% | Actual km vs planned km |
| Perceived effort | 30% | Whether effort felt appropriate |
| Completion rate | 20% | % of scheduled workouts completed |

### 16.3 Recency Weighting

Exponential decay with 3-week half-life:
```
weight = 2^(-weeks_ago / 3)
```

This ensures recent performance dominates: 1 week ago = 0.79×, 3 weeks = 0.50×, 6 weeks = 0.25×.

### 16.4 VDOT Recalibration

If computed VDOT shifts ≥ 1.0 point from the plan's baseline, pace zones are recalibrated across all future workouts.

### 16.5 Structural Preservation

When scaling future weeks:
- Quality caps, long run ratios, and polarized distribution remain enforced
- Warm-up/cool-down distances are absolute (not scaled)
- Work intervals scale proportionally

### 16.6 Adaptation Services

| Service | Purpose |
|---------|---------|
| `plan_adjuster.py` | Scale future workout distances based on composite multiplier |
| `run_mapper.py` | Map logged runs to planned workouts |
| `recalibrator.py` | Adjust plan based on strategy (volume_up/down, pace_up/down) |
| `alert_checker.py` | Detect overtraining, undertraining, missed workouts |
| `performance_analyzer.py` | Analyze fitness progression |
| `type_swapper.py` | Swap workout types while maintaining structure |
| `skipped_detector.py` | Detect consistently skipped workout types |

---

## 17. Plan Validation

### 17.1 Standard Generator Validation

Every generated week is checked against:

1. All workouts have `description` field
2. No legacy `recovery_rest` labels (must be `recovery`)
3. No easy run exceeds 125% of long run distance
4. Total weekly distance within ±5% of target
5. Recovery days have zero distance

### 17.2 Performance Generator Validation

1. No quality workout exceeds 110% of long run distance
2. No easy run below 2.0 km
3. Total weekly volume within 15% tolerance of target (wider tolerance because quality caps and minimum easy floors can push totals above target)

### 17.3 Post-Validation Scaling (Standard Generator)

| Condition | Action |
|-----------|--------|
| actual > target × 1.03 | Scale all distances down: `distance × (target / actual)` |
| actual < target × 0.97 | Expand easy and long runs: `deficit / count(easy + long)` per run |

---

## 18. Investigation Findings and Fixes Applied

### 18.1 Performance Generator — Original Issues (Pre-Fix)

The original performance generator had severe workout distribution skew:

| Issue | Severity | Root Cause |
|-------|----------|------------|
| Quality workouts used race distance instead of weekly volume | Critical | `distance_km` parameter was target race distance, not weekly_km |
| Fartlek used hardcoded distances (8-12 km) | High | Phase-based fixed values, ignoring runner capacity |
| No quality caps applied | High | `enforce_week_caps()` not called |
| No minimum easy run floor | Medium | Easy runs could be 0.0-0.5 km |
| No validation layer | Medium | Skewed plans returned without checks |

**Quantified impact (pre-fix):** Quality workouts reached up to 3.12× the long run distance for low-mileage runners. Easy runs dropped to 0.0 km. Plans were only acceptable when starting mileage ≥ 35 km/week.

### 18.2 Fixes Applied

All critical and high-severity issues have been resolved:

1. **Quality workouts scaled to weekly volume** — All performance workout builders now accept `weekly_km` and use phase-specific percentages (20-30% for tempo, 15-20% for VO₂max, etc.)

2. **Quality caps enforced** — `enforce_week_caps()` is called after workout generation, applying the same 85% structural cap and physiological caps used by the standard generator

3. **Minimum easy run floor** — Easy runs are floored at `max(3.0, long_dist × 0.20)` km

4. **Validation layer added** — `_validate_week_plan()` checks quality-vs-long-run ratio, minimum easy distance, and volume tolerance

5. **Fartlek scaled to weekly volume** — Uses `weekly_km × phase_pct` with [5, 14] km bounds

6. **Volume shortfall recovery (standard generator)** — Easy runs expand up to 120% of long run when quality caps cause shortfall

### 18.3 Remaining Accepted Edge Cases

| Edge Case | Scope | Why It's Acceptable |
|-----------|-------|-------------------|
| Beginner plans (0 km) produce no quality caps warnings | BeginnerPlanGenerator | Different generator, run/walk structure doesn't use cap system |
| 12-15% week-over-week jumps at phase transitions | Rare, 6 scenarios | Phase boundary arithmetic; marginal and within injury-safe range |
| Trail 10 km/week long-run dominance | Very low volume trail | Structural: long run floor (7.5 km) naturally dominates at low total volumes |

### 18.4 Unapplied Optional Fix

**Lower easy cap (0.95 → 0.80):** The investigation recommended optionally reducing `MAX_EASY_VS_LONG_RUN` from 0.95 to 0.80. This was deliberately not applied because: (a) it would increase volume shortfall in high-volume plans, (b) the shortfall recovery mechanism already handles the 0.95 cap adequately, and (c) the investigation doc itself flagged this as requiring careful cross-scenario testing first.

---

## 19. Nutrition Integration

Body weight (collected during plan generation) drives:
- Daily caloric targets based on training load
- Macronutrient ratios (carbs/protein/fat) scaled to weekly volume
- Pre/during/post-run nutrition timing
- Hydration targets

Nutrition guidance adjusts as weekly mileage progresses through phases.

---

## 20. Complete Generation Flow

### 20.1 Standard Plan Generation

```
User Input → Validation
  ↓
current_km == 0? → BeginnerPlanGenerator (5K/10K only)
  ↓ (no)
RunnerProfile enrichment (VDOT, actual weekly km)
  ↓
calculate_weekly_progression(current_km, target_distance, weeks, max_runs, vdot)
  ↓
For each week 1..N:
  ├─ calculate_phases() → determine phase, recovery status
  ├─ get_workout_distribution() → count of each workout type
  ├─ schedule_workout_types() → assign types to days
  ├─ calculate_long_run_distance() → long run km
  ├─ calculate_quality_distances() → quality km per type
  ├─ apply_quality_caps() → enforce structural + physiological limits
  ├─ allocate_easy_distances() → distribute remaining km
  ├─ build_workout_for_type() → construct each workout
  ├─ overlay_key_workout() → attach library descriptions (build/peak)
  ├─ generate_strength_session() → attach to easy runs
  ├─ generate_coaching_note() → add rationale
  ├─ scale if actual ≠ target (±3%)
  └─ validate_week_plan()
  ↓
Return training_plan[]
```

### 20.2 Performance Plan Generation

```
User Input → Validation (pace improvement ≤ 15%)
  ↓
calculate_phases() → phase durations
  ↓
calculate_vdot() from current pace + distance
  ↓
calculate_training_zones() → 5-zone system (from VDOT or goal pace fallback)
  ↓
calculate_weekly_progression(current_km, target_distance, weeks, runs, vdot)
  ↓
For each week 1..N:
  ├─ determine phase, recovery, week_in_phase
  ├─ generate_long_run(zones, weekly_km, ...)
  ├─ generate quality workouts (tempo/vo2max/race_pace/fartlek from phase priority)
  ├─ enforce_week_caps() → cap quality and easy vs long run
  ├─ fill remaining with easy runs (min 3km floor)
  ├─ fill unscheduled days with rest
  ├─ overlay_key_workout() → library descriptions (build/peak)
  ├─ generate_coaching_note() → rationale
  └─ validate_week_plan()
  ↓
Return plan with zones, phases, summary
```

### 20.3 Beginner Plan Generation

```
User Input → current_km == 0, distance ∈ {5K, 10K}
  ↓
Cap max_runs at 3
  ↓
Select C25K sequence (compressed if < 10 weeks)
  ↓
Weeks 1-10: generate_couch_to_5k_week()
  ├─ Run/walk intervals at assumed 8 min/km
  ├─ 3 sessions per week (easy runs)
  └─ Progressive increase in run duration, decrease in walk
  ↓
Weeks 11+ (10K only): generate_10k_extension_week()
  ├─ Introduces long runs, tempo, easy runs
  ├─ Phases: build → peak → taper
  └─ Distance from duration-based estimates
  ↓
Return plan
```

---

## 21. Safety Guardrails Summary

| Guardrail | Where | What It Prevents |
|-----------|-------|-----------------|
| 10% week-over-week cap | `mileage_progression.py` | Overuse injuries from volume spikes |
| Recovery week at 65% | `mileage_progression.py` | Accumulated fatigue without absorption |
| Quality ≤ 85% of long run | `quality_caps.py` | Quality session exceeding long run dominance |
| Easy ≤ 95% of long run | `quality_caps.py` | Easy runs becoming de facto long runs |
| Physiological caps by distance | `quality_caps.py` | Excessive quality volume for the race distance |
| Base phase 20% quality reduction | `quality_caps.py` | Too-intense quality work before aerobic base |
| Interval gating (< 40 km/week) | `workout_builders.py` | Long intervals without aerobic base |
| 80/20 polarized ratio validation | `workout_distribution.py` | Too much or too little intensity |
| Long run experience-tiered caps | `long_run_calculator.py` | Oversized long runs for experience level |
| Minimum easy run floor (3 km) | `performance_plan_generator.py` | Sub-1 km easy runs |
| Pace improvement ≤ 15% | `performance_plan_generator.py` | Unrealistic goal paces |
| VDOT clamped to [25, 85] | `vdot_calculator.py` | Erroneous VDOT from bad data |
| Pace < 2:30/km rejected | `vdot_calculator.py` | GPS artifacts |
| High-water mark recovery tracking | `mileage_progression.py` | Post-recovery ramp starting from dip |
| Weekly scaling (±3% tolerance) | `plan_generator.py` | Accumulated rounding errors |
| Shortfall recovery to 120% long run | `plan_generator.py` | Quality caps causing undertrained weeks |
