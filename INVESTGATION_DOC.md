# Investigation: PERFORMANCE Plan Generation Algorithm Skew

**Date:** 2026-04-20  
**Status:** Findings documented  
**Scope:** `PerformancePlanGenerator` and `performance_workout_builders.py`

## Executive Summary

The PERFORMANCE (time-goal-based) plan generator produces severely skewed workout distributions, particularly for runners with lower weekly mileage. The core issue is that **quality workout distances are calculated as percentages of the target race distance**, while **the long run is calculated as a percentage of weekly volume**. This creates plans where tempo runs can be 2.6x longer than the long run, and easy runs can be as short as 0.1km.

## Critical Findings

### 1. Quality Workouts Use Race Distance Instead of Weekly Volume

**File:** `performance_workout_builders.py`

All quality workout builders receive `distance_km` as a parameter, which is the **target race distance**, not the runner's weekly mileage. This causes workouts to be sized inappropriately for the runner's actual training volume.

```python
# generate_tempo_workout (line 40-55)
def generate_tempo_workout(zones, distance_km, week, phase):
    if phase == 'base':
        tempo_km = min(6, distance_km * 0.6)  # 60% of race distance!
    elif phase == 'build':
        tempo_km = min(10, distance_km * 0.8)  # 80% of race distance!
    elif phase == 'peak':
        tempo_km = min(12, distance_km)  # 100% of race distance!
```

**Impact:** A runner training for a 10K race gets a 6-10km tempo run regardless of whether they run 15km/week or 60km/week.

### 2. Fartlek Workouts Use Hardcoded Distances

**File:** `performance_workout_builders.py:190-206`

```python
if phase == 'base':
    total_km = 8   # Fixed 8km fartlek
elif phase == 'build':
    total_km = 10  # Fixed 10km fartlek
elif phase == 'peak':
    total_km = 12  # Fixed 12km fartlek
```

**Impact:** A runner doing 15km/week is prescribed an 8km fartlek (53% of weekly volume in one workout).

### 3. Long Run Uses Weekly Volume (Correct Approach)

**File:** `performance_workout_builders.py:247-260`

```python
def generate_long_run(zones, weekly_km, week, phase, distance_km):
    long_run_km = weekly_km * 0.30  # 30% of weekly volume
```

**Impact:** This is the correct approach, but creates the skew when compared to quality workouts that use race distance.

### 4. Easy Runs Get "Leftover" Volume

**File:** `performance_plan_generator.py:276-288`

```python
remaining_km = weekly_km - total_assigned_km
easy_runs_needed = runs_per_week - len(daily_workouts)
if easy_runs_needed > 0 and remaining_km > 0:
    easy_run_km = remaining_km / easy_runs_needed
```

**Impact:** When quality workouts consume most of the weekly volume, easy runs become tiny or sub-1km.

## Quantified Skew Analysis

| Scenario | Start km/week | Tempo/Long Ratio | Shortest Easy | Notes |
|----------|---------------|------------------|---------------|-------|
| 5K low mileage | 15km | 1.50x | 0.5km | Tempo longer than long run |
| 5K medium | 25km | 0.85x | 2.4km | Acceptable |
| 10K low mileage | 12km | 2.59x | 0.1km | **Severe skew** |
| 10K medium | 30km | 1.01x | 3.4km | Tempo equals long run |
| Half low | 25km | 1.28x | 1.6km | Tempo longer than long run |
| Half medium | 40km | 0.80x | 5.4km | Acceptable |

### Extreme Example: 10K Plan Starting at 12km/week

```
Week 1: tempo=10.0km, long=3.9km (2.56x ratio)
Week 3: easy=0.1km (twice), tempo=10.0km, long=4.4km
Week 4: vo2max=8.8km, tempo=12.0km, long=4.9km
Week 7: vo2max=9.0km, race_pace=12.0km, long=6.1km
```

## Root Causes

### 1. Parameter Misuse in Workout Builders

The `distance_km` parameter in quality workout builders represents the **target race distance**, but the functions treat it as if it were **weekly training volume**. This fundamental confusion causes all quality workouts to be sized incorrectly.

### 2. Missing Quality Caps

The standard `TrainingPlanGenerator` enforces quality caps via `quality_caps.py`:

