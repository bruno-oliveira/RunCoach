# Quality Workout System: Complete Analysis & Improvement Plan

> **Date:** 2026-05-03
> **Scope:** `app/core/training/key_workout_*.py`, `app/core/training/workout_*.py`, `app/core/generators/weekly_plan_builder.py`, `app/core/generators/performance_plan_generator.py`, `app/core/generators/performance_workout_builders.py`, templates

---

## 1. Quality Workout Types Inventory

### 1.1 Short-Distance Workouts (`key_workout_data.py`)

| Distance | ID | Type | Phases | Pace Zone |
|----------|-----|------|--------|-----------|
| 5K | `5k_vo2max_400s` | interval | build, peak | I |
| 5K | `5k_race_pace_3km` | tempo | build, peak | I |
| 5K | `5k_cruise_intervals` | tempo | build | T |
| 5K | `5k_threshold_run` | tempo | build | T |
| 5K | `5k_hill_sprints` | hill | build | R |
| 5K | `5k_pyramid` | interval | peak | I |
| 10K | `10k_cruise_intervals` | tempo | build, peak | T |
| 10K | `10k_goal_pace_segments` | tempo | build, peak | **10K** ⚠️ |
| 10K | `10k_tempo_progression` | tempo | peak | T |
| 10K | `10k_fartlek` | interval | build | **10K** ⚠️ |
| Half (21.1) | `half_progressive_long` | tempo | build, peak | M |
| Half (21.1) | `half_threshold_cruise` | tempo | build, peak | T |
| Half (21.1) | `half_race_pace_segments` | tempo | peak | M |
| Half (21.1) | `half_cutdown_long` | interval | build | M |

### 1.2 Long-Distance Workouts (`key_workout_data_long.py`)

| Distance | ID | Type | Phases | Pace Zone | Steps Builder |
|----------|-----|------|--------|-----------|---------------|
| Half (21.1) | `half_long_alternating_mp` | long | build, peak | M | `alternating_mp` |
| Half (21.1) | `half_long_fast_finish` | long | build, peak | T | `fast_finish` |
| Half (21.1) | `half_long_rolling_hills` | long | build | E | `rolling_hills` |
| Marathon (42.2) | `marathon_long_alternating_mp` | long | build, peak | M | `alternating_mp_3k` |
| Marathon (42.2) | `marathon_long_fast_finish` | long | build, peak | T | `fast_finish_4k` |
| Marathon (42.2) | `marathon_long_depletion` | long | build | E | `depletion` |
| Marathon (42.2) | `marathon_long_rolling_hills` | long | build | E | `rolling_hills` |
| Marathon (42.2) | `marathon_mp_long` | tempo | build, peak | M | — |
| Marathon (42.2) | `marathon_yasso_800s` | interval | build, peak | I | — |
| Marathon (42.2) | `marathon_progressive_long` | tempo | build | M | — |
| Marathon (42.2) | `marathon_tempo_cutdown` | tempo | peak | T | — |
| Marathon (42.2) | `marathon_mp_cutdown` | interval | peak | T | — |
| Marathon (42.2) | `marathon_easy_long_fueling` | tempo | build | E | — |
| Marathon (42.2) | `marathon_peak_progressive` | tempo | peak | M | — |
| 10K | `10k_long_fast_finish` | long | build, peak | T | `fast_finish_2k` |
| Trail (30.0) | `trail_elevation_repeats` | hill | build, peak | T | — |
| Trail (30.0) | `trail_time_on_feet` | tempo | build, peak | E | — |
| Trail (30.0) | `trail_technical_terrain` | interval | build | E | — |
| Trail (30.0) | `trail_power_hike` | hill | peak | E | — |
| Trail (30.0) | `trail_back_to_back` | tempo | peak | E | — |
| Trail (30.0) | `trail_downhill_technique` | interval | build | E | — |
| Trail (30.0) | `trail_flat_surge_fartlek` | tempo | build, peak | T | — |
| Trail (30.0) | `trail_flat_soft_surface` | tempo | build, peak | E | — |
| Trail (30.0) | `trail_flat_power_walk` | tempo | peak | E | — |
| Trail (30.0) | `trail_flat_proprioception` | interval | build | E | — |
| Trail (30.0) | `trail_long_fast_finish` | long | build, peak | T | `fast_finish` |
| Trail (30.0) | `trail_long_rolling_hills` | long | build | E | `rolling_hills` |
| Trail (30.0) | `trail_long_race_simulation` | long | peak | E | `rolling_hills` |
| Trail (30.0) | `trail_flat_long_fast_finish` | long | build, peak | T | `fast_finish` |
| Trail (30.0) | `trail_flat_long_fueling` | long | build | E | `depletion` |
| Trail (30.0) | `trail_flat_long_race_sim` | long | peak | E | `rolling_hills` |

