# Bug: "Adjusted" Banner Appears on Freshly Generated Plans

## Summary

The "adjusted from X km" chip appears on interval runs (and potentially other workouts) in freshly generated training plans, even though no adaptation has occurred and the user hasn't even set a start date yet.

## Reproduction

1. Generate a new training plan (e.g., 8-week plan)
2. View the plan immediately, before setting a start date
3. Observe that Week 8's interval run shows an "adjusted from X km" banner

## Root Cause

The bug is in `app/contexts/plan/plan_data_enricher.py`, specifically in the `enrich_plan_data_with_ids()` function (lines 121-194).

### Data Flow

1. **Generation**: `TrainingPlanGenerator` creates `plan_data` with workout distances
2. **Persistence**: `persist_weekly_workouts()` saves each workout with:
   ```python
   DailyWorkout(
       distance_km=dist,
       baseline_distance_km=dist,  # Same value as distance
   )
   ```
3. **View Enrichment**: When viewing the plan, `enrich_plan_data_with_ids()` runs:
   - `_repair_key_workout_steps()` bumps distance if below minimum (line 147)
   - Steps-based distance recompute changes distance if it differs by >0.2km (lines 149-156)
   - After these modifications, `workout["distance"]` no longer equals `baseline_distance_km`
   - Line 171-172 then sets `workout["baseline_distance"] = bl`:
     ```python
     if bl is not None and bl != workout.get("distance"):
         workout["baseline_distance"] = bl
     ```
4. **Template**: `workout_item.html` line 24-27 renders the chip when `baseline_distance` exists and differs from `distance`:
   ```html
   {% if workout.baseline_distance and workout.baseline_distance != workout.distance %}
     <span class="workout-adjusted-chip">adjusted from {{ '%.1f'|format(workout.baseline_distance) }} km</span>
   {% endif %}
   ```

### Why This Happens

The enrichment process modifies `workout["distance"]` for display purposes (steps-based recompute, key workout minimum bump), but the stored `baseline_distance_km` still holds the original value. The comparison at line 171 sees them as different and surfaces the baseline, triggering the "adjusted" chip — even though no actual plan adaptation occurred.

## Proposed Fix

Gate the baseline distance surfacing behind actual adaptation markers. Only show the "adjusted" chip when the plan has been genuinely adapted, indicated by:
- `training_plan.adjustment_multiplier` is set, OR
- `training_plan.last_recalibrated_at` is set, OR
- `training_plan.last_adjusted_at` is set

### Implementation

Modify `enrich_plan_data_with_ids()` to accept the `TrainingPlan` object and check for adaptation markers before surfacing the baseline distance:

```python
def enrich_plan_data_with_ids(
    plan_data: list[dict],
    training_plan_id: str,
    db: Session,
    training_plan: TrainingPlan | None = None,
) -> list[dict]:
    # ... existing code ...
    
    is_actually_adapted = training_plan and (
        training_plan.adjustment_multiplier is not None
        or training_plan.last_recalibrated_at is not None
        or training_plan.last_adjusted_at is not None
    )
    
    for week in plan_data:
        # ... existing code ...
        
        # Only surface baseline when plan has been genuinely adapted
        if is_actually_adapted and bl is not None and bl != workout.get("distance"):
            workout["baseline_distance"] = bl
```

Then update all callers to pass the `training_plan` object.

## Files Affected

1. `app/contexts/plan/plan_data_enricher.py` - Main fix location
2. `app/contexts/plan/plan_service.py` - Update `enrich_plan_data_with_ids()` signature
3. `app/contexts/plan/plan_view_service.py` - Update `enrich_plan_data_with_ids()` signature
4. `app/web/routers/plan_view.py` - Pass `training_plan` to enricher
5. `app/web/routers/plan_sharing.py` - Pass `training_plan` to enricher
6. `app/web/routers/nutrition.py` - Pass `training_plan` to enricher
7. `tests/test_services/test_plan_data_enricher.py` - Update tests