```python
MAX_QUALITY_VS_LONG_RUN = 0.85  # Quality ≤ 85% of long run
MAX_EASY_VS_LONG_RUN = 0.95     # Easy ≤ 95% of long run
```

**The performance generator does NOT apply these caps.**

### 3. No Minimum Distance Guards

There is no validation that:
- Easy runs meet a minimum distance (e.g., 3km for most runners)
- Quality workouts don't exceed a percentage of weekly volume
- The long run is always the longest run of the week

### 4. Hardcoded Fartlek Distances

Fartlek workouts ignore both race distance and weekly volume, using fixed phase-based distances that are inappropriate for many runners.

## Comparison with Standard Generator

The `TrainingPlanGenerator` (used for distance-based plans) follows a correct approach:

1. **Long run first:** Calculate as percentage of weekly volume
2. **Quality caps:** Enforce `MAX_QUALITY_VS_LONG_RUN` and physiological caps
3. **Easy allocation:** Distribute remaining volume to easy runs
4. **Validation:** Validate week plans before returning

The performance generator skips steps 2, 3, and 4.

## Recommended Fixes

### Immediate (High Impact)

1. **Pass weekly_km to quality builders** instead of race distance
2. **Apply quality caps** from `quality_caps.py` to all quality workouts
3. **Add minimum easy run distance** (e.g., 3km or 20% of long run)
4. **Cap fartlek distances** to weekly volume percentages

### Structural (Medium Impact)

5. **Refactor builders** to accept both race distance and weekly volume
6. **Add validation layer** similar to `_validate_week_plan` in standard generator
7. **Scale quality distances** by phase and runner level

### Long-term (Low Impact)

8. **Unify generation logic** between performance and standard generators
9. **Add runner profile integration** for better personalization
10. **Implement adaptive scaling** based on logged performance

## Files Requiring Changes

| File | Priority | Changes Needed |
|------|----------|----------------|
| `performance_workout_builders.py` | High | Fix distance calculations, add caps |
| `performance_plan_generator.py` | High | Add validation, apply quality caps |
| `quality_caps.py` | Medium | Extend caps for performance workout types |
| Tests | Medium | Add skew detection tests |

## Regular Plan Generator Findings

The standard `TrainingPlanGenerator` is significantly more robust than the performance generator, but has **two notable issues**:

### 1. Quality Caps Cause Volume Shortfall

**Severity:** Medium  
**Impact:** Plans consistently under-deliver target weekly mileage by 10-30%

The quality caps (`MAX_QUALITY_VS_LONG_RUN = 0.85`, `MAX_EASY_VS_LONG_RUN = 0.95`) prevent workouts from exceeding these ratios, but when the target weekly volume is high relative to the long run distance, **the caps cause systematic volume loss**.

**Example: 10K medium (30km/week start, 4 runs)**
```
Week 10 (peak): Target 61.8km, Actual 50.9km (10.9km shortfall)
  Distribution: long=15km, interval=7.5km, easy=2x14.2km
  Max possible: 15 + 12.8 + 2*14.2 = 56.2km (cap-limited)
```

The caps are working as designed to preserve the 80/20 ratio, but when weekly volume grows faster than long run distance, the plan cannot fill the gap without violating the caps.

**Affected scenarios:**
- 5K low base: Week 4 validation failed (20.2km target, 16.9km actual)
- 5K medium: Weeks 6-9 validation failed (40-47km target, 35.8km actual)
- 10K medium: Weeks 7-11 validation failed (53-62km target, 50-51km actual)
- 10K high: Weeks 6-11 validation failed (80-104km target, 69-71km actual)

### 2. Easy Runs Hit Upper Cap

**Severity:** Low  
**Impact:** Easy runs can reach 95-97% of long run distance

When easy runs are capped at `MAX_EASY_VS_LONG_RUN * long_run`, they can become nearly as long as the long run itself, which defeats the purpose of easy recovery runs.

**Example:**
```
5K low base Week 4: easy=4.8km, long=5.0km (0.96x ratio)
10K low base Week 4: easy=4.3km, long=4.5km (0.96x ratio)
```

### Comparison Summary

