# Trail VDOT Prediction Fix

## Problem
VDOT predicts 2h29 for a trail race that actually took 4h20 (~75% underestimation).

## Root Causes (4 compounding issues)

### 1. General predictions don't pass elevation data
- `RacePredictorService.get_predictions_for_user()` → `predict_time_for_distance(vdot, distance, endurance_factor=...)` — **no elevation_gain_m, no trail_runs_count**
- `VDOTCalculator.predict_times()` → same, no elevation
- Result: trail predictions are flat-ground equivalents

### 2. Trail inexperience penalty too weak
- `_TRAIL_INEXPERIENCE_MAX_FACTOR = 1.25` (+25% max)
- Actual gap: 4h20/2h29 ≈ 1.75x

### 3. No ultra-endurance distance decay
- VDOT validated for efforts ≤3.5h; at 4h+ nutrition/fatigue dominate

### 4. `predict_times` can't accept per-distance elevation
- Iterates all distances without course profile info

---

## Changes

### File 1: `app/core/training/race_predictor.py`

**Change A — Strengthen trail inexperience:**
```python
# Line 67-68: increase threshold and max factor
_TRAIL_INEXPERIENCE_RUNS_THRESHOLD = 8   # was 5
_TRAIL_INEXPERIENCE_MAX_FACTOR = 1.50    # was 1.25
```

**Change B — Add ultra-endurance decay (new function after `_trail_inexperience_factor`):**
```python
_ULTRA_DECAY_ONSET_HOURS = 3.0
_ULTRA_DECAY_RATE_PER_HOUR = 0.05
_ULTRA_DECAY_MAX_FACTOR = 1.20

def _ultra_endurance_decay(distance_km: float, predicted_seconds: float) -> float:
    time_hours = predicted_seconds / 3600.0
    if time_hours <= _ULTRA_DECAY_ONSET_HOURS:
        return 1.0
    excess = time_hours - _ULTRA_DECAY_ONSET_HOURS
    factor = 1.0 + excess * _ULTRA_DECAY_RATE_PER_HOUR
    return min(factor, _ULTRA_DECAY_MAX_FACTOR)
```

**Change C — Apply decay in `predict_time_for_distance` (line ~148-154):**
```python
# After: total_seconds = flat_seconds + elevation_penalty_sec
# Before the endurance_factor application, add:
ultra_decay = _ultra_endurance_decay(distance_km, total_seconds)
total_seconds *= ultra_decay

# Then existing lines:
if endurance_factor and endurance_factor > 1.0:
    total_seconds *= endurance_factor
if is_trail:
    total_seconds *= _trail_inexperience_factor(trail_runs_count)
```

**Change D — Update `predict_times` to accept elevation map:**
```python
def predict_times(
    vdot: float,
    trail_runs_count: Optional[int] = None,
    elevation_map: Optional[Dict[str, float]] = None,
    endurance_factor: Optional[float] = None,
) -> Dict[str, Dict]:
    from app.core.training.vdot_calculator import VDOTCalculator

    predictions = {}
    for name, distance in STANDARD_RACE_DISTANCES.items():
        elev = None
        if elevation_map and name in elevation_map:
            elev = elevation_map[name]
        seconds = predict_time_for_distance(
            vdot, distance,
            elevation_gain_m=elev,
            trail_runs_count=trail_runs_count,
            endurance_factor=endurance_factor,
        )
        if seconds:
            predictions[name] = {
                "seconds": seconds,
                "formatted": VDOTCalculator.format_duration(seconds),
                "distance_km": distance,
            }
    return predictions
```

### File 2: `app/core/training/vdot_calculator.py`

**Update `predict_times` passthrough (line 341-346):**
```python
@staticmethod
def predict_times(
    vdot: float,
    trail_runs_count: Optional[int] = None,
    elevation_map: Optional[Dict[str, float]] = None,
    endurance_factor: Optional[float] = None,
) -> Dict[str, Dict]:
    from app.core.training.race_predictor import predict_times
    return predict_times(
        vdot, trail_runs_count, elevation_map, endurance_factor
    )
```

