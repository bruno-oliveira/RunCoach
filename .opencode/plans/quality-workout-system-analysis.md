# Quality Workout System: Complete Analysis & Improvement Plan

> **Date:** 2026-05-03
> **Updated:** 2026-05-04 (Investigation round 2 — parser/distance mismatch bugs)
> **Scope:** `app/core/training/key_workout_*.py`, `app/core/training/workout_*.py`, `app/core/generators/weekly_plan_builder.py`, `app/core/generators/performance_plan_generator.py`, `app/core/generators/performance_workout_builders.py`, templates

---

## 1. Quality Workout Types Inventory

### 1.1 Short-Distance Workouts (`key_workout_data.py`)

| Distance | ID | Type | Phases | Pace Zone | Has Rewrite? | Parser Match? |
|----------|-----|------|--------|-----------|-------------|---------------|
| 5K | `5k_vo2max_400s` | interval | build, peak | I | ✅ | ✅ distance reps |
| 5K | `5k_race_pace_3km` | tempo | build, peak | I | ✅ | ✅ distance reps |
| 5K | `5k_cruise_intervals` | tempo | build | T | ✅ | ✅ distance reps |
| 5K | `5k_threshold_run` | tempo | build | T | ✅ | ✅ continuous |
| 5K | `5k_hill_sprints` | hill | build | R | ❌ | ❌ fallback |
| 5K | `5k_pyramid` | interval | peak | I | ✅ | ❌ fallback |
| 10K | `10k_cruise_intervals` | tempo | build, peak | T | ✅ | ✅ distance reps |
| 10K | `10k_goal_pace_segments` | tempo | build, peak | **10K** ⚠️ | ✅ | ✅ distance reps |
| 10K | `10k_tempo_progression` | tempo | peak | T | ✅ | ✅ as-progression |
| 10K | `10k_fartlek` | interval | build | **10K** ⚠️ | ✅ | ✅ fartlek |
| Half (21.1) | `half_progressive_long` | tempo | build, peak | M | ✅ | ❌ **BROKEN** |
| Half (21.1) | `half_threshold_cruise` | tempo | build, peak | T | ✅ | ✅ distance reps |
| Half (21.1) | `half_race_pace_segments` | tempo | peak | M | ✅ | ✅ distance reps |
| Half (21.1) | `half_cutdown_long` | interval | build | M | ✅ | ❌ **BROKEN** |

### 1.2 Long-Distance Workouts (`key_workout_data_long.py`)

