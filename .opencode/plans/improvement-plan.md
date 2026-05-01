# RunCoach Improvement Plan

> Synthesized from three parallel audits: maintainability/readability, duplication/complexity, and deep plan-engine analysis.
> Generated: 2026-05-01

---

## Priority 1 — Critical Bugs (fix before next release)

### P1-A: Phase collapse on short plans
**File:** `app/core/training/phase_calculator.py` ~lines 91–132

Plans shorter than ~6 weeks can produce `peak = 0` weeks, silently breaking the phase model. The minimum-phase enforcement (`base >= 2`) pulls weeks from other phases without checking whether `peak` collapses to zero.

**Fix:** Add explicit guard at the top of `calculate_phases()`:
```python
if weeks < MIN_WEEKS_FOR_PHASES:  # define as 6
    raise InsufficientTimeException(
        f"Minimum {MIN_WEEKS_FOR_PHASES} weeks required for structured periodization."
    )
```

---

### P1-B: Detraining for high-base runners
**File:** `app/core/training/mileage_progression.py` ~lines 90–125

A runner starting at 70 km/week training for a 5 K gets `peak = 40 km` — a 43% cut held for the entire plan. The code detects `current_km >= peak_km` and comments "hold steady," but holding at 40 km is still aggressive detraining.

**Fix:** Cap any downward adjustment to 10% below current base:
```python
if current_km > ideal_peak:
    peak_km = max(current_km * 0.90, ideal_peak)
```

---

### P1-C: Recovery-week assignment uses absolute week number
**File:** `app/core/training/phase_calculator.py` ~lines 151–173

Recovery weeks are inserted when `week_number % 4 == 0`. If a phase starts mid-plan, this clusters or skips recovery entirely for irregular phase lengths.

**Fix:** Use week-in-phase, not global week:
```python
week_in_phase = week_number - phase_start_week
if week_in_phase > 0 and week_in_phase % 4 == 0:
    return True
```

---

### P1-D: Interval intensity threshold uses weekly volume, not fitness proxy
**File:** `app/core/training/workout_builders.py` ~lines 250–327

`generate_interval_run()` gates 1000 m repeats on `total_km >= 40` (weekly volume), but a runner ramping quickly could hit that threshold in week 8 without adequate base. There's no assessment of cumulative readiness.

**Fix:** Add a 4-week rolling volume check before prescribing 1000 m repeats, or raise the threshold and document the reasoning.

---

## Priority 2 — High-Impact Refactors

### P2-A: Extract duplicated segment builders
**Files:** `app/core/generators/fitness_workout_builders.py` lines 9–38 and `app/core/generators/performance_workout_builders.py` lines 8–30, 109–130

`_warmup_segment()`, `_cooldown_segment()`, and `estimate_duration_min()` are copy-pasted verbatim between both workout builder modules.

**Fix:** Create `app/core/generators/segment_builders.py` with these three functions. Both modules import from there. Eliminates ~40 lines of duplication.

---

### P2-B: Extract duplicated spacing logic
**Files:** `app/core/generators/fitness_plan_generator.py` lines 341–359 and `app/core/generators/performance_plan_generator.py` lines 279–297

`_spacing_score()` and `_would_create_three_consecutive()` are identical nested helpers in both `_generate_weekly_plan()` implementations.

**Fix:** Extract to `app/core/training/workout_scheduling.py` and import in both generators. Eliminates ~20 lines of duplication.

---

### P2-C: Unify the two workout builder modules
**Files:** `app/core/generators/fitness_workout_builders.py` (417 lines) and `app/core/generators/performance_workout_builders.py` (436 lines)

~80% of workout types (`generate_tempo_workout`, `generate_vo2max_workout`, `generate_fartlek_workout`, `generate_easy_run`, `generate_long_run`) are near-identical. Only a handful of methods are truly distinct per generator.

**Fix:** Merge into `app/core/generators/workout_builders_unified.py`. Use the shared `segment_builders.py` (from P2-A) as the foundation. Add generator-specific extensions via parameters or a strategy object. Estimated savings: 150–200 lines.

---

### P2-D: Extract `BasePlanGenerator` abstract class
**Files:** All four generators (beginner, fitness, performance, triathlon)

All four generators share: `calculate_training_zones()`, delegation to `phase_calculator` and `mileage_progression`, `daily_workouts` construction, quality caps, coaching notes, and the same `plan_data` return schema.

