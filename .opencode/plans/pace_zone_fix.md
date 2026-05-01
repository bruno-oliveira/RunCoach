# Fix: Race-Specific Pace Zones for 10K/5K Workouts

## Problem

Workout cards that reference "10K pace" (e.g., Structured Fartlek: "6 x 3 min at 10K pace") display **Threshold (T) pace** instead of the actual 10K race pace. This happens because the system has no dedicated zone for race-specific paces -- it approximates 10K pace as T-pace (~86% VO2max) when the true 10K race pace is closer to ~95-97% VO2max.

### Visual Evidence

From the screenshots:
- **Structured Fartlek** shows `6 × 3 min on / 2 min off` at `6:37/km` labeled "hard" with a `T` badge
- This is T-pace (threshold), but the workout description says "at 10K pace"
- The actual 10K race pace should be noticeably faster than threshold pace

## Root Cause

Three locations conflate VDOT training zones with race-specific paces:

| File | Lines | Issue |
|------|-------|-------|
| `vdot_calculator.py` | 229-230 | `"10K pace"` replaced with T-pace string in descriptions |
| `key_workout_parser.py` | 23 | Regex maps `"10K pace"` → zone `"T"` |
| `key_workout_data.py` | 188, 229 | 10K workouts declare `"pace_zone": "T"` |

The `ZONE_PCT` dictionary only defines E, M, T, I, R zones -- no 5K or 10K race pace zones exist.

## Solution

Add dedicated `"5K"` and `"10K"` zone keys computed from predicted race times via the existing `predict_time_for_distance()` function. These zones represent the actual pace a runner would hold for that race distance, not a training zone approximation.

---

## Step 1: Add race-specific zones to `get_pace_zones()`

**File:** `app/core/training/vdot_calculator.py`

**Current signature (line 117):**
```python
def get_pace_zones(vdot: float) -> Dict[str, Dict]:
```

**Change to:**
```python
def get_pace_zones(vdot: float, target_distance_km: float = 0.0) -> Dict[str, Dict]:
```

**Add after line 188 (after the "R" zone, before the return):**

```python
# Race-specific pace zones computed from predicted race times
race_paces: Dict[str, Dict] = {}
for dist_km, label in [(5.0, "5K"), (10.0, "10K")]:
    race_seconds = predict_time_for_distance(vdot, dist_km)
    if race_seconds:
        race_pace = (race_seconds / 60.0) / dist_km
        race_paces[label] = {
            "pace_min_km": round(race_pace, 2),
            "pace_str": _format_pace(race_pace),
            "description": f"{label} race pace",
        }

# If user has a specific target distance, also add a "race" zone for it
if target_distance_km > 0 and target_distance_km not in (5.0, 10.0):
    race_seconds = predict_time_for_distance(vdot, target_distance_km)
    if race_seconds:
        race_pace = (race_seconds / 60.0) / target_distance_km
        race_paces["race"] = {
            "pace_min_km": round(race_pace, 2),
            "pace_str": _format_pace(race_pace),
            "description": f"{target_distance_km}K race pace",
        }
```

**Update the return statement (line 148) to merge race_paces:**
```python
return {
    "E": { ... },
    "M": { ... },
    "T": { ... },
    "I": { ... },
    "R": { ... },
    **race_paces,  # NEW
}
```

---

## Step 2: Update `_PACE_ZONE_PATTERNS` in parser

**File:** `app/core/training/key_workout_parser.py:21-27`

**Current:**
```python
_PACE_ZONE_PATTERNS = [
    (r"\b5K pace\b|\bVO₂max\b|\bVO2max\b|\bI[- ]pace\b", "I"),
    (r"\bthreshold\b|\btempo pace\b|\b10K pace\b|\bT[- ]pace\b", "T"),
    (r"\bmarathon (?:goal )?pace\b|\bMP\b|\bM[- ]pace\b", "M"),
    (r"\beasy(?:\s+(?:pace|effort))\b|\bE[- ]pace\b|\bconversational\b", "E"),
    (r"\brepetition\b|\bR[- ]pace\b|\b5K[- ]?10K sprint\b", "R"),
]
```

**Change to:**
```python
_PACE_ZONE_PATTERNS = [
    (r"\b5K pace\b|\bVO₂max\b|\bVO2max\b|\bI[- ]pace\b", "I"),
    (r"\b10K pace\b|\b10k pace\b", "10K"),              # NEW: before T pattern
    (r"\bthreshold\b|\btempo pace\b|\bT[- ]pace\b", "T"),  # removed 10K from here
    (r"\bmarathon (?:goal )?pace\b|\bMP\b|\bM[- ]pace\b", "M"),
    (r"\beasy(?:\s+(?:pace|effort))\b|\bE[- ]pace\b|\bconversational\b", "E"),
    (r"\brepetition\b|\bR[- ]pace\b|\b5K[- ]?10K sprint\b", "R"),
]
```

