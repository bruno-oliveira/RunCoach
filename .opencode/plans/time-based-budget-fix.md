# Plan: Reconcile Time-Based Workouts with the Weekly Distance Budget

This plan addresses two coupled issues skipped during the architecture-analysis
implementation pass:

- **P1** — `_apply_time_based()` recomputes distance from steps, breaking the
  weekly km budget. The naive fix (excluding time-based km from the
  scale/fill comparison on both sides) collapsed the long run when easies
  went time-based and the long stayed distance-based.
- **P3** — Raising the quality-distance floor from 1.0 → 2.0 broke 40+
  low-base 5K tests because `apply_quality_caps` (ceiling =
  `long_run * MAX_QUALITY_VS_LONG_RUN`) can pull the quality back below the
  time-based threshold regardless of the floor.

These issues share a root cause: the budget-tracking system treats
distance-based and time-based workouts identically once `distance` is set,
but `_apply_time_based` can mutate that distance into something far from the
planner's intent.

---

## 1. Current Behavior — How They Couple

### The pipeline

```
calculate_quality_distances()    floor = 1.0 km
  → apply_quality_caps()         ceiling = long_run * 0.85, phys cap
    → build_workout_for_type()   distance assigned to workout
      → _apply_time_based()      if distance < threshold: overwrite
                                 distance = compute_from_steps(25-min steps)
        → _scale_down()           non-time-based scaled to fit total_km * 1.03
        → _fill_shortfall()       non-time-based expanded if total < 0.97
```

Threshold for tempo/interval/hill is **2.0 km**, for easy/long is **3.0 km**.
A 25-minute easy/long step at default E pace re-computes to roughly **4–5 km**.

### The two failure modes

**Inflation (the common case):** Easies on a low-base 5K plan get planned at
1.5–2.0 km each. `_apply_time_based` fires, each easy bumps to ~2.5 km. The
weekly total now exceeds target by 3–5 km. `_scale_down` compresses the
non-time-based workouts (typically the long run) to compensate. The long
run ends up unrealistically short.

**Floor-vs-cap collision (P3):** Quality floor at 2.0 km. For a low-base 5K
plan with `long_run ≈ 2.5 km`, the cap is `2.5 * 0.85 = 2.13`. Multiplied by
the per-type physiological cap, effective cap can be ~1.5 km. Quality is set
to 1.5 km, falls below the 2.0 km time-based threshold anyway, time-based
fires, distance balloons. Same inflation as above.

### Why the naive scale-down exclusion failed

```python
# What I tried in _scale_down:
scalable_actual = actual_total - time_based_km
scalable_target = total_km - time_based_km
scale = scalable_target / scalable_actual
```

This says "non-time-based workouts must total `target - time_based`," which
implicitly forces the non-time-based portion to absorb 100% of the time-based
overshoot. Concretely: if 4 easies × 2.5 km go time-based on a 12.1 km target,
`scalable_target = 2.1`, `scalable_actual = 4.2`, the long collapses to 2.1 km.

---

## 2. Design Choice

Three viable strategies. We are recommending **Strategy B + a quality-slot
demotion rule** because it preserves budget integrity with the smallest
behavior change and lets the UI keep showing duration-based workouts as
duration-based.

### Strategy A — Cap recomputed distance at threshold

In `_apply_time_based`, after recomputing from steps, clamp:
```python
workout['distance'] = min(recomputed, threshold)
```
- ✅ Trivial.
- ❌ Misleading: steps say 25 min (≈ 5 km of running), distance reports 2 km.
  Volume tracking, ACWR, and progression all under-count what the runner
  actually does. This silently breaks adaptation accounting.

### Strategy B — Preserve planned distance; treat steps as authoritative for time

In `_apply_time_based`, do not overwrite `workout['distance']`. The original
planned distance was already a reasonable budget allocation; the time-based
fallback only changes *how* the workout is described and stepped, not how
much volume it represents to the planner.

```python
def _apply_time_based(workout, pace_zones=None):
    wtype = workout.get('type', '')
    dist = workout.get('distance', 0)
    threshold = _TIME_THRESHOLD.get(wtype)
    if threshold is None or dist >= threshold:
        return workout
    dur = _MIN_DURATION[wtype]
    workout['duration_min'] = dur
    if wtype in descs:
        workout['description'] = descs[wtype]
    workout['steps'] = _time_based_steps(wtype, dur, pace_zones)
    # Do NOT recompute workout['distance'].
    return workout
```

