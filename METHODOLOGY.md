# RunCoach Training Plan Methodology

This document details exactly how RunCoach generates, scales, and adapts training plans, including the physiological principles, mathematical models, and coaching methodologies that underpin every decision.

---

## 1. Foundational Framework: Jack Daniels' VDOT System

### 1.1 What VDOT Is

VDOT is a single-number representation of a runner's current aerobic fitness, derived from a recent race performance. It originates from Jack Daniels' *Running Formula* (3rd ed.) and represents the runner's maximal oxygen uptake (VO₂max) adjusted for the fact that no one can sustain 100% of VO₂max for race duration.

### 1.2 VDOT Calculation

The system uses two physiological equations from Daniels' research:

**Oxygen cost at velocity** (m/min):
```
VO₂ = -4.60 + 0.182258 × v + 0.000104 × v²
```

**Fraction of VO₂max sustainable for time t** (minutes):
```
%VO₂max = 0.8 + 0.1894393 × e^(-0.012778 × t) + 0.2989558 × e^(-0.1932605 × t)
```

VDOT is then computed as:
```
VDOT = VO₂ / %VO₂max
```

The result is clamped to 25–85 (beginner to world-class). Paces faster than 2:30/km over 2+ km are rejected as GPS artifacts.

### 1.3 Training Pace Zones

From a VDOT value, five training zones are derived by solving the quadratic equation for velocity at specific fractions of VO₂max:

| Zone | Key | %VO₂max | Purpose |
|------|-----|---------|---------|
| Easy (slow) | E_slow | 65% | Recovery runs, conversational |
| Easy (fast) | E_fast | 75% | Brisk easy runs |
| Marathon | M | 79% | Marathon goal pace |
| Threshold | T | 86% | Tempo / lactate threshold |
| Interval | I | 98% | VO₂max intervals |
| Repetition | R | 105% | Speed / running economy |

The Easy zone is further subdivided:
- **Recovery**: 59–65% — very easy, active recovery
- **Easy**: 65–72% — standard easy run
- **Long Run**: 72–76% — upper easy range for long runs

### 1.4 Race Time Prediction

A binary search solves `VO₂(d/t) / %VO₂max(t) = VDOT` to predict finish times for any distance. Confidence ranges use ±1.5 VDOT for road races and ±2.0 for trail (where terrain variance adds noise).

---

## 2. Plan Architecture: Four-Phase Periodization

Every plan is divided into four sequential phases, with proportions determined by race distance:

### 2.1 Phase Proportions by Distance

| Distance | Base | Build | Peak | Taper |
|----------|------|-------|------|-------|
| 5K | 35% | 30% | 20% | 1 week |
| 10K | 35% | 30% | 15% | 1 week |
| Half Marathon | 35% | 35% | 10% | 2 weeks |
| Trail (30K) | 35% | 35% | 10% | 2 weeks |
| Marathon | 30% | 35% | 5% | 3 weeks |

Taper weeks are prescribed as fixed counts (not percentages), then remaining weeks are split proportionally among base/build/peak. Rounding adjustments trim from the largest phase to hit the exact week count.

### 2.2 Phase Objectives

**Base Phase** — Builds aerobic foundation to 70% of peak mileage. Introduces one light quality session (strides for 5K/10K, short threshold for half/marathon, easy hills for trail). Recovery every 4th week.

**Build Phase** — Ramps from 70% to 100% of peak mileage. Quality sessions increase to 1–2 per week depending on runs-per-week allowance. Recovery every 4th week.

**Peak Phase** — Maintains near-peak mileage with slight oscillation (97% → 98% → 99%) to prevent the body from adapting to a flat ceiling. Maximum quality load. 4+ week peaks include a mid-phase recovery week at week 3.

**Taper Phase** — Progressive volume reduction to arrive fresh on race day. Distance-appropriate curves:

| Distance | Taper Length | Week-by-Week (% of peak) |
|----------|-------------|--------------------------|
| 5K | 1 week | 55% |
| 10K | 1 week | 55% |
| Half Marathon | 2 weeks | 75% → 55% |
| Trail | 2 weeks | 72% → 50% |
| Marathon | 3 weeks | 85% → 70% → 50% |

Trail tapers more aggressively than half marathon because eccentric damage from downhill running requires extra recovery time.

### 2.3 Recovery Week Schedule