| Distance | ID | Type | Phases | Pace Zone | Steps Builder | Has Rewrite? | Parser Match? |
|----------|-----|------|--------|-----------|---------------|-------------|---------------|
| Half (21.1) | `half_long_alternating_mp` | long | build, peak | M | `alternating_mp` | — | — |
| Half (21.1) | `half_long_fast_finish` | long | build, peak | T | `fast_finish` | — | — |
| Half (21.1) | `half_long_rolling_hills` | long | build | E | `rolling_hills` | — | — |
| Marathon (42.2) | `marathon_long_alternating_mp` | long | build, peak | M | `alternating_mp_3k` | — | — |
| Marathon (42.2) | `marathon_long_fast_finish` | long | build, peak | T | `fast_finish_4k` | — | — |
| Marathon (42.2) | `marathon_long_depletion` | long | build | E | `depletion` | — | — |
| Marathon (42.2) | `marathon_long_rolling_hills` | long | build | E | `rolling_hills` | — | — |
| Marathon (42.2) | `marathon_mp_long` | tempo | build, peak | M | — | ✅ | ✅ progression |
| Marathon (42.2) | `marathon_yasso_800s` | interval | build, peak | I | — | ❌ | ❌ fallback |
| Marathon (42.2) | `marathon_progressive_long` | tempo | build | M | — | ✅ | ⚠️ **hardcoded** |
| Marathon (42.2) | `marathon_tempo_cutdown` | tempo | peak | T | — | ✅ | ⚠️ **hardcoded** |
| Marathon (42.2) | `marathon_mp_cutdown` | interval | peak | T | — | ✅ | ⚠️ **hardcoded** |
| Marathon (42.2) | `marathon_easy_long_fueling` | tempo | build | E | — | ✅ | ❌ fallback |
| Marathon (42.2) | `marathon_peak_progressive` | tempo | peak | M | — | ✅ | ⚠️ **hardcoded** |
| 10K | `10k_long_fast_finish` | long | build, peak | T | `fast_finish_2k` | — | — |
| Trail (30.0) | `trail_elevation_repeats` | hill | build, peak | T | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_time_on_feet` | tempo | build, peak | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_technical_terrain` | interval | build | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_power_hike` | hill | peak | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_back_to_back` | tempo | peak | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_downhill_technique` | interval | build | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_flat_surge_fartlek` | tempo | build, peak | T | — | ✅ | ❌ fallback |
| Trail (30.0) | `trail_flat_soft_surface` | tempo | build, peak | E | — | ✅ | ❌ fallback |
| Trail (30.0) | `trail_flat_power_walk` | tempo | peak | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_flat_proprioception` | interval | build | E | — | ❌ | ❌ fallback |
| Trail (30.0) | `trail_long_fast_finish` | long | build, peak | T | `fast_finish` | — | — |
| Trail (30.0) | `trail_long_rolling_hills` | long | build | E | `rolling_hills` | — | — |
| Trail (30.0) | `trail_long_race_simulation` | long | peak | E | `rolling_hills` | — | — |
| Trail (30.0) | `trail_flat_long_fast_finish` | long | build, peak | T | `fast_finish` | — | — |
| Trail (30.0) | `trail_flat_long_fueling` | long | build | E | `depletion` | — | — |
| Trail (30.0) | `trail_flat_long_race_sim` | long | peak | E | `rolling_hills` | — | — |

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

overlay_key_workout()  [key_workout_library.py:242-301]
  → KeyWorkoutLibrary.get_for_phase() selects key workout
  → Rewrites description via _DISTANCE_REWRITES (if available)
  → Sets: key_workout_id, key_workout_name, key_workout_rationale
  → Sets structure:
      IF rewritten: _derive_structure(rewritten_description)
      ELSE: key_wk['structure'] (original hardcoded string)
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

### 🔴 CRITICAL BUG A: `_DISTANCE_REWRITES` + `_derive_structure()` destroys parser compatibility

**Location:** `key_workout_library.py:283-284` + `key_workout_parser.py`

**Root cause chain:**
1. When a workout ID is in `_DISTANCE_REWRITES`, the description is rewritten with scaled distances:
   ```python
   # half_progressive_long rewrite:
   "Run 18km total. Start at easy pace for 11.7km, then increase to marathon pace for the final 6.3km. No warm-up needed..."
   ```
2. `_derive_structure()` strips "Warm up..." and "Cool down..." and leading "Run ":
   ```python
   # Result:
   "18km total. Start at easy pace for 11.7km, then increase to marathon pace for the final 6.3km. No warm-up needed..."
   ```
3. This derived structure is passed to `parse_key_workout_steps()`
4. **None of the parser patterns match this format:**
   - `_try_progression_pattern` expects `"Nkm: first Xkm easy, last Ykm at ... pace"` — NO COLON, NO "first"
   - `_try_as_progression_pattern` expects `"Nkm as a progression"` — NO MATCH
   - `_try_distance_reps_pattern` expects `"N x Dkm at ..."` — NO MATCH
   - `_try_duration_reps_pattern` expects `"N x Dsec/min"` — NO MATCH
   - `_try_fartlek_pattern` expects `"N x (Dmin hard / Dmin easy)"` — NO MATCH
   - `_try_continuous_pattern` expects `"Xkm continuous at X pace"` — NO MATCH
5. **Fallback:** Single step with `structure[:60]` as label:
   ```python
   _step("run", "18km total. Start at easy pace for 11.7km, then increa", pace_zone="M", ...)
   ```

**Affected workouts (have rewrite but derived structure doesn't parse):**
- `half_progressive_long` — falls back to single block (should be easy + MP finish)
- `half_cutdown_long` — falls back to single block (should be 3 segments)
- `marathon_easy_long_fueling` — falls back to single block
- `trail_flat_surge_fartlek` — falls back to single block
- `trail_flat_soft_surface` — falls back to single block

**Impact:** Steps show a single undifferentiated block instead of the intended workout structure. The description says one thing (scaled distances with segments) but the steps show something completely different (one blob).

### 🔴 CRITICAL BUG B: Parser extracts HARDCODED distances from structure strings

**Location:** `key_workout_parser.py:51-69` (`_try_progression_pattern`), `key_workout_parser.py:96-124` (`_try_distance_reps_pattern`)

**Issue:** When the parser DOES match a pattern, it extracts distances directly from the structure string via regex. These are the hardcoded values from the workout definition, NOT the actual assigned distance.

**Concrete examples:**

| Workout | Structure (hardcoded) | Actual assigned | Parser extracts | Steps show | Mismatch |
|---------|----------------------|-----------------|-----------------|------------|----------|
| `marathon_progressive_long` | "28-30km: first 20km easy, last 8-10km..." | 25km | easy=20km, finish=10km | 30km total | +5km |
| `marathon_peak_progressive` | "28km: first 16km easy, last 12km..." | 25km | easy=16km, finish=12km | 28km total | +3km |
| `marathon_tempo_cutdown` | "2 x 5km at threshold pace..." | 12km | 2×5km=10km | 10km main + WU/CD | exceeds 12km |
| `marathon_mp_cutdown` | "5 x 2km: alternate MP and T-pace..." | 10km | 5×2km=10km | 10km + WU/CD | exceeds 10km |
| `marathon_mp_long` | "25km: first 15km easy, last 10km..." | 20km | easy=15km, finish=10km | 25km total | +5km |

**Impact:** Steps show distances that don't match the workout's `distance` field. For cutdown workouts, the steps can exceed the total workout distance (warmup + main + cooldown > assigned distance).

### 🔴 CRITICAL BUG C: Performance plan `_regenerate_description()` overwrites key workout descriptions

**Location:** `performance_plan_generator.py:328-331`

```python
self._overlay_key_workout(workout, phase, target_distance, week_in_phase, vdot_zones)
_regenerate_description(workout)  # ← Overwrites the description just set!
```

**Issue:** `_overlay_key_workout()` sets a rich key workout description with VDOT paces, rationale, and coaching context. `_regenerate_description()` immediately replaces it with a generic segment-based string like `"8km tempo: 2km warmup, 4.0km at 4:30/km, 2km cooldown"`.

**Impact:** Users see generic descriptions instead of curated key workout instructions. Key workout names, rationales, and structures are set but the main description is generic.

### 🟡 GAP 1: `segments` vs `steps` dual representation

- **Location:** `key_workout_library.py:301` vs `performance_workout_builders.py`
- **Issue:** Standard plan does `workout.pop('segments', None)` after overlay, replacing with `steps`. Performance plan uses `segments` throughout.
- **UI impact:** `workout_item.html` handles both with `{% if workout.steps %}` then `{% elif workout.segments %}`, but the data structures differ (meters vs km, `pace_zone` vs `zone_label`, `effort` vs no effort cue).
- **Risk:** If overlay fails (no key workout found), `segments` from the builder remain and render with a different schema.

### 🟡 GAP 2: Performance plan UI missing key workout metadata

- **Location:** `performance_plan.html`
- **Issue:** The template does NOT render:
  - `workout.key_workout_name` badge
  - `workout.structure` subtitle
  - `workout.key_workout_rationale` collapsible
- **Impact:** Even if key workout metadata is set on the workout dict, the performance plan template doesn't display it.

### 🟡 GAP 3: `pace_zone` "10K" is not a standard VDOT zone

- **Location:** `key_workout_data.py:188` (`10k_goal_pace_segments`), `key_workout_data.py:229` (`10k_fartlek`)
- **Issue:** VDOT zones are E, M, T, I, R. "10K" is not in `VDOTCalculator.get_pace_zones()`. `_pace_str()` in `workout_steps.py:35-38` returns `None` for unrecognized zones.
- **Impact:** Steps for these workouts will have `pace_str: null` — no pace shown in UI.

### 🟡 GAP 4: Incomplete `_DISTANCE_REWRITES` coverage

- **Location:** `key_workout_library.py:23-135`
- **Issue:** 14 of 34 key workout IDs have NO distance rewrite lambda:
  - `5k_hill_sprints`, `marathon_yasso_800s`, `trail_elevation_repeats`, `trail_time_on_feet`, `trail_technical_terrain`, `trail_power_hike`, `trail_back_to_back`, `trail_downhill_technique`, `trail_flat_power_walk`, `trail_flat_proprioception`, and others
- **Impact:** When these workouts are selected, descriptions show hardcoded distances (e.g., "Warm up 2km easy") that don't match the actual assigned workout distance.

### 🟡 GAP 5: `marathon_mp_cutdown` description rewrite keeps hardcoded "5 x 2km"

- **Location:** `key_workout_library.py:69-73`
- **Issue:**
  ```python
  "marathon_mp_cutdown": lambda d: (
      f"Warm up {round(max(1, d * 0.10)):g}km easy. "
      f"Run 5 x 2km alternating between marathon pace and threshold pace, "
      f"with 90s jog recovery between each. Cool down {round(max(1, d * 0.10)):g}km easy."
  ),
  ```
  The "5 x 2km" is hardcoded. For d=10km: warmup=1km + 5×2km=10km + cooldown=1km = 12km total, exceeding the assigned 10km.
- **Impact:** Description distances don't add up to the workout distance.

### 🟡 GAP 6: `half_progressive_long` type is "tempo" but has no warmup/cooldown

- **Location:** `key_workout_data.py:238-257`
- **Issue:** The description says "No warm-up needed — the easy start IS the warm-up." But the workout type is "tempo", which triggers warmup/cooldown addition in the parser (`has_wcd = workout_type in ("interval", "tempo", "hill")`).
- **Impact:** Parser adds warmup/cooldown steps that contradict the description.

### 🟡 GAP 7: Long-run key workout overlay conflicts with builder steps

- **Location:** `key_workout_library.py:256` includes `'long'` in valid types
- **Issue:** `generate_long_run()` in `workout_builders.py` already generates steps via `build_long_steps(distance, pace_zones, variant)`. The key workout overlay replaces these with steps from `steps_builder` or the parser, which may calculate distances differently.
- **Risk:** Long run steps could show different distances than the workout's `distance` field.

### 🟡 GAP 8: `week_in_phase` rotation skips workouts in short plans

- **Location:** `key_workout_library.py:354`
- **Issue:** `candidates[week_in_phase % len(candidates)]` — if a phase has 3 weeks but 5 candidates, 2 workouts never appear.
- **Impact:** Some curated workouts may never be prescribed in shorter plans.

### 🟡 GAP 9: Performance plan quality count differs from standard plan

- **Location:** `performance_plan_generator.py:228-231` vs `workout_distribution.py:15-95`
- **Issue:** Performance plan uses simple `int(runs_per_week * quality_percent / 100)`. Standard plan uses profile-aware logic with terrain, base mileage, workout history, and polarized ratio validation.
- **Impact:** Same user gets different quality session counts depending on generator.

### 🟡 GAP 10: `reconcile_workout_after_cap()` doesn't handle all types

- **Location:** `performance_workout_builders.py:54-106`
- **Issue:** Only handles `'tempo'`, `'vo2max'`, `'race_pace'`, `'fartlek'`. If key workout overlay changes a workout's type to `'interval'` or `'hill'`, reconciliation silently skips it.
- **Risk:** Segments and description become out of sync with capped distance.

---

## 6. Proposed Fixes (Prioritized)

### P0 — Critical (data inconsistency — steps don't match distances)

**Fix A1: Rewrite `_try_progression_pattern` to use `total_distance_km`**
- File: `app/core/training/key_workout_parser.py`
- Change: Instead of extracting distances from the structure string, use `total_distance_km` parameter to compute proportional splits. For "first Xkm easy, last Ykm at pace" patterns, compute ratios from the structure (X/(X+Y), Y/(X+Y)) and apply to `total_distance_km`.
- Affected workouts: `marathon_progressive_long`, `marathon_peak_progressive`, `marathon_mp_long`, `half_progressive_long` (if it matched)

**Fix A2: Rewrite `_try_distance_reps_pattern` to scale reps/distance**
- File: `app/core/training/key_workout_parser.py`
- Change: Extract the rep count and per-rep distance from structure, but scale to fit within `total_distance_km - warmup - cooldown`. Either adjust the number of reps or the per-rep distance proportionally.
- Affected workouts: `marathon_tempo_cutdown`, `marathon_mp_cutdown`, `marathon_yasso_800s`

**Fix A3: Fix `_DISTANCE_REWRITES` to produce parseable structures**
- File: `app/core/training/key_workout_library.py`
- Change: The rewrite lambdas should produce descriptions that, when processed by `_derive_structure()`, yield structure strings that match parser patterns. Alternatively, bypass `_derive_structure()` for rewritten workouts and construct a parseable structure directly.
- Affected workouts: `half_progressive_long`, `half_cutdown_long`, `marathon_easy_long_fueling`, `trail_flat_surge_fartlek`, `trail_flat_soft_surface`

**Fix A4: Stop `_regenerate_description()` from overwriting key workout descriptions**
- File: `app/core/generators/performance_plan_generator.py`
- Change: Call `_regenerate_description()` BEFORE `_overlay_key_workout()`, or have `_regenerate_description()` check for `key_workout_id` and skip if present.
- Alternative: Remove `_regenerate_description()` call entirely since `overlay_key_workout()` already sets a proper description.

### P1 — Important (UI/UX consistency)

**Fix B1: Add "10K" as a VDOT zone or alias**
- File: `app/core/training/vdot_calculator.py`
- Change: In `get_pace_zones()`, add a `"10K"` key computed as the geometric mean of T and I pace, or map it to T pace for 10K-focused runners.
- Also update `_pace_str()` in `workout_steps.py` to handle "10K" → resolve to the correct zone.

**Fix B2: Add key workout rendering to performance_plan.html**
- File: `app/templates/performance_plan.html`
- Change: Add rendering for `workout.key_workout_name`, `workout.structure`, and `workout.key_workout_rationale` matching the pattern in `workout_item.html`.

**Fix B3: Complete `_DISTANCE_REWRITES` for all workout IDs**
- File: `app/core/training/key_workout_library.py`
- Change: Add rewrite lambdas for all 14 missing workout IDs, using proportional distance calculations similar to existing patterns.

**Fix B4: Unify steps/segments representation**
- File: `app/core/generators/performance_workout_builders.py`
- Change: Convert `segments` to `steps` format at generation time, or add a conversion layer. This eliminates the dual-representation bug and simplifies templates.

**Fix B5: Fix `marathon_mp_cutdown` rewrite to scale rep count**
- File: `app/core/training/key_workout_library.py`
- Change: Instead of hardcoded "5 x 2km", compute the number of reps or rep distance from the actual distance: `f"Run {num_reps} x {rep_km}km alternating..."`

### P2 — Nice to have (robustness)

**Fix C1: Handle `'interval'` and `'hill'` types in `reconcile_workout_after_cap()`**
- File: `app/core/generators/performance_workout_builders.py`
- Change: Add cases for `'interval'` and `'hill'` types in `_regenerate_description()`.

**Fix C2: Improve workout rotation for short phases**
- File: `app/core/training/key_workout_library.py`
- Change: Instead of simple modulo rotation, use a hash of `(week_in_phase, target_distance)` to spread workouts more evenly, or prioritize by phase relevance.

**Fix C3: Add post-generation validation**
- New file or existing: `app/core/generators/plan_validator.py`
- Change: Validate that `workout['distance']` ≈ sum of step/segment distances, and that description distances match actual values. Log warnings on mismatch.

---

## 7. Implementation Order

### Phase 1: Fix the parser (P0 — A1, A2, A3)
1. **Fix A1** — Make `_try_progression_pattern` use `total_distance_km` (parser.py, ~20 lines)
2. **Fix A2** — Make `_try_distance_reps_pattern` scale to fit `total_distance_km` (parser.py, ~20 lines)
3. **Fix A3** — Fix `_DISTANCE_REWRITES` to produce parseable structures (library.py, ~30 lines)

### Phase 2: Fix performance plan description overwrite (P0 — A4)
4. **Fix A4** — Stop `_regenerate_description()` from overwriting key workout descriptions (perf_plan_gen.py, ~5 lines)

### Phase 3: Fix zone and rewrite gaps (P1 — B1, B3, B5)
5. **Fix B1** — Add "10K" zone support (vdot_calculator.py + workout_steps.py, ~15 lines)
6. **Fix B3** — Complete distance rewrites for missing IDs (library.py, ~40 lines)
7. **Fix B5** — Fix `marathon_mp_cutdown` rewrite to scale reps (library.py, ~5 lines)

### Phase 4: UI consistency (P1 — B2, B4)
8. **Fix B2** — Add key workout UI to performance template (performance_plan.html, ~20 lines)
9. **Fix B4** — Unify steps/segments (perf_workout_builders.py, larger refactor)

### Phase 5: Robustness (P2 — C1, C2, C3)
10. **Fix C1** — Handle all types in `reconcile_workout_after_cap()` (~10 lines)
11. **Fix C2** — Improve workout rotation (~10 lines)
12. **Fix C3** — Add post-generation validation (~30 lines)
