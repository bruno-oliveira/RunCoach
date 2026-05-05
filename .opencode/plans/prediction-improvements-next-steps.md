# Prediction-quality improvements — deferred next steps

Context: after `use-running-data-investigation.md`, we shipped fixes E1–E5 (elevation/trail handling) and A+B (endurance calibration + VDOT outlier filter). The two items below were identified during that work and deferred — they're more invasive but would close real remaining gaps.

---

## C — Non-linear elevation penalty + per-run terrain factor

### Why this matters

The current trail elevation penalty is linear: `1.2 sec per meter of gain` (mirrors `RacePacingService`'s 12 sec/km/% grade rule, integrated). This works for moderate rolling courses but underestimates two things:

1. **Steep grades.** Penalty per % grade is constant. In reality, climbs above ~8 % grade slow runners super-linearly because they cross the threshold from "running uphill" to "power hiking" (vertical speed roughly caps at 800–1000 m/h regardless of horizontal pace). The linear model assumes you can keep adding horizontal speed cost as grade climbs, but you can't — you stop running.
2. **Technical terrain.** Two trails with identical elevation profiles can take wildly different times depending on surface (paved bike path vs. rocky single-track with roots and stream crossings). Elevation alone doesn't capture footing complexity.

For the user's 22.3 km / 1000 m race: linear elevation + trail-inexperience pushes the prediction from 2:29 to ~2:38; actual was 4:05. The remaining ~1:30 gap is plausibly half steepness, half technical terrain.

### Approach (sketch)

**Non-linear grade penalty** — replace the constant `UPHILL_PENALTY_SEC_PER_KM_PER_PCT = 12` with a piecewise function:

```
grade_pct < 4   ->  12 sec/km/%   (current)
4 <= grade < 8  ->  16 sec/km/%
8 <= grade < 12 ->  24 sec/km/%
grade >= 12     ->  35 sec/km/%   (effectively power-hiking)
```

This requires per-segment grade data, not just total elevation gain. Two implementation paths:

- **Path A (cheap):** when only `elevation_gain_m` and `distance_km` are known (current case for most runs), assume the climb is concentrated in 50 % of the distance at 2× the average grade. Apply the piecewise function to that estimate. Crude but better than the flat-grade integral.
- **Path B (right):** require GPX upload (already supported via race-prep flow). Use per-segment grades. Replace the prediction pipeline so all trail predictions go through `RacePacingService` regardless of entry point. This is the doc's "longer-term fix #6" (unify the two prediction pipelines).

**Terrain factor** — add a `terrain_factor` field on `RunLog` (and a UI affordance to set it):

```
1.00  paved (default)
1.10  smooth dirt / fire road
1.25  trail with roots/rocks
1.45  technical single-track / scree / scrambling
```

Apply as a multiplier after elevation but before trail-inexperience. For Strava-imported runs, default to 1.0 (we have no signal). Allow auto-bumping the terrain factor when actual run pace is significantly slower than the elevation-adjusted prediction over multiple runs on similar courses (i.e., the user reveals their typical terrain difficulty by what they consistently run).

### Files likely touched

- `app/core/training/race_predictor.py` — replace `_UPHILL_PENALTY_SEC_PER_M_GAIN`, accept optional `avg_grade_pct` and `terrain_factor`.
- `app/services/fitness/race_pacing_service.py` — extend with the piecewise grade function; consider becoming the single prediction engine.
- `app/models/run_log.py` + Alembic migration — add `terrain_factor` column.
- `app/services/runs/run_enrichment_service.py` — pass terrain into the prediction snapshot.
- `app/templates/components/workout_card.html` (or run-log editor) — UI for setting terrain.

### Risk / scope

- Tuning the piecewise penalty requires a sanity-check dataset. Small starting sample is OK; iterate from there.
- Adding a new column has a migration cost. Default it to 1.0 so existing predictions are unchanged.
- The "auto-bump terrain factor" idea is feedback-loop-shaped — get the manual version working first.

---

## D — Auto-classify race-effort runs from pace + HR + perceived effort

### Why this matters

`_EFFORT_TYPE_WEIGHT` in `race_predictor_service.py` weights candidates by `workout_type` — `race=1.5`, `interval=1.3`, `tempo=1.2`, `easy=0.7`. The intent is good: race / interval VDOTs are more reliable signals of fitness than easy-pace VDOTs.

In practice this signal is dead for most users. `workout_type` is set:
- Manually when the user logs a run via the in-app form (rarely a race tag)
- From Strava's `workout_type` field, which is 0 (default = easy) for ~99 % of activities because almost no Strava users tag their workouts.

For the user we investigated, **all 37 runs in the last 12 weeks are tagged `easy`**. The weighting is a no-op — every candidate has effort_weight 0.7.

This means the system can't distinguish a 5K time-trial from a Sunday easy run, which is the exact distinction VDOT estimation cares most about.

### Approach (sketch)

Detect "this was a race-effort run" from observable signals, ignoring the unreliable `workout_type` tag:

1. **Pace deviation vs. user's distribution.** For each new run, compute the pace as a percentile against the user's pace distribution at similar distance (within ±50 % km). Top 10 % at distance → classify as `race_effort`. Top 25 % → `tempo_effort`.
2. **HR ceiling proximity.** If `avg_heart_rate >= 0.92 * max_hr` (where max_hr comes from user profile or estimated) → boost effort confidence regardless of pace.
3. **Perceived effort.** When set, `perceived_effort >= 8` is a strong signal. Already partially used (`pe_multiplier = 1.2 if pe >= 7`), but classification should be stronger: PE ≥ 9 unconditionally → `race_effort`.
4. **Combine into a derived `effort_class`** stored on RunLog (separate from the user-tagged `workout_type` so we don't overwrite their input). Use `effort_class` in the VDOT weighting.

### Files likely touched

- `app/models/run_log.py` + migration — add `effort_class` column.
- `app/services/fitness/effort_classifier.py` (new) — the classification logic, taking a run + the user's distribution.
- `app/services/runs/run_enrichment_service.py` — call the classifier when ingesting a run (manual + Strava).
- `app/services/fitness/race_predictor_service.py` — replace `_EFFORT_TYPE_WEIGHT.get(workout_type, ...)` with `effort_class` lookup; keep `workout_type` as a fallback when `effort_class` is unset.
- Backfill migration to classify existing runs.

### Risk / scope

- Classification needs at least ~5 prior runs at similar distance to be meaningful. New users fall back to the current `workout_type` weighting.
- Heart-rate signal requires `max_heart_rate` to be set or estimated — most users don't enter it. Default to age-based estimate when missing (220 − age), but age isn't currently stored either, so this signal is probably unavailable for most users until profile fields expand.
- The pace-percentile classifier risks classifying a runner's first hard 10K as "race effort" when in fact they have no prior 10Ks — guard with the minimum-sample rule.

### Why D is lower priority than C for the trail-prediction problem

D improves the *VDOT estimate itself*. C improves *what we do with the VDOT* for trail/technical races. The trail-prediction gap we observed (2:29 → 4:05) was almost entirely a "what we do with VDOT" problem; the VDOT itself was reasonable (~31 from real flat 5Ks at 25:30). So C is the bigger lever for trail accuracy, and D is the bigger lever for *general* prediction accuracy across all users.

---

## Suggested order of work

1. **C path A first** (piecewise grade, no GPX requirement, no schema change). Tunable, low-risk, immediate benefit for any user with `elevation_gain_m` on their runs. Validate with a handful of known trail-race outcomes before tuning aggressively.
2. **D**, scoped to the pace-percentile signal (HR/age dependencies are too sparse). One new column, one new module, deterministic.
3. **C path B** (unify pipelines through `RacePacingService`). Larger refactor; do it after C path A has validated the steepness model.