- **Base/Build**: Every 4th week (only if phase ≥ 4 weeks)
- **Peak**: Week 3 of 4+ week peaks
- **Taper**: No recovery weeks (taper itself is the recovery)
- **Reduction**: 65% of the high-water mark (a ~35% cut gives real absorption without losing fitness)

---

## 3. Weekly Mileage Progression

### 3.1 Peak Mileage Determination

Peak mileage is the minimum of two calculations:

1. **Duration-based**: `current_km × (1 + 1.5 × weeks/16)`, capped at 2.6×
2. **Distance-based ideal**:
   - 5K: max(25, current × 2.0)
   - 10K: max(30, current × 2.2)
   - Half: max(40, current × 2.3)
   - Trail: max(45, current × 2.0)
   - Marathon: max(50, current × 2.0)

**VDOT adjustment**: Higher-fitness runners can absorb more volume:
```
vdot_factor = 0.95 + min(0.13, (vdot - 30) / 350)
```
This yields 0.95× at VDOT 30, 1.0× at VDOT 50, and 1.08× at VDOT 65+.

The final peak is clamped to at least `current_km × 1.2` (a 20% minimum increase over the plan).

### 3.2 The 10% Rule

A core safety invariant: **no non-recovery week increases more than 10% over the previous non-recovery week**. This prevents overuse injuries from rapid volume spikes.

The progression uses a "high-water mark" that tracks the highest non-recovery milestone. Recovery weeks dip to 65% of this mark but do **not** reset it — the post-recovery ramp resumes from the pre-recovery level.

### 3.3 Phase-by-Phase Ramp

**Base Phase**: Linear interpolation from `current_km` to `70% of peak`, clamped by the 10% cap and a minimum 1% bump (to avoid flat weeks that look like plateaus).

**Build Phase**: Linear interpolation from the base endpoint to full peak, same clamping rules.

**Peak Phase**: Oscillates around peak mileage — 97%, 98%, 99% of peak, repeating. The first peak week is capped to +10% over the build high-water to prevent an abrupt jump.

### 3.4 Minimum Mileage Validation

Starting mileage must meet distance-specific thresholds:

| Distance | Min km/week | Rationale |
|----------|------------|-----------|
| 5K | 5 | Base aerobic fitness |
| 10K | 10 | Sustained running ability |
| Half | 15 | Endurance foundation |
| Trail | 15 | Trail-specific base |
| Marathon | 25 | Significant base fitness |

Zero-mileage runners are routed to a Couch-to-5K program (5K/10K only, minimum 8 weeks).

---

## 4. Workout Type Distribution

### 4.1 Polarized Training (80/20 Rule)

RunCoach enforces a polarized training model where ~80% of runs are easy and ~20% are quality (tempo, interval, hill). Trail gets slightly easier targets (85/15 in build, 80/20 in peak) because terrain naturally provides intensity through elevation.

| Phase | Hard % Target | Trail Hard % |
|-------|--------------|--------------|
| Base | 10% | 10% |
| Build | 20% | 15% |
| Peak | 25% | 20% |
| Taper | 10% | 10% |

If the hard percentage exceeds the target by >5%, a quality session is converted to easy. If under by >10% in build/peak (and ≥3 runs), an easy run is converted to interval.

### 4.2 Quality Workout Count by Phase and Runs/Week

| Phase | ≤2 runs | 3 runs | 4 runs | 5+ runs |
|-------|---------|--------|--------|---------|
| Base | 0 | 0 | 1 | 1 |
| Build (weeks 1-2) | 0 | 0 | 1 | 1 |
| Build (weeks 3+) | 0 | 1 | 1 | 2 |
| Peak | 0 | 1 | 1 | 2 |
| Taper | 0 | 0 | 0 | 0 |

At 2 runs/week (minimum effective dose), the week is always 1 long + 1 easy — quality workouts need a third running day to maintain the 80/20 balance.

### 4.3 Quality Type Selection by Distance Profile

**5K**: VO₂max emphasis — intervals dominate (2 intervals when 2 quality slots available)

**10K**: Balanced — 1 interval + optional tempo

**Half Marathon**: Balanced — 1 interval + optional tempo

**Marathon**: Tempo/marathon-pace emphasis; peak phase drops intervals entirely in favor of double tempo