**Fix:** Create `app/core/generators/base_plan_generator.py`:
```python
class BasePlanGenerator(ABC):
    @abstractmethod
    def _generate_weekly_plan(self, week_number, phase, weekly_km, ...) -> list: ...
    def calculate_training_zones(self, ...) -> dict: ...  # shared impl
    def _apply_coaching_notes(self, weeks) -> None: ...   # shared impl
    def generate_plan(self, ...) -> dict: ...             # orchestrator
```
Each generator only overrides `_generate_weekly_plan()` and any truly unique logic. Eliminates the parallel hierarchy.

---

### P2-E: Consolidate `_generate_weekly_plan` scaffolding
**Files:** `fitness_plan_generator.py` lines 267–413, `performance_plan_generator.py` lines 219–355

~90% of these two methods is identical: long run on day 6, quality workouts on Tue/Fri, easy run gap-fill with spacing logic, remaining km distribution.

**Fix:** Implement as part of P2-D's base class, with two override points:
1. `_get_quality_generators(phase)` → returns the dict of quality workout generators (the 10% that differs)
2. `_post_process_week(week)` → for performance's `enforce_week_caps()` / `reconcile_workout_after_cap()`

---

### P2-F: Replace magic numbers with named constants
**Files:** `mileage_progression.py`, `phase_calculator.py`, `vdot_calculator.py`, `workout_distribution.py`, `pace_feedback.py`

Scattered hardcoded values with no explanation:
- `1.5, 1.6, 1.85, 2.0` peak multipliers in `mileage_progression.py` lines 72–80
- `1, 1.5, 16, 2.6` in the peak multiplier formula (lines 101–102)
- Phase percentages `35%, 30%, 15%` in `phase_calculator.py` lines 91–101
- VDOT formula coefficients `-4.60, 0.182258, 0.000104` in `vdot_calculator.py` lines 26–31

**Fix:** Define as module-level constants with a comment citing the physiological/mathematical source. For VDOT: cite Daniels' Running Formula.

---

### P2-G: Move business logic out of route handlers
**Files:** `app/routers/plan_generation.py`, `app/routers/runs.py`

Route handlers directly call `calculate_quality_score()`, build plan parameters, and branch on `time_goal` vs `distance_goal` — all business logic that belongs in services.

**Fix:**
- Create `PlanGenerationOrchestrator` in `app/services/` to handle the full generate-save-redirect flow. Router just calls it and returns the response.
- Create `RunScoreService.compute_run_quality(run_data) -> QualityScore` in `app/services/`. Router calls it and stores the result.

---

## Priority 3 — Plan Engine & Science

### P3-A: Strengthen the adaptation engine
**File:** `app/services/adaptation/plan_adjuster.py`, `app/services/adaptation/signal_computer.py`

The current adaptation only scales future workout distances by a single multiplier (capped at ±15–25%). It cannot reorder phases, swap workout types mid-plan, or detect ACWR overreach before it manifests.

**Specific issues:**
- `effort_factor` maps raw RPE linearly with no drift correction — a runner who consistently underreports effort gets systematically under-adjusted
- Volume ratio ignores workout-type distribution: completing 100% of volume doing only easy runs gets full credit
- `vdot_trend == "declining"` is logged but doesn't feed back into the multiplier

**Recommended additions (in order):**
1. Track ACWR (acute 7-day / chronic 28-day load ratio). Alert and reduce load when ratio > 1.5.
2. Add per-type completion tracking. If tempo completion < 60% for 2+ weeks, swap to a more achievable quality format instead of just scaling down distance.
3. Correct effort drift: normalize RPE against the runner's own distribution (z-score), not the absolute 1–10 scale.
4. Feed `vdot_trend == "declining"` into a 5% multiplier reduction (not just a log message).

---

### P3-B: Implement race-week sharpening
**Files:** `app/core/training/key_workout_library.py`, generator files

Taper weeks reduce volume but no system generates a race-pace sharpening session in the final 3–4 days before race day (e.g., "4 × 200 m at 5 K pace" on Thursday before Sunday race). Daniels and Pfitzinger both prescribe this.

**Fix:** Add `race_week_sharpener(target_distance, vdot)` in `key_workout_library.py`, injected into the penultimate workout slot of the final plan week.

---

### P3-C: Validate generated workouts against VDOT paces
**Files:** `app/core/training/vdot_calculator.py` lines 238–267, `app/core/training/workout_builders.py`

`inject_paces_into_description()` uses regex to replace pace references but only matches exact strings like "5K pace" or "threshold pace". Variations like "fast-but-controlled" are silently missed.

