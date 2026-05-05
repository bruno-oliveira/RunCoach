# RunCoach Plan Quality Report

**Date**: April 29, 2026
**Scope**: Plan generation (all variants, distances, base mileages) and adaptation/adjustment flow
**Test Suite**: 32,382 tests, 100% passing

---

## Overall Grades

| System | Efficiency | Usability | Overall |
|--------|-----------|-----------|---------|
| Plan Generation | **A** | **A-** | **A** |
| Adaptation/Adjustment | **A** | **B+** | **A-** |

---

## Part 1: Plan Generation

### Architecture Grade: A

The plan generation system is well-decomposed into focused modules:

- **3 generators** (standard, beginner, performance) with clean entry points
- **7 training calculation modules** each owning a single responsibility (phases, mileage, distribution, workouts, long runs, key workouts, VDOT)
- **Facade pattern** — `TrainingPlanGenerator` delegates to sub-modules rather than accumulating logic
- **Validator layer** — Pydantic schemas catch invalid inputs before generation starts

### What Works Well

**1. Mileage Progression (mileage_progression.py)**

The progression engine is production-grade:

- 10% rule enforcement as a post-generation safety net with high-water mark tracking
- Phase-aware ramping: base→70% of peak, build→100%, peak oscillates (0.97-0.99), taper curves by distance
- Recovery weeks at 65% with high-water preservation (resume from pre-recovery level, not recovery level)
- VDOT-aware peak scaling (VDOT 30 → 0.95x, VDOT 65+ → 1.08x)
- ACWR risk adjustment (high risk → 15% reduction, very high → 25%)
- Max-runs distribution cap prevents impossible per-workout volumes for low-frequency runners

The peak mileage calculation is particularly well-tuned with distance-specific ideal peaks and caps:

| Distance | Ideal Peak Formula | Hard Cap |
|----------|--------------------|----------|
| 5K | max(20, current × 1.5) | 40 km |
| 10K | max(25, current × 1.6) | 50 km |
| Half | max(40, current × 1.85) | 65 km |
| Trail | max(35, current × 1.5) | 75 km |
| Marathon | max(55, current × 2.0) | 85 km |

**2. Phase Calculator (phase_calculator.py)**

Distance-specific phase proportions with distinct tuning per category:
- 5K: shorter build, longer peak (speed focus)
- Marathon: longer build, longer taper (endurance focus)
- Recovery week cadence changes by phase (every 4th in base/build, 3rd in peak)

**3. Workout Distribution (workout_distribution.py)**

Profile-aware quality allocation is a standout feature:
- Adjusts quality count based on hard-work ratio, easy-run ratio, and training history
- Detects gaps in training history (no speed work → tempo-focused base phase)
- Distance-specific quality rotation (5K: VO2max-heavy, Marathon: tempo-heavy, Trail: hill-heavy)

**4. Key Workout Library (key_workout_library.py)**

~20 curated race-specific workouts with:
- Distance rewriting (generates description scaled to actual workout distance)
- VDOT pace injection (replaces "5K pace" with "4:20/km (I-pace)")
- Phase filtering (only build/peak) and terrain awareness

**5. Workout Builders (workout_builders.py)**

Multiple variants per type that rotate by day — no two consecutive weeks feel identical:
- Long runs: conversational, race-pace finish, varied terrain
- Intervals: 400s, pyramids, hills, Yasso 800s, 1000m repeats
- Time-based fallback for very short distances (< 3 km → duration-based workout)

**6. Beginner Generator (beginner_plan_generator.py)**

Genuine Couch-to-5K progression (run/walk intervals) with compressed week sequences for shorter plans. The 10K extension adds duration-based progressive long runs.

**7. Performance Plan Generator (performance_plan_generator.py)**

5-zone training system with VDOT-driven pace zones, phase-quality mapping (30% base → 60% peak), and 3-consecutive-day prevention logic.

### Flagged Improvements

**P2 — Beginner pace assumption is hardcoded at 8.0 min/km**

The beginner generator uses a fixed 8.0 min/km pace for distance estimation. A fit beginner (e.g., cyclist starting running) might run at 6.0 min/km; an older beginner might be at 10+ min/km. The C25K structure (run/walk intervals) is correct regardless, but the estimated distances shown to users will be inaccurate.

*Impact*: Misleading distance estimates on the plan display for users far from the assumed pace.
*Suggestion*: Accept an optional estimated pace or derive from first logged run, then recompute distances.