**Trail (hilly)**: Hills are the dominant stimulus. With 2 quality slots: hills every week + rotating second (intervals weeks 1-2 of 4-week cycle, tempo weeks 3-4). With 1 slot: hills 2/3 of weeks, interval on the off week (3-week cycle).

**Trail (flat)**: No hill access, tempo replaces the hill stimulus. With 2 quality slots: weeks 1-2 get tempo + interval, weeks 3-4 get double tempo.

### 4.4 Distance Distribution Percentages by Phase

**Base Phase**:
| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 35% | 0% | 5% | 0% | 60% |
| 10K | 40% | 0% | 5% | 0% | 55% |
| Half | 45% | 5% | 0% | 0% | 50% |
| Trail | 45% | 0% | 0% | 5% | 50% |
| Marathon | 45% | 5% | 0% | 0% | 50% |

**Build Phase**:
| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 35% | 12% | 10% | 5% | 38% |
| 10K | 40% | 12% | 10% | 5% | 33% |
| Half | 45% | 10% | 8% | 4% | 33% |
| Trail | 45% | 6% | 6% | 8% | 35% |
| Flat Trail | 45% | 14% | 6% | 0% | 35% |
| Marathon | 45% | 10% | 8% | 4% | 33% |

**Peak Phase** (similar to build, slightly reduced long run share):
| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 33% | 12% | 10% | 5% | 40% |
| 10K | 38% | 12% | 10% | 5% | 35% |
| Half | 43% | 10% | 8% | 4% | 35% |
| Trail | 43% | 6% | 6% | 8% | 37% |
| Flat Trail | 43% | 14% | 6% | 0% | 37% |
| Marathon | 43% | 10% | 8% | 4% | 35% |

**Taper Phase** (quality reduced, easy increased):
| Distance | Long | Tempo | Interval | Hill | Easy |
|----------|------|-------|----------|------|------|
| 5K | 30% | 12% | 0% | 0% | 58% |
| 10K | 35% | 12% | 0% | 0% | 53% |
| Half | 40% | 10% | 0% | 0% | 50% |
| Trail | 40% | 6% | 0% | 4% | 50% |
| Marathon | 40% | 10% | 0% | 0% | 50% |

---

## 5. Long Run Calculation

### 5.1 Long Run Ratio by Phase and Distance

The long run's share of weekly mileage increases with race distance and phase progression:

| Distance | Base | Build | Peak | Taper |
|----------|------|-------|------|-------|
| 5K | 25–30% | 28–32% | 30–35% | 25–30% |
| 10K | 28–33% | 31–36% | 35–40% | 28–33% |
| Half | 30–35% | 33–38% | 38–43% | 30–35% |
| Trail | 30–35% | 35–40% | 40–45% | 35–40% |
| Marathon | 32–38% | 35–42% | 40–45% | 32–38% |

The ratio progresses linearly within each phase from min to max. Recovery weeks apply a 15% reduction (minimum 20% of race distance).

### 5.2 Long Run Distance Caps

Experience-tiered caps prevent the long run from growing too large:

| Distance | Beginner | Intermediate | Advanced | Hard Ceiling |
|----------|----------|-------------|----------|-------------|
| 5K | 7 km | 8 km | 10 km | 14 km |
| 10K | 12 km | 15 km | 16 km | 22 km |
| Half | 18 km | 20 km | 22 km | 28 km |
| Trail | 20 km | 24 km | 28 km | 32 km |
| Marathon | 28 km | 32 km | 35 km | 38 km |

When weekly volume is high enough that the static cap would prevent filling target volume, the cap scales up to 30% of weekly km (bounded by the hard ceiling).

### 5.3 Long Run Variants

Long runs rotate through three variants:
1. **Steady easy** — entire run at long run pace (E zone, upper range)
2. **Marathon-pace finish** — 80% easy, final 20% at marathon pace
3. **Nutrition practice** — steady easy with fueling every 45–60 minutes

Key workouts can override these with specialized structures:
- **Alternating MP blocks** — alternating easy and marathon-pace 2 km blocks
- **Fast finish** — easy aerobic base with a hard T-pace final segment (2–4 km)
- **Rolling hills** — steady effort on varied terrain (pace by effort, not watch)
- **Depletion** — fasted/low-carb long run for mitochondrial adaptation (marathon)

---

## 6. Quality Workout Distance Allocation

### 6.1 Proportional Allocation

Quality workout distances are derived from phase distribution percentages, applied to the remaining km after subtracting the long run:

```
tempo_km = remaining_km × (tempo% / (1 - long%))
interval_km = remaining_km × (interval% / (1 - long%))
hill_km = remaining_km × (hill% / (1 - long%))
```

### 6.2 Quality Caps

Two layers of caps prevent any single quality workout from becoming excessive:

**Structural cap**: Quality workouts may not exceed 85% of the long run distance. This ensures the long run remains the dominant session of the week.

**Physiological caps** (distance-specific, in km):

| Distance | Tempo | Interval | Hill |
|----------|-------|----------|------|
| 5K | 6 | 5 | 5 |
| 10K | 10 | 8 | 6 |
| Half | 14 | 10 | 8 |
| Trail | 12 | 8 | 12 |
| Marathon | 18 | 12 | 10 |

Base phase reduces all quality caps by 20%.

### 6.3 Easy Run Caps

Individual easy runs may not exceed 95% of the long run distance. If quality caps cause a volume shortfall, easy runs are expanded up to 120% of the long run to meet the weekly target.

---

## 7. Workout Scheduling

### 7.1 Day Assignment Rules

The weekly schedule follows these principles:

1. **Day 2 is always recovery** — active recovery (swimming/walking) after the presumed long run day, positioned early in the week for optimal spacing
2. **Long run on Day 6 (Saturday)** — traditional weekend placement
3. **Quality sessions on Days 3–4 (Tue–Wed)** — midweek placement with adequate recovery before and after
4. **Easy runs fill remaining slots** — distributed to avoid consecutive hard days
5. **Rest days fill the gaps** — at least 1 rest day per week

For 2-run weeks (1 easy + 1 long), the easy run is anchored on Day 3 (Wednesday) to sit ~3 days from the Saturday long run on either side, avoiding lopsided 5-day gaps.

### 7.2 Interval Guardrails

Interval sessions are gated by base mileage:
- **<40 km/week**: 400m reps (and 200m for very low-base 5K runners)
- **≥40 km/week**: Full suite including 800m and 1000m intervals

This protects less-experienced runners from the injury risk of long intervals without sufficient aerobic base.

---

## 8. Key Workout Library

During Build and Peak phases, generic interval/tempo descriptions are replaced with curated, race-specific key workouts that make plans feel coached rather than generated.

### 8.1 Selection Process

Key workouts are selected by:
1. Filtering by target distance, phase, and requested workout type
2. Filtering by terrain (flat vs. hilly for trail plans)
3. Rotating through available candidates using the week-in-phase index

### 8.2 Examples by Distance

**5K**:
- VO₂max 400m repeats (10–12 × 400m at 5K pace, 90s recovery)
- Race-pace 3 km block (2 × 1.5 km at goal pace)
- Cruise intervals (4 × 1 km at threshold, 60s recovery)
- Speed ladder (200m–400m–600m–800m–600m–400m–200m)

**10K**:
- Lactate threshold intervals (5 × 1200m at 10K pace)
- Progressive tempo (2 km easy → 4 km threshold → 1 km fast)
- VO₂max pyramid (400m–800m–1200m–800m–400m)

**Half Marathon**:
- Long tempo with MP finish (6 km threshold + 3 km at MP)
- Alternating MP long run (2 km easy / 2 km MP blocks)
- Race-pace simulation (8 km at goal half pace)

**Marathon**:
- Long run with MP blocks (alternating 3 km easy / 3 km MP)
- Depletion run (fasted long run for fat adaptation)
- Progressive long run (easy → steady → MP finish)
- Yasso 800s (10 × 800m at marathon goal pace)

**Trail**:
- Hill repeat ladder (30s → 60s → 90s → 60s → 30s)
- Rolling hills long run (effort-based pacing)
- Technical descent practice
- Uphill surge intervals

---

## 9. Strength Training Integration

Strength sessions are attached to easy runs and periodized across phases.

### 9.1 Phase Focus Rotations

| Phase | Standard Rotation | Trail Rotation |
|-------|------------------|----------------|
| Base | Lower body → Core | Lower body → Trail stability → Core |
| Build | Lower body → Core → Plyometric | Lower body → Trail stability → Plyometric |
| Peak | Lower body → Plyometric → Core | Lower body → Plyometric → Trail stability |
| Taper | Core only | Core only |

### 9.2 Phase Modifiers