### 1.3 Selection Logic (`key_workout_library.py`)

- `KeyWorkoutLibrary.get_for_phase()` filters by: `target_distance` ∈ `distances`, `phase` ∈ `phases`, `workout_type` == `type`, terrain match
- Rotation: `candidates[week_in_phase % len(candidates)]`
- Terrain filtering: `terrain == "flat"` → only `"flat"` terrain workouts; otherwise `"any"` or `"hilly"`

---

## 2. Distance Assignment Flow

### 2.1 Standard Plan (`TrainingPlanGenerator`)

```
total_km (from mileage_progression)
    │
    ├──► long_run_calculator.calculate_long_run_distance()
    │     total_km × long_run_ratio (from phase/distance tables)
    │     → capped by experience tier + hard ceiling
    │     → profile-aware week-1 gentle nudge
    │
    ├──► long_run_calculator.calculate_quality_distances()
    │     remaining_km = total_km - long_run_distance
    │     quality_dist = remaining_km × (phase_pct / non_long_pct)
    │
    ├──► apply_quality_caps()
    │     cap = min(long_run × 0.85, phys_cap[target_distance][type])
    │
    └──► allocate_easy_distances()
          easy_budget = remaining_km - quality_total
          per_run = easy_budget / easy_runs
          capped at long_run × 0.95
```

### 2.2 Performance Plan (`PerformancePlanGenerator`)

```
weekly_km (from mileage_progression)
    │
    ├──► generate_long_run()
    │     long_run_km = weekly_km × 0.30
    │     capped by distance (15/22/32 km)
    │
    ├──► generate_tempo/vo2max/race_pace/fartlek_workout()
    │     distance = weekly_km × phase_percentage
    │     with per-workout max caps
    │
    ├──► enforce_week_caps()
    │     caps quality vs long run (0.85×) + physiological caps
    │
    └──► reconcile_workout_after_cap()
          syncs segments to match capped distance
          regenerates description from segments
```

---

## 3. Segment/Step Description Generation

### 3.1 Three Parallel Systems

| System | Output Format | Generated By | Used By |
|--------|--------------|-------------|---------|
| **Steps** | `[{kind, label, distance_m, duration_s, repeat, pace_zone, pace_str, effort, note}]` | `workout_steps.build_*_steps()` | Standard plan |
| **Segments** | `[{name, distance_km, pace_formatted, pace_raw, zone, zone_label, type, intervals?}]` | `performance_workout_builders.py` | Performance plan |
| **Parsed Steps** | Same as Steps | `key_workout_parser.parse_key_workout_steps()` | Key workout fallback |

### 3.2 Standard Plan Flow

```
build_workout_for_type()
  → generate_tempo/interval/hill/easy/long_run()
    → returns {description, steps, distance, type, ...}
    → steps from workout_steps.build_*_steps()

overlay_key_workout()  [key_workout_library.py:206-266]
  → KeyWorkoutLibrary.get_for_phase() selects key workout
  → Rewrites description via _DISTANCE_REWRITES (if available)
  → Sets: key_workout_id, key_workout_name, structure, key_workout_rationale
  → Generates steps from:
      1. key_wk['steps'] (pre-built)
      2. steps_builder → _resolve_long_steps_builder()
      3. parse_key_workout_steps(structure) — fallback parser
  → workout.pop('segments', None)  ← REMOVES segments
```

### 3.3 Performance Plan Flow