| Issue | Performance Generator | Regular Generator |
|-------|----------------------|-------------------|
| Quality > Long run | ✅ Yes (up to 2.6x) | ❌ No (capped at 0.85x) |
| Easy runs < 1km | ✅ Yes (0.1km) | ❌ No (min ~2.8km) |
| Volume shortfall | ❌ No (fills exactly) | ✅ Yes (10-30% under) |
| Validation failures | ❌ No validation | ✅ Yes (caps cause mismatch) |
| Fartlek hardcoded | ✅ Yes (8-12km) | ❌ N/A |

## Final Comprehensive Analysis

Tested across 10 scenarios covering all race distances and mileage ranges:

| Scenario | Start km | Tempo/Long | Quality/Long | Fartlek/Long | Shortest Easy | Issues |
|----------|----------|------------|--------------|--------------|---------------|--------|
| 5K very low | 10km | 2.26x | 2.26x | 2.32x | 0.0km | 28 |
| 5K low | 15km | 1.50x | 1.50x | 1.55x | 0.5km | 17 |
| 5K medium | 25km | 0.85x | 0.85x | 1.23x | 2.4km | 1 |
| 10K very low | 10km | 3.12x | 3.12x | 2.32x | 0.0km | 22 |
| 10K low | 12km | 2.59x | 2.59x | 1.93x | 0.1km | 24 |
| 10K medium | 30km | 1.01x | 1.01x | 1.03x | 3.4km | 2 |
| Half low | 25km | 1.28x | 1.28x | 1.23x | 1.6km | 15 |
| Half medium | 40km | 0.80x | 0.80x | 0.77x | 5.4km | 0 |
| Marathon low | 35km | 0.89x | 1.10x | 0.97x | 5.7km | 1 |
| Marathon medium | 55km | 0.56x | 0.69x | 0.61x | 7.6km | 0 |

**Key patterns:**
- Plans are acceptable when starting mileage ≥ 35km/week for the target distance
- Severe skew occurs below 25km/week, with quality workouts up to 3x longer than long runs
- Quality workouts consume up to 84% of weekly volume in low-mileage plans (should be 20-30%)

## Testing Recommendations

1. Test plans across mileage ranges (10-60km/week)
2. Verify long run is always longest run
3. Verify easy runs meet minimum distance
4. Verify quality workouts don't exceed 85% of long run
5. Test all race distances (5K, 10K, Half, Marathon)
6. **For regular plans:** Investigate volume shortfall when caps prevent filling target mileage
7. **For regular plans:** Consider whether easy run cap should be lower (e.g., 80% of long run)

## Proposed Recommendations

**⚠️ WARNING: The specific ratios, caps, and thresholds below are derived from algorithmic analysis of what produces reasonable output (not from coaching expertise or sports science literature). They are designed to fix the structural problems identified in this investigation. An LLM can implement these directly, but the values should be reviewed and adjusted once real-world feedback is available.**

### Performance Generator Fixes

#### 1. Scale Quality Workouts to Weekly Volume (Not Race Distance)

**Problem:** Quality builders use `distance_km` (race distance) instead of `weekly_km`, causing workouts sized for the race rather than the runner's capacity.

**Implementation:**

Change all quality workout builders in `performance_workout_builders.py` to accept `weekly_km` and base distances on it:

```python
def generate_tempo_workout(zones: Dict, weekly_km: float, week: int, phase: str) -> Dict:
    """Generate a tempo workout scaled to weekly volume."""
    target_pace = zones['zone_3_tempo']['pace']

    # Tempo as percentage of weekly volume, phase-scaled
    if phase == 'base':
        tempo_km = min(6, weekly_km * 0.20)  # 20% of weekly volume
    elif phase == 'build':
        tempo_km = min(10, weekly_km * 0.25)  # 25% of weekly volume
    elif phase == 'peak':
        tempo_km = min(12, weekly_km * 0.30)  # 30% of weekly volume
    else:  # taper
        tempo_km = min(5, weekly_km * 0.15)  # 15% of weekly volume

    warmup_km = 2
    cooldown_km = 2
    total_km = warmup_km + tempo_km + cooldown_km
    # ... rest of function unchanged
```

Apply the same pattern to other builders:

- **VO2max:** `interval_km = weekly_km * 0.15` (base), `0.20` (build), `0.18` (peak), `0.12` (taper)
- **Race pace:** `race_km = weekly_km * 0.15` (base), `0.20` (build), `0.25` (peak), `0.10` (taper)
- **Fartlek:** `total_km = weekly_km * 0.20` (base), `0.25` (build), `0.28` (peak), `0.15` (taper)

**Update call sites** in `performance_plan_generator.py` to pass `weekly_km` instead of `target_distance`:

```python
# In _generate_weekly_plan, change:
'tempo': lambda: generate_tempo_workout(zones, target_distance, week_number, phase),
# To:
'tempo': lambda: generate_tempo_workout(zones, weekly_km, week_number, phase),
```

**⚠️ Assumption:** The percentages (20-30% of weekly volume for tempo) are chosen to produce reasonable outputs across the tested scenarios. They may need tuning based on user feedback.

#### 2. Apply Quality Caps from Standard Generator

**Problem:** Performance generator has no caps preventing quality workouts from exceeding long run distance.

**Implementation:**

Add cap enforcement to `performance_plan_generator.py` in `_generate_weekly_plan`, after all workouts are generated but before returning:

```python
from app.core.training.quality_caps import (
    MAX_QUALITY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    get_quality_caps,
)

# After generating all daily_workouts, before calculating actual_total_km:
long_runs = [w for w in daily_workouts if w['type'] == 'long']
if long_runs:
    long_dist = long_runs[0]['distance']

    # Cap quality workouts
    for workout in daily_workouts:
        if workout.get('quality', False) and workout['distance'] > 0:
            ceiling = long_dist * MAX_QUALITY_VS_LONG_RUN
            phys_caps = get_quality_caps(target_distance, phase)
            cap = min(ceiling, phys_caps.get(workout['type'], ceiling))
            if workout['distance'] > cap:
                workout['distance'] = round(cap, 1)
                # Recalculate segments proportionally
                for seg in workout.get('segments', []):
                    if seg['type'] == 'main':
                        seg['distance_km'] = round(cap - 4, 1)  # Subtract warmup+cooldown

    # Cap easy runs
    for workout in daily_workouts:
        if workout['type'] == 'easy' and workout['distance'] > 0:
            max_easy = long_dist * MAX_EASY_VS_LONG_RUN
            if workout['distance'] > max_easy:
                workout['distance'] = round(max_easy, 1)
```

**⚠️ Assumption:** The same caps (0.85 for quality, 0.95 for easy) from the standard generator are appropriate for performance plans. If performance plans should allow more intensity, these could be raised to 0.90 and 1.0 respectively.

#### 3. Add Minimum Easy Run Distance

**Problem:** Easy runs can be 0.0-0.5km when quality workouts consume most of the weekly volume.

**Implementation:**

In `performance_plan_generator.py`, after calculating `easy_run_km`:

```python
# In _generate_weekly_plan, after:
easy_run_km = remaining_km / easy_runs_needed

# Add minimum floor:
min_easy_km = max(3.0, long_runs[0]['distance'] * 0.20) if long_runs else 3.0
easy_run_km = max(easy_run_km, min_easy_km)
```

This ensures easy runs are at least 3km or 20% of the long run distance, whichever is greater.

**⚠️ Assumption:** 3km is a reasonable minimum for an effective easy run. This may need adjustment for very low-mileage runners (e.g., those starting at 10km/week).

#### 4. Add Validation Layer

**Problem:** Performance generator has no validation to catch skew before returning plans.

**Implementation:**

Add a `_validate_week_plan` method to `PerformancePlanGenerator`, mirroring the standard generator:

```python
def _validate_week_plan(self, workouts: List[Dict], total_km: float,
                        target_total_km: float, phase: str) -> tuple[bool, str]:
    """Validate week plan follows training principles."""
    long_runs = [w for w in workouts if w['type'] == 'long']
    long_dist = long_runs[0]['distance'] if long_runs else 0

    for workout in workouts:
        # Quality should not exceed long run
        if workout.get('quality', False) and workout['distance'] > long_dist * 1.1:
            return False, f"Quality workout {workout['type']} ({workout['distance']}km) exceeds long run ({long_dist}km)"

        # Easy runs should meet minimum
        if workout['type'] == 'easy' and workout['distance'] > 0 and workout['distance'] < 2.0:
            return False, f"Easy run too short ({workout['distance']}km)"

    # Total distance tolerance
    tolerance = target_total_km * 0.05
    if abs(total_km - target_total_km) > tolerance:
        return False, f"Total distance mismatch: expected {target_total_km}km, got {total_km}km"

    return True, "Valid"
```