**Fix:**
1. Expand regex patterns to catch common pace-zone aliases.
2. Add a post-injection validation pass: log at DEBUG if a quality workout description contains no pace reference.

---

### P3-D: Fix 24-week plan phase imbalance
**File:** `app/core/training/phase_calculator.py` lines 112–132

The while-loop rebalancing dumps all extra weeks into `build`, producing plans like `base=2, build=15, peak=4, taper=3` for a 24-week marathon plan.

**Fix:** Apply proportional redistribution with a cap on build phase:
```python
deficit = target_weeks - sum(phases.values())
# Distribute proportionally, cap build at max(10, int(total_weeks * 0.40))
```

---

### P3-E: Add beginner graduation pathway
**File:** `app/core/generators/beginner_plan_generator.py`

The Couch-to-5K plan is entirely disconnected from the main system: hardcoded run/walk ratios, no VDOT, no phase model, no transition path to a standard plan.

**Fix:**
1. At the end of the beginner plan, estimate VDOT from the final continuous run pace.
2. Expose `graduate_to_standard_plan()` that generates a standard 5 K plan seeded with that VDOT and the final beginner week's mileage.

---

### P3-F: Load balancing within the training week
**Files:** `performance_plan_generator.py` lines 219–355, `fitness_plan_generator.py` lines 267–413

Day assignments are hard-coded (long run day 6, quality days 2 and 5). No check that quality workouts are ≥ 48 h apart or that cumulative load doesn't spike mid-week.

**Fix:**
1. Accept optional `rest_day: int` input (0=Mon … 6=Sun).
2. Enforce minimum 48 h between quality sessions before assigning days.
3. Expose as a plan customization parameter in the form/API.

---

## Priority 4 — Missing Capabilities (Roadmap)

| Capability | Description | Complexity |
|---|---|---|
| **ACWR tracking** | Compute acute (7-day) / chronic (28-day) workload ratio. Alert when > 1.5. | Medium |
| **Readiness scoring** | Use RHR, sleep quality, perceived wellness to suggest workout downgrades. | High |
| **Injury risk model** | Track cumulative impact load; flag 3+ consecutive hard weeks. | High |
| **Stochastic workout variation** | Randomize within workout type per week instead of deterministic cycling. | Low |
| **Race simulation** | Predict finish time at taper start; validate taper adequacy. | Medium |
| **Strength training progression** | Model sets/reps growth over phases; account for running load. | Medium |
| **Cross-training load accounting** | When swim/bike is logged, reduce easy-day running volume proportionally. | Medium |
| **Block periodization** | Support 3-week accumulation + 1-week realization micro-cycles explicitly. | High |

---

## Housekeeping

### Dead code to remove
- `workout_types` dict in `TrainingPlanGenerator.__init__` (`plan_generator.py` lines 48–56) — initialized, never used
- `PHASE_DISTRIBUTIONS` re-export at module level (`plan_generator.py` line 37) — replace with explicit import at call site or document the backward-compat reason

### Files to consolidate
- `triathlon_plan_data.py` + `triathlon_plan_data_70_3.py` → merge under a `DISTANCES` dict key
- `key_workout_data.py` + `key_workout_data_long.py` → merge under distance-keyed structure or add a `distance_tag` field to a single flat list

### Type-hint gaps (quick wins)
- `app/services/plan_service.py`: all delegation methods missing return types
- `app/core/training/workout_builders.py`: `_apply_time_based()` and `_time_based_steps()` missing return types
- `app/core/coaching/pattern_analyzer.py`: function params missing `RunLog` and `Session` types
- `app/core/training/mileage_progression.py`: `_acwr_peak_factor()` and `_volume_trend_cap()` — document expected dict keys with `TypedDict`

### Error handling gaps
- Replace bare `except Exception` in `fitness_service.py` line 70 with logging + typed re-raise
- In `plan_generation.py`, catch `PlanGenerationException` and `ValidationException` separately to return appropriate user-facing messages
- Wrap `float(target_distance)` Form conversion in a try/except with a `ValidationException`

---

## Effort Estimates

| Priority | Items | Estimated effort |
|---|---|---|
| P1 — Critical bugs | 4 items | ~1 day |
| P2 — High-impact refactors | 7 items | ~3–4 days |
| P3 — Plan engine & science | 6 items | ~4–5 days |
| P4 — New capabilities | 8 items | 2–4 weeks |
| Housekeeping | ~10 items | ~0.5 day |