```
generate_tempo/vo2max/race_pace/fartlek_workout()
  → returns {description, segments, distance, type, quality, ...}
  → segments: warmup + main + cooldown with pace zones

_overlay_key_workout()  [performance_plan_generator.py:200-213]
  → Maps: vo2max→interval, tempo→tempo, race_pace→tempo
  → Calls overlay_key_workout_shared()
  → Sets key_workout fields on workout dict

_regenerate_description()  [performance_workout_builders.py:54-106]
  → Rebuilds description FROM SEGMENTS
  → Overwrites the key workout description just set!
```

---

## 4. Complete Data Flow: Source → UI

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. USER SUBMITS FORM                                             │
│    Router: plan_generation.py POST /generate-plan                │
│    → Validates PlanRequest (Pydantic)                            │
│    → Calls TrainingPlanGenerator.generate_plan()                 │
│    → Saves TrainingPlan to DB                                    │
│    → Redirects to GET /plan/{plan_id}                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. PLAN GENERATION (per week)                                    │
│                                                                  │
│    build_weekly_plan() [weekly_plan_builder.py:221-266]          │
│    ├── calculate_phases()                                        │
│    ├── get_workout_distribution() → {easy:2, tempo:1, long:1}   │
│    ├── schedule_workout_types() → [None,recovery,easy,interval,  │
│    │                                easy,long,rest]              │
│    └── generate_daily_workouts() [lines 80-159]                  │
│        ├── calculate_long_run_distance()                         │
│        ├── calculate_quality_distances()                         │
│        ├── apply_quality_caps()                                  │
│        ├── allocate_easy_distances()                             │
│        └── For each day:                                         │
│            ├── build_workout_for_type() → workout dict           │
│            │   (description + steps from workout_builders.py)    │
│            └── overlay_key_workout() [key_workout_library.py]    │
│                → Replaces description with key workout text      │
│                → Generates steps from library or parser          │
│                → Removes segments                                │
│                → Sets key_workout_name, structure, rationale     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. PLAN VIEW ENRICHMENT                                          │
│    Router: plan_view.py GET /plan/{plan_id}                      │
│    ├── enrich_plan_data_with_ids()                               │
│    ├── compute nutrition, HR zones                               │
│    ├── For performance plans: recalculates training zones        │
│    └── Renders plan.html with context                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. TEMPLATE RENDERING                                            │
│                                                                  │
│    plan.html                                                     │
│    └── week_card.html [for each week]                            │
│        └── workout_item.html [for each workout]                  │
│            │                                                     │
│            ├── Line 21: {% if workout.key_workout_name %}        │
│            │     → Key workout badge                             │
│            │                                                     │
│            ├── Line 26: {% if workout.structure %}               │
│            │     → Structure subtitle (one-liner)                │
│            │                                                     │
│            ├── Line 29: {{ workout.notes }}                      │
│            │     → Description (notes field)                     │
│            │                                                     │
│            ├── Line 31-39: {% if workout.steps %}                │
│            │     → Collapsible "Session blocks"                  │
│            │     → Includes workout_steps.html                   │
│            │     → Shows: label, distance_m, pace_str, effort    │
│            │                                                     │
│            ├── Line 40-67: {% elif workout.segments %}           │
│            │     → Collapsible "Session blocks" (alt format)     │
│            │     → Shows: name, distance_km, pace_formatted      │
│            │     → Shows: intervals (reps × distance_m + rec)    │
│            │                                                     │
│            ├── Line 69-73: {% if workout.key_workout_rationale %}│
│            │     → "Why this workout" collapsible                │
│            │                                                     │
│            └── Line 76-88: {% if workout.coaching_rationale %}   │
│                  → "Coach says" collapsible                      │
│                                                                  │
│    performance_plan.html                                         │
│    └── For each workout:                                         │
│        ├── type badge, distance, description                     │
│        ├── zone indicator + pace                                 │
│        └── Collapsible segments (same format as segments above)  │
│        ⚠️ NO key_workout_name badge rendering                    │
│        ⚠️ NO structure subtitle rendering                        │
│        ⚠️ NO key_workout_rationale rendering                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Gaps & Inconsistencies

