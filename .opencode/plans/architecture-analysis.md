# RunCoach — Architecture Analysis & Improvement Plan

## 1. Plan Generation Flow

### Entry Points

| Plan Type | Endpoint | Generator | File |
|-----------|----------|-----------|------|
| Distance | `POST /generate-plan` | `TrainingPlanGenerator` | `app/core/generators/plan_generator.py:244` |
| Performance | `POST /generate-plan` with `plan_mode="time"` | `PerformancePlanGenerator` | `app/core/generators/performance_plan_generator.py` |
| Fitness | `POST /generate-fitness-plan` | `FitnessPlanGenerator` | `app/core/generators/fitness_plan_generator.py` |
| Beginner (0km, 5K/10K) | Sub-path of Distance | `BeginnerPlanGenerator` | `app/core/generators/beginner_plan_generator.py` |
| Triathlon | `POST /api/triathlon/generate-plan` | Static data lookup | `app/core/generators/triathlon_plan_generator.py` |

### Distance Plan Pipeline (main path)

```
POST /generate-plan (PlanRequest)
  └─ PlanService.create_plan()
       └─ TrainingPlanGenerator.generate_plan()          # plan_generator.py:244
            ├─ [if current_km == 0] → BeginnerPlanGenerator
            ├─ VDOTCalculator.get_pace_zones(vdot)       # vdot_calculator.py:238
            ├─ derive_experience_level(current_km)        # strength_plan.py
            ├─ calculate_weekly_progression()             # mileage_progression.py:250
            │    ├─ get_peak_mileage()                    # distance caps, VDOT adj, ACWR
            │    ├─ _progress_ramp_phase(base)            # linear ramp to 70% peak
            │    ├─ _progress_ramp_phase(build)           # linear ramp to 100% peak
            │    ├─ _progress_peak_phase()                # oscillation 0.97→0.98→0.99
            │    └─ _progress_taper_phase()               # distance-specific curves
            └─ for each week:
                 └─ build_weekly_plan()                   # weekly_plan_builder.py:224
                      ├─ calculate_phases()               # phase_calculator.py:76
                      ├─ get_phase() / is_recovery_week()
                      ├─ get_workout_distribution()       # workout_distribution.py:15
                      │    ├─ quality count by phase      # base:0-1, build:1-2, peak:2
                      │    ├─ profile selection           # road_5k, road_marathon, trail_hilly...
                      │    └─ _build_quality_distribution # type assignment per profile
                      ├─ schedule_workout_types()         # week_scheduler.py:9
                      │    └─ day 2=recovery, day 6=long, days 3-5=quality
                      ├─ calculate_long_run_distance()    # long_run_calculator.py:146
                      │    └─ ratio by phase/distance, experience caps, week-1 nudge
                      ├─ calculate_quality_distances()    # long_run_calculator.py:216
                      │    └─ remaining_km × phase_dist_pct
                      ├─ apply_quality_caps()             # weekly_plan_builder.py:27
                      ├─ allocate_easy_distances()        # even split of remaining budget
                      └─ for each day:
                           ├─ build_workout_for_type()    # workout_builders.py
                           ├─ overlay_key_workout()       # key_workout_library.py:381
                           ├─ generate_strength_session()
                           └─ generate_coaching_note()
                      ├─ _scale_down()                    # if actual > target × 1.03
                      └─ _fill_shortfall()                # expand easy/long to hit target
```

### Key Workout Slotting

**Selection** (`key_workout_library.py:449-496`):
- Filters `_WORKOUTS` by: `target_distance`, `phase`, `workout_type`, `terrain`
- Rotates through candidates: `candidates[week_in_phase % len(candidates)]`
- Only applies in `build` and `peak` phases

**Overlay** (`key_workout_library.py:381-443`):
1. Guard: only for interval/tempo/hill/long types, build/peak phases, no `duration_min` set
2. Selects key workout via `KeyWorkoutLibrary.get_for_phase()`
3. Injects VDOT paces if available
4. Rewrites description using `_DISTANCE_REWRITES[workout_id](actual_distance)`
5. Sets `key_workout_id`, `key_workout_name`, `structure`, `key_workout_rationale`
6. Generates steps from: pre-defined `steps` → `steps_builder` → parsed `structure`

**Workout Inventory by Distance:**