**Critical:** The `"10K pace"` pattern must come BEFORE the `"T"` pattern.

---

## Step 3: Update `inject_paces_into_description()`

**File:** `app/core/training/vdot_calculator.py:218-231`

**Current:**
```python
replacements = {
    "5K pace": f"{zones['I']['pace_str']} (I-pace)",
    "5k pace": f"{zones['I']['pace_str']} (I-pace)",
    "VO2 max pace": f"{zones['I']['pace_str']} (I-pace)",
    "VO2max pace": f"{zones['I']['pace_str']} (I-pace)",
    "threshold pace": f"{zones['T']['pace_str']} (T-pace)",
    "tempo pace": f"{zones['T']['pace_str']} (T-pace)",
    "marathon goal pace": f"{zones['M']['pace_str']} (M-pace)",
    "marathon pace": f"{zones['M']['pace_str']} (M-pace)",
    "10K pace": f"{zones['T']['pace_str']} (T-pace)",
    "10k pace": f"{zones['T']['pace_str']} (T-pace)",
}
```

**Change to:**
```python
replacements = {
    # Interval cues
    "5K pace": f"{zones['I']['pace_str']} (I-pace)",
    "5k pace": f"{zones['I']['pace_str']} (I-pace)",
    "VO2 max pace": f"{zones['I']['pace_str']} (I-pace)",
    "VO2max pace": f"{zones['I']['pace_str']} (I-pace)",
    # Race-specific cues (NEW)
    "10K pace": f"{zones['10K']['pace_str']} (10K pace)",
    "10k pace": f"{zones['10K']['pace_str']} (10K pace)",
    # Tempo cues
    "threshold pace": f"{zones['T']['pace_str']} (T-pace)",
    "tempo pace": f"{zones['T']['pace_str']} (T-pace)",
    "marathon goal pace": f"{zones['M']['pace_str']} (M-pace)",
    "marathon pace": f"{zones['M']['pace_str']} (M-pace)",
}
```

---

## Step 4: Fix `pace_zone` values in key workout data

**File:** `app/core/training/key_workout_data.py`

**Line 188** (`10k_goal_pace_segments`):
```python
# Change from:
"pace_zone": "T",
# To:
"pace_zone": "10K",
```

**Line 229** (`10k_fartlek`):
```python
# Change from:
"pace_zone": "T",
# To:
"pace_zone": "10K",
```

**Line 209** (`10k_tempo_progression`): Keep as `"T"` -- this is a progression run where the main block builds to 10K pace, not pure 10K pace throughout.

---

## Step 5: Update callers of `get_pace_zones()` to pass `target_distance_km`

Search for all calls to `get_pace_zones()` and update them:

**Files to check:**
- `app/core/generators/performance_plan_generator.py`
- `app/core/generators/fitness_plan_generator.py`
- `app/core/training/key_workout_library.py`
- `app/services/plan_service.py`

**Pattern to update:**
```python
# Before:
pace_zones = VDOTCalculator.get_pace_zones(vdot)

# After:
pace_zones = VDOTCalculator.get_pace_zones(vdot, target_distance_km=target_distance)
```

---

## Step 6: Verify `_pace_str()` handles new zone keys

**File:** `app/core/training/workout_steps.py`

The `_pace_str()` helper does a generic dict lookup, so it should work as-is with the new `"5K"`, `"10K"`, and `"race"` keys.

---

## Step 7: Run tests

```bash
python3 -m pytest tests/test_vdot_calculator.py tests/test_key_workouts.py -v
```

---

## Expected Outcome

### Before
- Structured Fartlek: `6 × 3 min on / 2 min off` → `6:37/km` with `T` badge

### After
- Structured Fartlek: `6 × 3 min on / 2 min off` → `~6:00/km` with `10K` badge
- 10K race pace is faster than T-pace (95-97% VO2max vs 86%)

---

## Trade-offs

1. **5K pace still maps to I-pace**: I-pace (98% VO2max) is a reasonable approximation for 5K. A dedicated `"5K"` zone could be added later.

2. **Zone key naming**: `"5K"` and `"10K"` are clear and match workout description text.

3. **Backward compatibility**: `target_distance_km` defaults to `0.0`, so existing callers still work.

4. **Half marathon / marathon**: Already use M-pace appropriately. The `"race"` zone gives exact predicted pace for any target distance.