### GAP 1: `segments` vs `steps` dual representation
- **Location:** `key_workout_library.py:265` vs `performance_workout_builders.py`
- **Issue:** Standard plan does `workout.pop('segments', None)` after overlay, replacing with `steps`. Performance plan uses `segments` throughout.
- **UI impact:** `workout_item.html` handles both with `{% if workout.steps %}` then `{% elif workout.segments %}`, but the data structures differ (meters vs km, `pace_zone` vs `zone_label`, `effort` vs no effort cue).
- **Risk:** If overlay fails (no key workout found), `segments` from the builder remain and render with a different schema.

### GAP 2: Performance plan `_regenerate_description()` overwrites key workout descriptions
- **Location:** `performance_plan_generator.py:328-331`
```python
self._overlay_key_workout(workout, phase, target_distance, week_in_phase, vdot_zones)
_regenerate_description(workout)  # ← Overwrites the description just set!
```
- **Issue:** `_overlay_key_workout()` sets a rich key workout description with VDOT paces, rationale, and coaching context. `_regenerate_description()` immediately replaces it with a generic segment-based string like `"8km tempo: 2km warmup, 4.0km at 4:30/km, 2km cooldown"`.
- **Impact:** Users see generic descriptions instead of curated key workout instructions.

### GAP 3: Performance plan UI missing key workout metadata
- **Location:** `performance_plan.html`
- **Issue:** The template does NOT render:
  - `workout.key_workout_name` badge
  - `workout.structure` subtitle
  - `workout.key_workout_rationale` collapsible
- **Impact:** Even if key workout metadata is set on the workout dict, the performance plan template doesn't display it.

### GAP 4: `pace_zone` "10K" is not a standard VDOT zone
- **Location:** `key_workout_data.py:188` (`10k_goal_pace_segments`), `key_workout_data.py:229` (`10k_fartlek`)
- **Issue:** VDOT zones are E, M, T, I, R. "10K" is not in `VDOTCalculator.get_pace_zones()`. `_pace_str()` in `workout_steps.py:35-38` returns `None` for unrecognized zones.
- **Impact:** Steps for these workouts will have `pace_str: null` — no pace shown in UI.

### GAP 5: Incomplete `_DISTANCE_REWRITES` coverage
- **Location:** `key_workout_library.py:23-135`
- **Issue:** Only 22 of 34 key workout IDs have distance rewrite lambdas. Missing:
  - `5k_hill_sprints`
  - `10k_fartlek`
  - `marathon_yasso_800s`
  - `marathon_progressive_long`
  - `trail_elevation_repeats`
  - `trail_time_on_feet`
  - `trail_technical_terrain`
  - `trail_power_hike`
  - `trail_back_to_back`
  - `trail_downhill_technique`
  - `trail_flat_surge_fartlek` (partially)
  - `trail_flat_soft_surface` (partially)
  - `trail_flat_power_walk`
  - `trail_flat_proprioception`
- **Impact:** When these workouts are selected, descriptions show hardcoded distances (e.g., "Warm up 2km easy") that don't match the actual assigned workout distance.

### GAP 6: Long-run key workout overlay conflicts with builder steps
- **Location:** `key_workout_library.py:220` includes `'long'` in valid types
- **Issue:** `generate_long_run()` in `workout_builders.py` already generates steps via `build_long_steps(distance, pace_zones, variant)`. The key workout overlay replaces these with steps from `steps_builder` or the parser, which may calculate distances differently.
- **Risk:** Long run steps could show different distances than the workout's `distance` field.

### GAP 7: `week_in_phase` rotation skips workouts in short plans
- **Location:** `key_workout_library.py:318`
- **Issue:** `candidates[week_in_phase % len(candidates)]` — if a phase has 3 weeks but 5 candidates, 2 workouts never appear. If 6 weeks and 2 candidates, each repeats 3 times.
- **Impact:** Some curated workouts may never be prescribed in shorter plans.

### GAP 8: Performance plan quality count differs from standard plan
- **Location:** `performance_plan_generator.py:228-231` vs `workout_distribution.py:15-95`
- **Issue:** Performance plan uses simple `int(runs_per_week * quality_percent / 100)`. Standard plan uses profile-aware logic with terrain, base mileage, workout history, and polarized ratio validation.
- **Impact:** Same user gets different quality session counts depending on generator.