| Distance | Key Workouts | Types |
|----------|-------------|-------|
| 5K (6) | vo2max_400s, race_pace_3km, cruise_intervals, threshold_run, hill_sprints, pyramid | interval, tempo, hill |
| 10K (5) | cruise_intervals, goal_pace_segments, tempo_progression, fartlek, long_fast_finish | tempo, interval, long |
| Half (7) | progressive_long, threshold_cruise, race_pace_segments, cutdown_long, long_alternating_mp, long_fast_finish, long_rolling_hills | tempo, interval, long |
| Marathon (10) | mp_long, yasso_800s, progressive_long, tempo_cutdown, mp_cutdown, easy_long_fueling, peak_progressive, long_alternating_mp, long_fast_finish, long_depletion, long_rolling_hills | tempo, interval, long |
| Trail 30K Hilly (9) | elevation_repeats, time_on_feet, technical_terrain, power_hike, back_to_back, downhill_technique, long_fast_finish, long_rolling_hills, long_race_simulation | hill, tempo, interval, long |
| Trail 30K Flat (7) | surge_fartlek, soft_surface, power_walk, proprioception, long_fast_finish, long_fueling, long_race_sim | tempo, interval, long |

### Adaptation Flow

```
POST /api/runs
  ├─ Compute pace = duration / distance
  ├─ Quality score (quality_scorer.py:37) — effort 40% + pace 60% vs planned
  ├─ VDOT enrichment (vdot_calculator.py:82) — Daniels' formula, clamped [25,85]
  ├─ FeedbackService.generate_and_store()
  │    ├─ pace_feedback()      — actual vs planned pace, type-specific tolerances
  │    ├─ hr_zone_feedback()   — HR zone vs target, 2+ zones above = warning
  │    ├─ effort_feedback()    — quality score narrative
  │    ├─ volume_feedback()    — weekly km progress
  │    └─ pattern_feedback()   — repeated deviations over 45-day window
  └─ AdaptationService.evaluate_recommendation()
       ├─ gather_signals()
       │    ├─ map_runs_to_plan()           — retroactively link runs to workouts
       │    ├─ compute_adjustment_signals() — 5 weighted signals:
       │    │    ├─ volume_ratio             — recency-weighted actual/planned
       │    │    ├─ effort_factor            — avg perceived effort trend
       │    │    ├─ completion_factor        — workout completion rate
       │    │    ├─ hr_zone_factor           — HR zone adherence
       │    │    └─ feedback_factor          — sentiment aggregation
       │    ├─ overreach detection           — cap multiplier if overtraining
       │    └─ VDOT trend                    — improving/stable/declining
       └─ Store pending_recommendation on TrainingPlan
            └─ User accepts → apply_adjustment_to_future_weeks()
                 ├─ Per-type multipliers (clamped [0.85, 1.15])
                 ├─ Long run protection (not reduced)
                 ├─ Quality workout dampening (half the volume change)
                 └─ VDOT recalibration (if delta >= 1.0)
```

---

## 2. Grading

### Correctness: C+ (65/100)

Do distances sum up correctly? Mostly, but with notable exceptions:
- The `_scale_down` and `_fill_shortfall` mechanisms attempt to reconcile budgets but `_apply_time_based` can break this by recalculating distances from steps
- Hardcoded key workout descriptions describe distances that exceed the assigned budget
- Quality distance allocation with 1.0km floor can trigger time-based fallback that further drifts

Are distances per key workout correct? No — several workouts have hardcoded rep counts that don't scale with the assigned distance budget.

Do descriptions match? Partially — `_DISTANCE_REWRITES` lambdas handle many cases but several are hardcoded or use fragile math.

### Effectiveness: B (78/100)

Are plans actually good? Yes, with caveats:
- Solid periodization with distance-appropriate phase splits
- 10% rule enforcement with high-water mark tracking
- Good key workout variety with terrain awareness
- Multi-signal adaptation engine with overreach detection
- Marathon peak long run capped at 36km (advanced) — acceptable but low side
- No explicit cutback week before the longest long run
- Performance and fitness generators duplicate logic instead of sharing core modules

### Ease of Use: B- (72/100)

- Clean FastAPI architecture with dependency injection
- Well-organized module separation
- Three separate plan generators with overlapping logic = maintenance burden
- `TrainingPlanGenerator` class is essentially a namespace wrapper (180+ lines of delegation)
- No API versioning, SQLite limits concurrency

---

## 3. Bugs & Improvements (Priority Order)

### P0 — Crash Bug: FlatTrail KeyError