### File 3: `app/services/fitness/race_predictor_service.py`

**Update `get_predictions_for_user` (line 367-416):**
- For the trail distance specifically, compute average elevation gain from user's trail runs
- Pass `elevation_gain_m` and `trail_runs_count` when predicting trail

```python
# In get_predictions_for_user, before the predictions loop:
def _get_user_trail_elevation_profile(user_id: str, db: Session) -> Dict[str, Any]:
    """Compute user's typical trail elevation per km and trail run count."""
    trail_runs = (
        db.query(RunLog.distance_km, RunLog.elevation_gain_m)
        .filter(
            RunLog.user_id == user_id,
            RunLog.distance_km > 0,
            RunLog.elevation_gain_m.isnot(None),
        )
        .all()
    )
    trail_entries = [
        (d, e) for d, e in trail_runs
        if d and e and e / d >= 20.0
    ]
    if not trail_entries:
        return {"avg_m_per_km": None, "count": 0}
    count = len(trail_entries)
    avg_m_per_km = statistics.median([e / d for d, e in trail_entries])
    return {"avg_m_per_km": avg_m_per_km, "count": count}

# In the predictions loop, for trail distance:
trail_profile = _get_user_trail_elevation_profile(user_id, db)
for name, distance in STANDARD_RACE_DISTANCES.items():
    elev = None
    trail_count = None
    if name == "trail" and trail_profile["avg_m_per_km"]:
        elev = trail_profile["avg_m_per_km"] * distance
        trail_count = trail_profile["count"]

    endurance_factor = RacePredictorService.compute_endurance_factor(
        user_id, distance, db, current_vdot=current_vdot
    )
    seconds = VDOTCalculator.predict_time_for_distance(
        current_vdot, distance,
        elevation_gain_m=elev,
        trail_runs_count=trail_count,
        endurance_factor=endurance_factor,
    )
    # ... rest unchanged
```

### File 4: `app/routers/runs.py`

**Update run creation response (line 117-118):**
```python
# After creating a run, pass elevation for trail runs:
response_data = run_to_response(new_run)
if new_run.vdot:
    elevation_map = None
    trail_count = None
    if new_run.elevation_gain_m and new_run.distance_km > 0:
        if new_run.elevation_gain_m / new_run.distance_km >= 20.0:
            from app.services.runs.run_enrichment_service import _count_prior_trail_runs
            trail_count = _count_prior_trail_runs(current_user.id, db)
            elevation_map = {"trail": new_run.elevation_gain_m}
    response_data.predictions = VDOTCalculator.predict_times(
        new_run.vdot,
        trail_runs_count=trail_count,
        elevation_map=elevation_map,
    )
```

### File 5: `app/services/runs/run_enrichment_service.py`

**Export `_count_prior_trail_runs`** — it's already defined there, just needs to be importable (it is, since it's a module-level function).

### File 6: Tests

**Update `tests/test_core/test_vdot_calculator.py`:**
- Add test: trail prediction with elevation is significantly slower than flat
- Add test: ultra-endurance decay applies for >3h predictions
- Add test: strengthened inexperience factor (1.5x for 0 trail runs)

---

## Expected Impact

For the user's case (trail race, 0 trail runs, ~4h20 actual):
- Flat-ground VDOT prediction: ~2h29 (unchanged base)
- Elevation penalty (assuming typical trail ~50m/km × 30km = 1500m gain): adds ~15-20 min
- Trail inexperience (0 runs → 1.50x): 2h49 × 1.50 ≈ 4h14
- Ultra-endurance decay (~4h → 1.05x): 4h14 × 1.05 ≈ 4h27

Result: prediction moves from **2h29 → ~4h27**, very close to actual **4h20**.