**P3 — 10% rule enforcement is post-generation only**

The safety ceiling is applied after the full plan is generated, which means the mileage progression engine can produce weeks that get retroactively scaled down. The two systems can disagree:

```
Generated: Week 8 = 52 km (peak)
10% ceiling check: high-water = 44 km → ceiling = 48.4 km
Post-fix: Week 8 scaled to 48.4 km (all workouts proportionally reduced)
```

*Impact*: Post-fix scaling can create workout distances that don't match the workout description (e.g., a "20 km long run" description with an 18.6 km distance after scaling).
*Suggestion*: Feed the 10% ceiling into the mileage progression engine as a constraint during generation rather than patching afterward. Or regenerate workout descriptions after scaling.

**P4 — No cross-distance progression path**

When a user finishes a 5K plan and wants to move to 10K, there's no carry-over of fitness data or mileage base. The new plan starts from scratch with whatever `current_km` the user enters.

*Impact*: Users who've been following a plan for weeks lose context when creating the next plan.
*Suggestion*: The "next plan CTA" feature already exists in the UI. Consider pre-filling `current_km` from the final week of the completed plan and carrying over VDOT.

**P5 — Profile override of current_km can surprise users**

If a profile's `avg_weekly_km` is higher than the stated `current_km`, the profile value silently takes over. A user who intentionally enters a lower base (e.g., returning from injury) would get a more aggressive plan than expected.

*Impact*: Safety concern for injury-return scenarios.
*Suggestion*: When profile overrides `current_km`, surface this to the user: "Your recent training shows X km/week — we used that instead of Y."

---

## Part 2: Adaptation / Adjustment Flow

### Architecture Grade: A

The adaptation system is decomposed into 14 focused modules under `app/services/adaptation/`:

```
signal_computer.py    — 5-signal weighted computation
plan_adjuster.py      — orchestrates the adjustment flow
week_adjuster.py      — applies multiplier to future workouts
run_mapper.py         — greedy run-to-workout matching
alert_checker.py      — proactive missed/fatigue alerts
suggestion_generator.py — per-week suggestion cards
recalibrator.py       — strategy-based recalibration (missed week, recovery, time off, ahead)
missed_week_handler.py — missed week shift-down logic
recovery_inserter.py  — ad-hoc recovery week insertion
performance_analyzer.py — workout completion analysis
skipped_detector.py   — unlinked workout detection
hr_zone_analyzer.py   — HR zone adherence tracking
vdot_recalibrator.py  — VDOT drift correction
type_swapper.py       — workout type swap proposals
```

### What Works Well

**1. Multi-Signal Weighted Adjustment (signal_computer.py)**

This is the core of the system and it's well-designed:

- **5 input signals**: volume ratio, effort factor, completion rate, HR zone adherence, feedback sentiment
- **Phase-aware weighting**: Base phase weights volume at 40%; taper phase weights completion and HR at 25% each
- **Recency decay**: Half-life of 3 weeks (exponential), so recent runs matter more
- **Importance weighting by workout type**: long runs count 1.5x, recovery 0.5x — missing a long run matters more than missing a recovery run
- **Per-type Bayesian shrinkage**: With few runs of a type, the ratio shrinks toward the global volume ratio. As more type-specific data accumulates, the per-type ratio dominates. This prevents a single tempo run from wildly swinging tempo-specific adjustments.
- **Consecutive direction clamping**: After 3+ adjustments in the same direction, the range widens from [0.85, 1.15] to [0.70, 1.25] — recognizing sustained trends that need larger corrections.

**2. Overreach Detection**

Triple-layer safety:
1. Volume > 120% AND effort > 8.0/10 → force cap at 0.88x
2. HR zone adherence < 30% AND deviation > 1.0 zone → force cap at 0.85x
3. VDOT declining → cap at 0.92x

These operate independently, so multiple signals can trigger simultaneously.

**3. Workout-Type-Aware Adjustment (week_adjuster.py)**

Not all workouts are scaled equally:
- **Long runs protected on downturns**: If multiplier < 1.0, long run distance stays at baseline (long run fitness is the hardest to rebuild)
- **Quality workouts get half the adjustment**: `1.0 + (mult - 1.0) * 0.5` — a 10% volume increase only increases intervals by 5%
- **Easy runs get full adjustment**: These absorb the volume change safely

**4. Run-to-Plan Mapping (run_mapper.py)**