- ✅ Budget remains exactly what the planner allocated.
- ✅ `_scale_down` / `_fill_shortfall` reasoning stays correct.
- ✅ Adaptation/volume tracking sees the planned number.
- ❌ Inconsistency between step contents (25 min ≈ 5 km @ E) and
  reported distance (e.g., 1.5 km). UI must be inspected: does it show
  duration when `duration_min` is set, or does it surface both? Most plan
  views render duration-based workouts as "25 min" without computing distance.

### Strategy C — Track planned vs. actual separately

Add `workout['planned_distance']` (set before `_apply_time_based`) and
`workout['distance']` (post-time-based recompute). Use planned for budget,
actual for runner-facing display.

- ✅ Most accurate model.
- ❌ Touches every consumer (PDF, JSON storage, adaptation, UI). Risky for a
  bug fix.

---

## 3. Recommended Implementation (Strategy B + quality-slot demotion)

### Step 1 — Stop overwriting distance in `_apply_time_based`

`app/core/training/workout_builders.py:43`

Remove the line:
```python
workout['distance'] = round(workout_steps._compute_distance_from_steps(workout['steps']), 1)
```

Verify no consumer relies on the recomputed distance. Search:
```bash
rg "duration_min" app/   # find anything that branches on time-based
rg "_compute_distance_from_steps" app/
```
Expected consumers that need a duration-aware path:
- PDF/HTML rendering of workouts (should already prefer `duration_min`
  when set — confirm).
- Adaptation `compute_adjustment_signals` — see step 3.

### Step 2 — Audit & fix UI rendering

For each renderer (`templates/components/workout_card.html`,
`pdf_generator.py`, plan JSON serialization), confirm the rule:

> If `workout.duration_min` is set, display "{duration_min} min" and step
> contents; treat `workout.distance` as a planning estimate, not a runner
> instruction.

Add a Jinja macro `workout_volume(w)` that returns `"25 min"` when
`duration_min` is present, otherwise `"{distance} km"`. Replace direct
`{{ w.distance }}` in workout cards with that macro. Bound the change to the
display layer — all data structures stay the same.

### Step 3 — Adaptation accounting

`app/services/adaptation_service.py` (and any volume-ratio computation):
distance is still the right number to use for "planned km this week" because
under Strategy B it equals what the planner intended. Verify nothing
re-reads steps and substitutes a different value.

### Step 4 — Quality-slot demotion for tiny budgets

Even with budget integrity restored, a 1.5 km tempo with 25-min steps is a
poor user experience: the description says one thing, the runner does
another. For very low budgets, demote the quality slot to easy entirely.

`app/core/generators/weekly_plan_builder.py::generate_daily_workouts`, after
`apply_quality_caps`:

```python
DEMOTE_THRESHOLD = {'tempo': 2.0, 'interval': 2.0, 'hill': 2.0}
demoted = []
for qtype in ('tempo', 'interval', 'hill'):
    if quality_distances.get(qtype, 0) < DEMOTE_THRESHOLD[qtype]:
        demoted.append(qtype)
        quality_distances.pop(qtype, None)
# Move demoted slots to easy in `workout_types` before scheduling.
```

This requires running the demotion **before** `schedule_workout_types` so
the freed days get easy runs instead. Implementation: convert the
`distribution` dict in-place — for each demoted qtype, decrement
`distribution[qtype]` and increment `distribution['easy']`.

### Step 5 — Re-attempt P3 quality floor (optional)

Once Step 4 is in place, the floor question is moot: the only way quality
ends up below 2 km is if the planner chooses to schedule it at all, and
the demotion rule prevents that.

If a floor is still desired for documentation purposes, set it to the same
`DEMOTE_THRESHOLD` value so the floor and demotion threshold are linked in
one constant.

---

## 4. Test Strategy

### Existing coverage to re-verify

These tests previously broke under the naive fix and must pass after the
new approach:

```
tests/test_core/test_plan_full_coverage.py::TestMileageProgression::test_no_zero_distance_running_workouts
tests/test_core/test_plan_full_coverage.py::TestPlanGenerationAllCombinations::test_long_run_is_longest
tests/test_core/test_plan_validation.py::TestEasyNeverExceedsLongRun::test_easy_le_long
tests/test_core/test_plan_validation.py::TestQualityCapsHold::test_quality_le_long
tests/test_core/test_plan_validation.py::TestNoZeroDistanceRunningWorkouts::test_no_zero_runners
```

