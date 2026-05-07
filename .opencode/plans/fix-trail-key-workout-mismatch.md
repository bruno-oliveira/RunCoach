# Fix Trail Key Workout Description/Distance Mismatch

## Problem

Trail key workout descriptions and displayed distances are mismatching. The root cause is a multi-pass distance computation flow where the description is written early with an initial distance value, but the final displayed distance is computed later from the generated steps, and the description is never updated to reflect this final value.

## Root Cause Analysis

The `overlay_key_workout()` function in `key_workout_library.py:542-619` follows this flow:

1. **Initial distance** is taken from `workout.get('distance', 0)` and potentially bumped by `_KEY_WORKOUT_MIN_DISTANCE_KM` floor values
2. **Description is written** using this initial distance via `_DISTANCE_REWRITES` lambdas
3. **Structure is set** from `_STRUCTURE_REWRITES` or derived from the description
4. **Steps are computed** either from `steps_builder`, pre-defined `steps`, or parsed from the structure string
5. **Final distance is recomputed** from the steps via `_compute_distance_from_steps()` and overwrites `workout['distance']`
6. **Description and structure are NEVER updated** after step 5

Additionally, there's a secondary drift source: the `_wu_cd()` helper in `key_workout_library.py` and `_wucd_m()` in `workout_steps.py` implement the same warmup/cooldown calculation differently (one rounds to 1 decimal km, the other to integer meters), causing ~100m drift in warmup/cooldown allocation.

## Affected Workouts

All 16 trail workouts with `_DISTANCE_REWRITES` entries:

| Workout ID | Type | Drift Sources |
|------------|------|---------------|
| `trail_elevation_repeats` | hill | description, structure, wu_cd mismatch, parser |
| `trail_technical_terrain` | interval | description, structure, wu_cd mismatch, parser |
| `trail_power_hike` | hill | description, structure, wu_cd mismatch, parser |
| `trail_downhill_technique` | interval | description, structure, wu_cd mismatch, parser |
| `trail_flat_surge_fartlek` | tempo | description, structure, wu_cd mismatch, parser |
| `trail_flat_soft_surface` | tempo | description, structure, wu_cd mismatch |
| `trail_time_on_feet` | tempo | description, structure, wu_cd mismatch |
| `trail_back_to_back` | tempo | description, structure, wu_cd mismatch |
| `trail_flat_power_walk` | tempo | description, structure, wu_cd mismatch |
| `trail_flat_proprioception` | interval | description, structure, wu_cd mismatch |
| `trail_long_fast_finish` | long | description, structure, wu_cd mismatch, steps_builder |
| `trail_long_rolling_hills` | long | description, structure, wu_cd mismatch, steps_builder |
| `trail_long_race_simulation` | long | description, structure, wu_cd mismatch, steps_builder |
| `trail_flat_long_fast_finish` | long | description, structure, wu_cd mismatch, steps_builder |
| `trail_flat_long_fueling` | long | description, structure, wu_cd mismatch, steps_builder |
| `trail_flat_long_race_sim` | long | description, structure, wu_cd mismatch, steps_builder |

## Implementation Plan

### Step 1: Re-sync Description & Structure After Step Computation

**File:** `app/core/training/key_workout_library.py`

After the step-computed distance overwrite (around line 617), re-run the description rewrite and re-derive structure for workouts that don't have explicit `_STRUCTURE_REWRITES`.

```python
# Current code (lines 615-617):
steps_total_km = _steps_mod._compute_distance_from_steps(workout['steps'])
if steps_total_km > 0:
    workout['distance'] = round(steps_total_km, 1)

# Replace with:
steps_total_km = _steps_mod._compute_distance_from_steps(workout['steps'])
if steps_total_km > 0:
    workout['distance'] = round(steps_total_km, 1)
    if key_wk['id'] in _DISTANCE_REWRITES:
        workout['description'] = _DISTANCE_REWRITES[key_wk['id']](workout['distance'])
        if key_wk['id'] not in _STRUCTURE_REWRITES:
            workout['structure'] = _derive_structure(workout['description'])
```

### Step 2: Unify Warmup/Cooldown Calculation

**File:** `app/core/training/key_workout_library.py`

Replace the `_wu_cd()` function to match `workout_steps._wucd_m()` logic exactly.

```python
# Current:
def _wu_cd(d: float) -> tuple:
    wu = min(2.0, max(0.5, round(d * 0.25, 1)))
    return (wu, wu)

# Replace with:
def _wu_cd(d: float) -> tuple:
    """Return (warmup_km, cooldown_km) matching workout_steps._wucd_m exactly."""
    total_m = int(round(d * 1000))
    wu_m = min(2000, max(500, int(round(total_m * 0.25))))
    return (wu_m / 1000.0, wu_m / 1000.0)
```

### Step 3: Improve `_derive_structure` for Non-Standard Descriptions

**File:** `app/core/training/key_workout_library.py`

The current `_derive_structure` doesn't handle descriptions that start with non-Run sentences (e.g., `trail_technical_terrain` starts with "Find a technical trail...").

```python
# Current:
def _derive_structure(description: str) -> str:
    s = re.sub(r"Warm up [\d.]+km easy\.\s*", "", description)
    s = re.sub(r"\s*Cool down [\d.]+km easy\.", "", s)
    s = re.sub(r"^Run\s+", "", s.strip())
    return s.strip()

# Replace with:
def _derive_structure(description: str) -> str:
    s = re.sub(r"Warm up [\d.]+km easy[^.]*\.\s*", "", description)
    s = re.sub(r"\s*Cool down [\d.]+km easy[^.]*\.", "", s)
    s = re.sub(r"^Run\s+", "", s.strip())
    s = re.sub(r"^Find a[^.]*\.\s*", "", s.strip())
    return s.strip()
```

## Testing

After implementation, verify with:

1. Generate a trail plan with a short distance (e.g., 30km trail, 8 weeks) to trigger the `_KEY_WORKOUT_MIN_DISTANCE_KM` floor
2. Check that `workout['description']` distance matches `workout['distance']` for all trail key workouts
3. Check that `workout['structure']` is consistent with the description
4. Run existing tests: `python3 -m pytest tests/test_plan_generator.py -v`

## Risk Assessment

- **Low risk**: Changes are localized to the reconciliation step at the end of `overlay_key_workout()`
- **No API changes**: All changes are internal to the workout generation pipeline
- **Backwards compatible**: Existing non-trail workouts are unaffected (they don't use `_DISTANCE_REWRITES`)