The greedy matching with composite scoring (date proximity × 3 + distance difference + rest penalty) is pragmatic. The `dry_run` mode enables testing without side effects. Unmatched runs still count toward weekly volume via the "weekly_volume" category.

**5. Recalibration Strategies (recalibrator.py)**

Four distinct strategies for different scenarios:
- **missed_week**: Phase-aware ease-in (base: 80%, peak: 65%) then shift remaining weeks
- **recovery_insertion**: Convert next non-recovery week to 60% volume (limited to 2 per plan)
- **time_off**: Progressive ramp-back from 70% with linear increase
- **ahead**: 10% flat increase on remaining weeks

**6. Alert System (alert_checker.py)**

Graduated cooldown after recalibration is a sophisticated touch:
- Week 1: suppress all alerts (let the adjustment take effect)
- Week 2: allow effort alerts, suppress volume alerts
- Week 3+: full alerting

The fatigue alert (avg effort ≥ 7.5 with increasing trend) catches overtraining risk before it becomes injury.

**7. Gap Analysis (gap_analysis_service.py)**

Multi-dimensional analysis (volume, long run, pace, consistency, fitness trajectory) with actionable recommendations tied to specific endpoints:
- `extend_long_run` → per-week override
- `bump_volume` → per-week override
- `view_swap_proposals` → opens type swap modal
- `adjust_plan` → triggers full recalibration

**8. Readiness Service (readiness_service.py)**

Weighted 5-component readiness score (volume 25%, VDOT 25%, long run 20%, consistency 15%, taper 15%) with per-component breakdowns and race-day scenarios.

**9. Coaching Feedback Pipeline**

Full loop from run logging → quality scoring → per-run feedback → weekly summaries → adaptation signals. The sentiment classification feeds back into the signal computer as the feedback_factor.

### Flagged Improvements

**P1 — No automatic adaptation trigger**

Currently, `adjust_plan()` only runs when the user manually clicks "Adjust Plan" or an API call is made. There's no automatic trigger after N runs or at week boundaries.

*Impact*: Users who don't know about the adjustment feature (or forget to use it) never benefit from the adaptation system. The system accumulates signals but doesn't act on them.
*Suggestion*: Auto-trigger adjustment after each completed training week (7 days since last adjustment) or after every 3rd logged run linked to the plan. Surface the result as a non-blocking notification rather than auto-applying changes, so the user maintains control.

**P2 — Run-to-plan greedy matching is suboptimal**

The greedy algorithm processes runs sequentially within each week, taking the best available match. This can produce suboptimal global matches:

```
Week 3: Run A (8 km, Monday) and Run B (5 km, Tuesday)
Workouts: Easy (5 km, Monday), Tempo (8 km, Wednesday)

Greedy: A→Easy (date penalty 0, dist diff 3), B→Tempo (date penalty 1, dist diff 3)
Optimal: A→Tempo (date penalty 2, dist diff 0), B→Easy (date penalty 1, dist diff 0)
```

*Impact*: Misattributed run types can skew per-type volume ratios in signal computation.
*Suggestion*: Use the Hungarian algorithm (scipy.optimize.linear_sum_assignment) for optimal bipartite matching within each week. The cost matrix is already computed; it's only the selection strategy that's suboptimal. Week sizes are small (≤7 workouts), so performance isn't a concern.

**P3 — Effort trend uses simplistic midpoint split**

```python
mid_point = len(efforts) // 2
first_half_avg = sum(efforts[:mid_point]) / mid_point
second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
```

With only 4+ data points required and a 1.0-point threshold, this is noisy. A runner with efforts [6, 8, 5, 7] shows "stable" despite high variance. One with [5, 5, 6, 7] shows "increasing" but the trend is mild.

*Impact*: Effort trend modifier (±0.03) may fire inappropriately on small datasets.
*Suggestion*: Use a simple linear regression slope on chronologically-ordered efforts, weighted by recency. The slope directly gives trend magnitude, and its p-value indicates confidence.

**P4 — Alert cooldown can suppress critical signals**

After recalibration, the graduated cooldown (full → volume_only → none over 3 weeks) suppresses all alerts in week 1. If a user recalibrates but then has a genuine injury or life event, the system won't alert for a full week.

*Impact*: Delayed detection of legitimate problems post-recalibration.
*Suggestion*: Allow severity="critical" alerts (e.g., zero runs in a full week or effort > 9.0/10 on 3+ consecutive runs) to bypass cooldown. Only suppress "informational" and "high" alerts during cooldown.

**P5 — Weekly total recalculation is scattered across 6+ locations**