### New tests to add

1. **`test_time_based_preserves_planned_distance`** — Build a 5K, 10 km/wk,
   5-runs/wk plan. Find a week where easies trigger time-based. Assert
   `workout['distance']` equals the planner's allocation (≤ threshold) and
   `workout['duration_min'] == 20`.

2. **`test_low_budget_quality_demotion`** — Build a 5K, 5 km/wk, 5-runs/wk
   plan. Assert that no week contains an interval/tempo/hill workout with
   distance < 2 km. (Demoted slots became easies.)

3. **`test_weekly_total_within_tolerance`** — For all
   distance/weeks/base/runs combinations in
   `test_plan_full_coverage`, assert `0.95 * target ≤ actual ≤ 1.05 * target`.
   Currently, time-based inflation could push `actual` to 1.3× target on
   low-budget weeks. After the fix, this should hold.

4. **`test_render_time_based_workout`** — Smoke test the workout-card macro
   renders a time-based workout as "25 min" (not "5.0 km").

### Manual validation

Generate a plan via the UI for these edge cases and visually inspect:
- 5K, 5 km/wk, 5 runs/wk, 12 weeks (worst-case low budget)
- 10K, 10 km/wk, 5 runs/wk, 12 weeks
- Marathon, 30 km/wk, 6 runs/wk, 16 weeks (high-budget control)

---

## 5. Implementation Order & Time Estimate

| Step | Description                                       | Time   |
|------|---------------------------------------------------|--------|
| 1    | Remove distance overwrite in `_apply_time_based`  | 5 min  |
| 2    | Audit & fix UI rendering for time-based workouts  | 45 min |
| 3    | Verify adaptation accounting unchanged            | 20 min |
| 4    | Quality-slot demotion in `weekly_plan_builder`    | 30 min |
| 5    | Tests (3 new + verify existing)                   | 60 min |
| 6    | Manual UI validation + screenshot                 | 20 min |

**Total: ~3 hours.**

Sequence Step 1 + Step 4 in the same commit — they are coupled. Steps 2 and
3 are independent verifications. Step 5 confirms the whole bundle.

---

## 6. Risks & Open Questions

### Risk: silent UI regression

Strategy B relies on the UI consistently preferring `duration_min` over
`distance` for display. If any renderer shows "1.5 km easy" while the steps
say "20 min easy," runners will be confused. Step 2 mitigates this but
requires a careful audit.

### Risk: PDF generator

`app/core/export/pdf_generator.py` may format distance directly. Confirm the
PDF picks up duration-based formatting and existing PDF tests pass.

### Risk: stored plans

Plans persisted to SQLite as JSON include the post-`_apply_time_based`
distance. Existing rows will not retroactively change, but new plans will
have smaller `distance` values for time-based workouts. Confirm there is no
analytics/reporting that compares old vs. new plans on this axis.

### Open question: should `total_km` reflect planned or "real" volume?

`weekly_plan['total_km']` is the sum of `workout.distance`. Under Strategy B,
that sum is the planner's intent, not what the runner will actually cover.
For a low-base week with 4 time-based easies, the runner covers ~10 km of
actual road but the plan reports ~8 km. This is a feature, not a bug
(progression curves and ACWR computations stay clean), but it should be
documented.

### Open question: demotion threshold

`DEMOTE_THRESHOLD = 2.0` is a guess. Validate by inspecting the demoted
plans manually — is "easy 2 km + strides" preferable to "20 min hard
intervals" at this volume? Coaches may have an opinion.

---

## 7. Out-of-Scope / Follow-Ups

- Renaming `distance` to `planned_distance_km` or adding an
  `actual_distance_km` field is the cleanest long-term fix (Strategy C),
  but is a larger refactor and best done after this lands.
- Reviewing `MAX_QUALITY_VS_LONG_RUN = 0.85` — for low-base plans the
  ceiling alone produces sub-threshold quality even before time-based fires.
  Demotion sidesteps the issue, but the cap itself may be too aggressive.
- The `_fill_shortfall` "expand non-time-based" logic still inflates easy
  runs to absorb deficits caused by capping. With Strategy B + demotion
  the deficits are smaller, but the expansion math still deserves a review
  pass once this fix lands.