| Phase | Sets | Duration | Note |
|-------|------|----------|------|
| Base | Baseline | Baseline | Foundation building |
| Build | Baseline | +5 min | Increased volume |
| Peak | Baseline | Baseline | Explosive tempo, controlled power |
| Taper | -1 set | -10 min | Maintenance only, preserve strength |

### 9.3 Experience Levels

Derived from weekly mileage:
- **Beginner**: <20 km/week — bodyweight exercises, higher reps
- **Intermediate**: 20–40 km/week — single-leg work, moderate complexity
- **Advanced**: 40+ km/week — plyometric progressions, higher intensity

Taper phase drops strength to only the first easy run of the week (one session total).

---

## 10. Heart Rate Zone System

A 5-zone model based on percentage of maximum heart rate:

| Zone | Name | % Max HR | Purpose |
|------|------|----------|---------|
| 1 | Recovery | 50–60% | Active recovery, warm-up |
| 2 | Aerobic | 60–70% | Conversational pace, aerobic base |
| 3 | Tempo | 70–80% | Lactate clearance, stamina |
| 4 | Threshold | 80–90% | Lactate threshold, race-day tolerance |
| 5 | VO₂max | 90–100% | Peak oxygen uptake, speed |

Workout-to-zone mapping:
- Easy/Long → Zone 2
- Recovery → Zone 1
- Tempo → Zone 3
- Interval/Hill → Zone 5

Max HR is estimated from run data when available, defaulting to 190 BPM. Values below 140 BPM are rejected as sensor errors.

---

## 11. Effort Quality Scoring

Logged runs are scored 0–100 against the planned workout using two components:

**Effort component** (40% for most, 50% for hills): Compares reported perceived effort (1–10) against expected ranges:

| Workout Type | Expected PE Range |
|-------------|------------------|
| Easy | 3–5 |
| Recovery | 1–3 |
| Long | 5–7 |
| Tempo | 6–7 |
| Interval | 7–9 |
| Hill | 7–8 |

**Pace component** (60% for most, 50% for hills): Compares actual pace against VDOT-based target pace with ±8% tolerance.

Labels: "Nailed it" (90+), "On track" (70–89), "Too easy" (<70, effort low), "Too hard" (<70, effort high).

---

## 12. Adaptive Plan Adjustment

Plans adapt based on logged performance when ≥3 runs are recorded.

### 12.1 Signal Composition

A composite multiplier combines three signals:
- **Volume adherence** (50%): How closely actual km matched planned km
- **Perceived effort** (30%): Whether effort felt appropriate
- **Completion rate** (20%): Percentage of scheduled workouts completed

### 12.2 Recency Weighting

Exponential decay with a 3-week half-life ensures recent performance weighs more heavily:
```
weight = 2^(-weeks_ago / 3)
```

### 12.3 VDOT Recalibration

If the runner's computed VDOT changes by ≥1.0 point from the plan's baseline, pace zones are recalibrated across all future workouts.

### 12.4 Structural Preservation

When scaling future weeks, the same quality caps, long run ratios, and polarized distribution rules are enforced. Step-level scaling preserves warm-up/cool-down distances (absolute) while scaling work intervals proportionally.

---

## 13. Beginner Plans (Couch to 5K)

True beginners (0 km/week) receive a run/walk progression plan for 5K or 10K only.

### 13.1 C25K Progression

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

For plans shorter than 10 weeks, early weeks are merged to preserve the critical run/walk-to-continuous transition. 10K plans add extension weeks beyond C25K with progressive long runs and introductory tempo segments.

---

## 14. Plan Validation

Every generated week is validated against these invariants:

1. All workouts have descriptions
2. Recovery days are labeled correctly (not legacy labels)
3. No easy run exceeds 125% of the long run distance
4. Total weekly distance matches target within ±5% tolerance
5. Recovery days have zero distance
6. Quality workouts respect structural and physiological caps

If actual totals exceed the target by >3%, all distances are scaled down proportionally. If they fall short by >3% (due to quality caps), easy and long runs are expanded to fill the gap.

---

## 15. Nutrition Integration

Body weight (collected during plan generation) is used to personalize:
- Daily caloric targets based on training load
- Macronutrient ratios (carbs/protein/fat) scaled to weekly volume
- Pre/during/post-run nutrition timing
- Hydration targets

Nutrition guidance adjusts dynamically as weekly mileage progresses through the phases.