### GAP 9: `reconcile_workout_after_cap()` doesn't handle all types
- **Location:** `performance_workout_builders.py:54-106`
- **Issue:** Only handles `'tempo'`, `'vo2max'`, `'race_pace'`, `'fartlek'`. If key workout overlay changes a workout's type to `'interval'` or `'hill'`, reconciliation silently skips it.
- **Risk:** Segments and description become out of sync with capped distance.

### GAP 10: `structure` field not set in performance plan
- **Location:** `performance_plan_generator.py`
- **Issue:** `_overlay_key_workout()` sets `structure` via the shared library, but `_regenerate_description()` doesn't touch it. However, `performance_plan.html` doesn't render `structure` at all.
- **Impact:** Inconsistent UI — standard plan shows structure subtitle, performance plan doesn't.

---

## 6. Proposed Fixes (Prioritized)

### P0 — Critical (data inconsistency)

**Fix 1: Stop `_regenerate_description()` from overwriting key workout descriptions**
- File: `app/core/generators/performance_plan_generator.py`
- Change: Call `_regenerate_description()` BEFORE `_overlay_key_workout()`, or better: have `_regenerate_description()` preserve key workout descriptions by checking for `key_workout_id` first.
- Alternative: Remove `_regenerate_description()` call entirely since `overlay_key_workout()` already sets a proper description.

**Fix 2: Add "10K" as a VDOT zone or alias**
- File: `app/core/training/vdot_calculator.py`
- Change: In `get_pace_zones()`, add a `"10K"` key computed as the geometric mean of T and I pace, or map it to T pace for 10K-focused runners.
- Also update `_pace_str()` in `workout_steps.py` to handle "10K" → resolve to the correct zone.

**Fix 3: Complete `_DISTANCE_REWRITES` for all workout IDs**
- File: `app/core/training/key_workout_library.py`
- Change: Add rewrite lambdas for all 12 missing workout IDs, using proportional distance calculations similar to existing patterns.

### P1 — Important (UI/UX consistency)

**Fix 4: Add key workout rendering to performance_plan.html**
- File: `app/templates/performance_plan.html`
- Change: Add rendering for `workout.key_workout_name`, `workout.structure`, and `workout.key_workout_rationale` matching the pattern in `workout_item.html`.

**Fix 5: Unify steps/segments representation**
- File: `app/core/generators/performance_workout_builders.py`
- Change: Convert `segments` to `steps` format at generation time, or add a conversion layer. This eliminates the dual-representation bug and simplifies templates.

**Fix 6: Ensure `structure` is always set**
- File: `app/core/generators/performance_workout_builders.py`
- Change: Have `_regenerate_description()` also set `workout['structure']` from segment data, or ensure `_overlay_key_workout()` sets it after description regeneration.

### P2 — Nice to have (robustness)

**Fix 7: Handle `'interval'` and `'hill'` types in `reconcile_workout_after_cap()`**
- File: `app/core/generators/performance_workout_builders.py`
- Change: Add cases for `'interval'` and `'hill'` types in `_regenerate_description()`.

**Fix 8: Improve workout rotation for short phases**
- File: `app/core/training/key_workout_library.py`
- Change: Instead of simple modulo rotation, use a hash of `(week_in_phase, target_distance)` to spread workouts more evenly, or prioritize by phase relevance.

**Fix 9: Add post-generation validation**
- New file or existing: `app/core/generators/plan_validator.py`
- Change: Validate that `workout['distance']` ≈ sum of step/segment distances, and that description distances match actual values. Log warnings on mismatch.

---

## 7. Implementation Order

1. **Fix 1** — Stop description overwrite in performance plan (1 file, ~5 lines)
2. **Fix 2** — Add "10K" zone support (2 files, ~15 lines)
3. **Fix 3** — Complete distance rewrites (1 file, ~40 lines)
4. **Fix 4** — Add key workout UI to performance template (1 file, ~20 lines)
5. **Fix 5** — Unify steps/segments (2-3 files, larger refactor)
6. **Fix 6** — Ensure structure always set (1-2 files, ~10 lines)
7. **Fix 7-9** — Robustness improvements (3 files, ~50 lines)