Call this at the end of `_generate_weekly_plan` and include validation status in the returned week plan.

### Regular Generator Fixes

#### 5. Address Volume Shortfall from Quality Caps

**Problem:** When quality caps prevent filling target mileage, plans under-deliver by 10-30%.

**Root cause:** The caps limit individual workout sizes, but the weekly volume target assumes those workouts can be larger.

**Implementation:**

In `plan_generator.py`, after capping quality workouts and allocating easy distances, if there's still a shortfall, redistribute the remaining volume to easy runs (up to a higher cap):

```python
# In _generate_daily_workouts, after easy_distances allocation:

actual_total = long_run_distance + quality_total + sum(easy_distances)
shortfall = total_km - actual_total

if shortfall > total_km * 0.05 and easy_runs > 0:
    # Redistribute shortfall to easy runs with a relaxed cap
    relaxed_max = long_run_distance * 1.10  # Allow easy runs up to 110% of long run
    extra_per_easy = shortfall / easy_runs
    for i in range(len(easy_distances)):
        new_distance = easy_distances[i] + extra_per_easy
        easy_distances[i] = round(min(new_distance, relaxed_max), 1)
```

**⚠️ Assumption:** Allowing easy runs to slightly exceed the long run (up to 110%) is acceptable when it's the only way to hit target volume. The alternative would be to reduce the target progression, but that would compound over weeks and leave runners undertrained.

#### 6. Lower Easy Run Cap (Optional)

**Problem:** Easy runs can reach 95-97% of long run distance, defeating the purpose of recovery.

**Implementation:**

In `quality_caps.py`, change:

```python
# Current:
MAX_EASY_VS_LONG_RUN = 0.95

# Proposed:
MAX_EASY_VS_LONG_RUN = 0.80
```

**⚠️ WARNING:** This change will increase the volume shortfall issue (#5). Implement #5 first, then test whether this cap causes acceptable behavior across all scenarios. If it causes excessive shortfall, consider keeping 0.95 but adding a secondary check that easy runs don't exceed `long_run - 2km`.

### Structural Improvements

#### 7. Unify Quality Cap Enforcement

Create a shared function in `quality_caps.py` that both generators can use:

```python
def enforce_week_caps_v2(workouts: List[Dict], target_distance: float,
                         phase: str, long_run_distance: float) -> List[Dict]:
    """Apply quality and easy caps to a week's workouts (in place).

    Returns the modified workouts list.
    """
    quality_types = ('tempo', 'interval', 'hill', 'vo2max', 'race_pace', 'fartlek')

    for workout in workouts:
        wtype = workout.get('type', '')
        dist = workout.get('distance', 0)

        if wtype in quality_types and dist > 0:
            capped = cap_quality_distance(dist, long_run_distance, wtype, target_distance, phase)
            workout['distance'] = capped
        elif wtype == 'easy' and dist > 0:
            capped = cap_easy_distance(dist, long_run_distance)
            workout['distance'] = capped

    return workouts
```

Then call this from both generators after workout generation.

## Implementation Order

1. **Fix #1** (Scale quality to weekly volume) — addresses the root cause of performance plan skew
2. **Fix #2** (Apply quality caps) — prevents individual workout excess
3. **Fix #3** (Minimum easy run) — prevents sub-1km easy runs
4. **Fix #4** (Validation layer) — catches any remaining issues
5. **Fix #5** (Volume shortfall) — addresses regular plan under-delivery
6. **Fix #7** (Unify caps) — structural improvement for maintainability
7. **Fix #6** (Lower easy cap) — optional, test after #5 is implemented

## Post-Implementation Validation

After implementing these fixes, verify:

1. Generate plans across all scenarios in the comprehensive analysis table
2. Confirm no quality workout exceeds long run distance
3. Confirm no easy run is below 3km
4. Confirm total weekly volume matches target within 5%
5. Confirm plans still feel appropriately challenging for higher-mileage runners
6. Monitor user feedback for 2-4 weeks and adjust ratios if needed