`total_km` is recomputed in: `week_adjuster.py`, `plan_adjuster.py` (reset), `recalibrator.py`, `missed_week_handler.py`, `recovery_inserter.py`, `week_adjustment_service.py`, and `plan_adjustments.py`. Each has the same pattern:

```python
new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
```

*Impact*: Maintenance burden and risk of drift if one location is missed during a change.
*Suggestion*: Extract a `sync_week_total(week, workouts, pd_week)` helper into `_helpers.py` and call it from all locations.

**P6 — Recovery insertion hard-limited to 2 per plan**

The limit is reasonable for most plans, but a 24-week marathon plan with two mid-plan illnesses could legitimately need a third recovery insertion. The limit is a blunt instrument.

*Impact*: Users with legitimate recovery needs are blocked.
*Suggestion*: Scale the limit by plan duration: `max(2, weeks_duration // 10)`. A 24-week plan gets 2, an 8-week plan still gets 2, but very long plans (if ever supported) could get more.

**P7 — VDOT recalibration failure is silently swallowed**

```python
try:
    vdot_result = check_vdot_recalibration(training_plan, user_id, db)
except Exception as e:
    logger.warning("VDOT recalibration failed (non-fatal): %s", e)
```

*Impact*: If VDOT recalibration consistently fails (e.g., due to a data issue), the system never corrects goal times, leading to increasingly stale pace targets.
*Suggestion*: Track consecutive VDOT recalibration failures on the plan. After 3 consecutive failures, surface a warning to the user or in the adjustment response.

**P8 — No minimum workout distance after quality cap enforcement**

`enforce_week_caps()` can reduce workout distances to maintain total-week caps, but there's no minimum floor per workout. A tempo run could theoretically be capped down to 1.0 km, which isn't a useful workout.

*Impact*: Unusable short workouts post-cap enforcement.
*Suggestion*: Add a per-type minimum floor (e.g., tempo ≥ 3 km, interval ≥ 2 km, long ≥ 5 km). If a cap would push below the floor, convert the workout to easy or rest instead.

---

## Part 3: Cross-Cutting Observations

### Strengths

1. **Test coverage is outstanding** — 32,382 tests across 29 test files covering plan generation, adaptation, routing, Strava integration, security, and VDOT calculations. All passing.

2. **Separation of concerns is clean** — Business logic lives in `core/` and `services/`, routing in `routers/`, models in `models/`. The adaptation service facade pattern keeps the API stable while internals are refactored.

3. **Safety-first design** — 10% rule, overreach detection, long run protection on downturns, recovery week cadence, ACWR risk adjustment, and quality workout half-adjustment all prioritize runner safety over aggressive optimization.

4. **Progressive complexity** — Beginner → Standard → Performance plans offer appropriate sophistication for each level. Users aren't overwhelmed with VDOT zones on a Couch-to-5K plan.

5. **Rich feedback loop** — Run logging → quality scoring → coaching feedback → weekly summaries → adaptation signals → plan adjustments → gap analysis → readiness assessment forms a complete closed loop.

### Areas for Investment

1. **Automatic adaptation trigger** (P1 above) — this is the single highest-impact improvement. The entire adaptation pipeline exists but depends on manual user action.

2. **Cross-plan progression** (Generation P4) — carrying fitness context between plans would significantly improve the multi-race-season experience.

---

## Summary of Improvements by Priority

| # | System | Issue | Priority | Effort |
|---|--------|-------|----------|--------|
| 1 | Adaptation | No automatic adaptation trigger | P1 | Medium |
| 2 | Adaptation | Greedy run matching → Hungarian algorithm | P2 | Low |
| 3 | Adaptation | Scattered weekly total recalculation | P5 | Low |
| 5 | Generation | Beginner pace hardcoded at 8.0 min/km | P2 | Low |
| 6 | Generation | 10% rule post-generation only | P3 | Medium |
| 7 | Adaptation | Effort trend simplistic midpoint split | P3 | Low |
| 8 | Adaptation | Alert cooldown suppresses critical signals | P4 | Low |
| 9 | Adaptation | VDOT recalibration failure silent | P7 | Low |
| 10 | Adaptation | No minimum workout distance after caps | P8 | Low |
| 11 | Generation | Profile override of current_km not surfaced | P5 | Low |
| 12 | Generation | No cross-distance progression path | P4 | Medium |
| 13 | Adaptation | Recovery insertion hard limit of 2 | P6 | Low |