**File:** `app/core/training/phase_calculator.py:109`
**Issue:** When `terrain='flat'` and `target_distance=30.0`, `get_distance_category()` returns `'FlatTrail'` but `phase_profiles` dict has no `'FlatTrail'` key → `KeyError`
**Fix:** Add `'FlatTrail': {'base_pct': 0.35, 'build_pct': 0.35, 'peak_pct': 0.15, 'taper': 2}` to `phase_profiles` at line 101-107

### P1 — Distance Integrity: Hardcoded Key Workouts

**File:** `app/core/training/key_workout_library.py:42-45`
**Issue:** `5k_vo2max_400s` always says "10-12 x 400m" regardless of actual distance. If assigned 4km, the described workout needs ~8.8km (4.8km work + 4km warmup/cooldown).

**File:** `app/core/training/key_workout_library.py:59-62`
**Issue:** `5k_pyramid` hardcodes 3.2km of work + warmup/cooldown = ~7.2km minimum. Will exceed budget for low-volume weeks.

**Fix:** Scale rep counts to fit distance `d` in the rewrite lambdas, or add a guard that falls back to generic description when budget is too small.

### P1 — Distance Drift: _apply_time_based Overwrites Distance

**File:** `app/core/training/workout_builders.py:43`
**Issue:** When workouts fall below time threshold, `_apply_time_based()` recalculates distance from steps, breaking the weekly km budget. The `_fill_shortfall` mechanism tries to compensate but this creates oscillation.
**Fix:** Either adjust the week total after this happens, or have `_fill_shortfall` account for time-based distance changes explicitly.

### P2 — Logic Bug: Distribution Goes Negative

**File:** `app/core/training/week_scheduler.py:19-20`
**Issue:** `distribution['long'] -= 1` after hardcoding `workout_types[5] = 'long'`. If `distribution['long']` is already 0 (e.g., edge case with 2-run week), this goes negative. The 2-run special case at lines 39-43 handles easy runs but not this scenario.
**Fix:** Add guard: `if distribution['long'] > 0: distribution['long'] -= 1`

### P2 — Trail Distance Categorization Too Broad

**File:** `app/core/training/phase_calculator.py:68-71`
**Issue:** `target_distance <= 30.0` with `terrain != 'flat'` returns `'Trail'`. A 25km road race with no terrain specified would be categorized as Trail.
**Fix:** Trail should require `target_distance == 30.0` explicitly, or add a road category for 21.1-30km range.

### P3 — Architecture: TrainingPlanGenerator is a Namespace Wrapper

**File:** `app/core/generators/plan_generator.py:58-240`
**Issue:** ~180 lines of delegation methods that just call module-level functions. No state, no behavior, no value added.
**Fix:** Flatten to module-level functions or use a dataclass + single `generate_plan` method.

### P3 — Duplicated Logic Across Generators

**Issue:** Performance and Fitness generators duplicate phase calculation, mileage progression, and VDOT logic instead of sharing the core modules.
**Fix:** Extract shared logic into composable functions that all three generators call.

### P3 — Quality Distance Floor Too Low

**File:** `app/core/training/long_run_calculator.py:237`
**Issue:** `max(dist, 1.0)` means a quality workout can be 1.0km, below the 2.0km threshold for interval/tempo, triggering time-based fallback that overwrites the distance.
**Fix:** Raise floor to 2.0km or adjust `_TIME_THRESHOLD` to handle this case.

### P4 — Marathon mp_cutdown Description Math Fragile

**File:** `app/core/training/key_workout_library.py:89-94`
**Issue:** The rep count formula `round(max(2, d - 2 * max(1, d * 0.10)) / 2)` produces non-intuitive results. For d=10km: "4 x 2km" = 8km work + 2km warmup/cooldown = 10km. Works but fragile.
**Fix:** Simplify to explicit rep count based on distance ranges.

---

## 4. Recommended Implementation Order

1. **Fix P0 FlatTrail KeyError** — 5 min, single line addition
2. **Fix P1 hardcoded key workouts** — 30 min, update rewrite lambdas for 5k_vo2max_400s and 5k_pyramid
3. **Fix P2 distribution negative** — 5 min, add guard in week_scheduler
4. **Fix P1 distance drift** — 45 min, reconcile _apply_time_based with budget system
5. **Fix P2 trail categorization** — 15 min, tighten distance category logic
6. **Fix P3 quality floor** — 10 min, raise floor to 2.0km
7. **Refactor TrainingPlanGenerator** — 2 hrs, flatten delegation methods
8. **Deduplicate generator logic** — 4 hrs, extract shared phase/mileage/VDOT functions
