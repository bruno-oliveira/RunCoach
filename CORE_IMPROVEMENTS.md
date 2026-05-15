# RunCoach Core Improvements

A domain-informed assessment of the current plan generation and adaptation system, benchmarked against Runna, Strava, TrainingPeaks, and Garmin Coach — with a prioritized roadmap of concrete, file-referenced changes.

This document is roadmap-level: every item is **What / Why / Where / Delta / Effort / Type**. No code; the citations point you to the right module to start a PR.

---

## 1. Executive Summary

### What we should keep doing

RunCoach already does several things that are genuinely good — these are not where we should spend energy:

- **Jack Daniels VDOT math** is correctly implemented with the full 6-zone model (`app/core/training/vdot_calculator.py`).
- **10% week-over-week mileage cap** is enforced against the *actual high-water mark*, not the plan's ceiling, with flexible workouts (easy/long) absorbing scaling while prescriptive key workouts stay fixed (`app/core/generators/plan_generator.py:96-148`). This is more sophisticated than most apps.
- **80/20 polarization** is enforced via `app/core/training/quality_caps.py`.
- **Multi-signal adaptation pipeline** already exists (`app/services/adaptation/signal_computer.py`): volume, effort, completion, HR zone, feedback sentiment, VDOT trend.
- **ACWR-based injury risk** is computed and used in alerts.
- **Race prediction** uses VDOT with endurance calibration on flat long runs, an outlier filter (Tukey IQR + median-ratio), and trail-aware elevation modeling (`app/services/fitness/race_predictor_service.py`).
- **Curated key-workout library** of ~30 race-specific overlay sessions (`app/core/training/key_workout_library.py`).

### Top 7 gaps vs. mature apps

| # | Gap | App that does this |
|---|-----|--------------------|
| 1 | Adaptation requires user clicking "Adjust"; no auto re-plan on new runs | Runna |
| 2 | `ReadinessLog` (sleep/soreness/energy/stress) is collected but **never queried** in plan logic | Garmin Coach |
| 3 | `CTL / ATL / TSB` is computed by `TrainingLoadService` but only surfaced in analytics — disconnected from `signal_computer` and `plan_adjuster` | TrainingPeaks PMC |
| 4 | No GAP (grade-adjusted pace), no per-km splits, no streams — hilly easy runs look "too slow" | Strava |
| 5 | 44 hardcoded coaching-note templates keyed by `(workout_type, phase)`; zero personalization at render time | Runna workout-of-the-day reasoning |
| 6 | Pace zones are frozen at plan generation — they don't progress as fitness improves mid-plan | Runna progressive zones |
| 7 | `RunLog.effort_quality_score`, `hr_zone_deviation`, `effort_class` are populated by ingest but **not read** in adaptation (only `quality_label` is, in `type_swapper.py:105,121`) | — |

The good news: most of these are *wire-ups* of data we already collect, not new infrastructure.

---

## 2. Signal capture upgrades

> **Data we already collect but ignore:** `RunLog.effort_quality_score`, `RunLog.hr_zone_deviation`, `RunLog.effort_class`, the entire `ReadinessLog` table.

### 2.1 Activate ReadinessLog — `wire-up`, **S**
- **Why.** Garmin Coach and Runna both gate today's workout on subjective wellness. We collect sleep/soreness/energy/stress already (`app/models/readiness_log.py`) but nothing reads it.
- **Where.** `app/services/adaptation/signal_computer.py` (phase-weight tuple `_PHASE_WEIGHTS` near top of file); `app/services/adaptation/plan_adjuster.py` (`gather_signals`).
- **Delta.** Load the last 7 `ReadinessLog` rows in `gather_signals`. Compute a `readiness_factor` in [0.92, 1.05] from the existing `score`. Blend into `raw_multiplier` with ~0.10 weight; rebalance `_PHASE_WEIGHTS` so total stays at 1.0. Low readiness → mild volume cut; high readiness during peak → slightly raise ceiling.

### 2.2 Surface unused run-log enrichment — `wire-up`, **S**
- **Why.** `effort_quality_score`, `hr_zone_deviation`, and `effort_class` already exist on every `RunLog`. The adapter ignores them.
- **Where.** `app/services/adaptation/signal_computer.py` — extend the per-workout-type aggregation in `compute_adjustment_signals`.
- **Delta.** Add an *effort-quality drift* trend (last 8 runs trending down → ~-0.03 to the multiplier). Use `hr_zone_deviation` to detect "drift to higher zone at same pace" → flag fatigue independent of perceived effort. `quality_label` is already consumed by `type_swapper.py` — leave alone.

### 2.3 GAP (grade-adjusted pace) — `new-data`, **M**
- **Why.** Strava's GAP is the de-facto fairness metric. A hilly easy run currently looks "too slow" and falsely depresses pace consistency.
- **Where.** New `app/services/runs/gap_calculator.py`. Add `gap_min_km` column to `app/models/run_log.py` via Alembic migration.
- **Delta.** Populate during Strava sync (`app/services/integrations/strava_post_sync_service.py`) using the existing elevation gain and a standard grade-cost curve (Minetti or Strava's published model). `signal_computer.py` switches to GAP for `effort_factor` when `elevation_gain_m / distance_km >= 10`. Manual run logs default `gap = avg_pace_min_km`.

### 2.4 Splits / laps and time-series streams — `new-data`, **L**
- **Why.** Enables (a) per-interval grading of key workouts (did the runner hit reps 5–8 of the 8×400?), (b) rolling PR detection per segment distance, (c) HR drift / decoupling computation.
- **Where.** New `app/models/run_split.py` (1:N with `RunLog`). Extend Strava sync to persist `laps` and a 30s-downsampled HR/pace stream.
- **Delta.** Wire per-lap completion into the post-run coaching feedback engine so a missed interval pace shows up as "you ran 3:55 pace on reps 5–8 vs. 3:42 target" instead of a single workout-average judgment.

### 2.5 HRV / wellness ingestion — `new-data`, **L** (feature-flagged)
- **Why.** Garmin "Training Readiness" combines HRV + sleep + acute load.
- **Where.** New `app/services/integrations/healthkit_service.py` (iOS HealthKit) or extend Strava sync if available there.
- **Delta.** Daily HRV row supplements (does not replace) the subjective `ReadinessLog` inputs from §2.1.

---

## 3. Fitness modeling upgrades

### 3.1 Wire CTL / ATL / TSB into the adjuster — `wire-up`, **M**
- **Why.** TrainingPeaks' Performance Management Chart is the industry standard "form" gauge. We compute it (`app/services/fitness/training_load_service.py`) but `analytics.py:140-146` is the *only* caller. The adapter has no access to it.
- **Where.** `app/services/adaptation/plan_adjuster.py` (`gather_signals`); `app/services/adaptation/signal_computer.py` (apply at multiplier-clamp step).
- **Delta.** Call `TrainingLoadService.get_training_load` inside `gather_signals`. Negative TSB ≤ -25 → cap `raw_multiplier` at 0.92 (same pattern as the existing `vdot_trend == "declining"` clamp). Positive TSB ≥ +10 on a peak-phase week → permit `raw_multiplier` up to +1.08 (conditional extension of `_EXPANDED_MAX = 1.25`). Expose `tsb_form` in `recommendation_evaluator` output so the UI can show a "primed" label.

### 3.2 Per-workout TSS — `new-model`, **M**
- **Why.** TSS is the unit that makes CTL meaningful. Current load is a duration × intensity TRIMP proxy in `training_load_service.py` — fine for ACWR, coarse for everything else.
- **Where.** New `app/services/fitness/tss_calculator.py`. Persist `tss` on `RunLog` via Alembic.
- **Delta.** rTSS formula: `(duration_s × IF²) × 100 / 3600`, with `IF = NGP / T_pace_from_vdot`. Backfill via migration script. Surface per-workout TSS in the run detail view in place of the current `effort_quality_score` chart.

### 3.3 Dynamic VDOT recompute cadence — `wire-up`, **S**
- **Why.** Runna's "your pace zones just got faster" notification is one of the most-cited UX moments. We currently only recompute VDOT inside `adjust_plan`.
- **Where.** `app/services/adaptation/vdot_recalibrator.py`; call site needs to move.
- **Delta.** Invoke recalibration from a per-run hook in the run-enrichment path (`app/routers/runs.py` after `evaluate_recommendation`, and from `strava_post_sync_service.py`) when the just-logged run is a tempo / long / race-effort. The user sees a "VDOT 51 → 52" toast immediately. Pair with §4.1.

---

## 4. Plan generation upgrades

### 4.1 Pace-zone progression mid-plan — `wire-up`, **S**
- **Why.** Runna calls this their #1 differentiator. Today our zones are persisted at plan generation and never updated — even after VDOT changes.
- **Where.** `app/services/adaptation/vdot_recalibrator.py`; `WeeklyPlan` and `DailyWorkout` models.
- **Delta.** After §3.3 recalibration fires, loop over the remaining `adjustable_weeks` and rewrite each future `DailyWorkout.pace_zones`. Add `pace_zones_updated_at` to `WeeklyPlan`. Show a "Zones updated" badge in the plan view.

### 4.2 Individualized phase shapes — `new-model`, **M**
- **Why.** `PHASE_DISTRIBUTIONS` in `app/core/training/phase_calculator.py` is *distance-only*. A first-time half-marathoner and a 1:25 half-marathoner targeting the same race should not have the same base:build:peak ratio.
- **Where.** `app/core/training/phase_calculator.py`.
- **Delta.** Add an `experience_level` axis. `app/core/training/strength_plan.py` already derives experience from `current_km` — reuse the same bucketing. Beginners: +1 week base, -1 week peak. Advanced: inverse. Mid-tier: status quo.

### 4.3 Smarter key-workout selection — `wire-up`, **S**
- **Why.** `key_workout_library.py` (`overlay_key_workout`, `get_for_phase`) currently filters by `(phase, distance, terrain)`. It ignores what the runner is *actually weak at*.
- **Where.** `app/core/training/key_workout_library.py`; consume signal from `app/services/fitness/gap_analysis_service.py`.
- **Delta.** Add a "user weakness" axis from the gap analyzer's top action. Pace gap → prefer tempo/interval overlays. Volume gap → prefer long-run progressions. Consistency gap → prefer fartlek over rigid interval sessions.

---

## 5. Adaptation loop upgrades

### 5.1 Auto-adjust on run logging — `wire-up`, **M** *(flagship change)*
- **Why.** Runna re-plans automatically. The current "click Adjust" pattern is the single biggest UX gap.
- **Where.** `app/routers/runs.py` already calls `evaluate_recommendation` after each run; `app/services/integrations/strava_post_sync_service.py` does the same for synced runs. Both write `pending_recommendation` and stop.
- **Delta.** When `recommendation_evaluator` returns high-confidence (|multiplier delta| > 0.05 OR an overreach signal), call `plan_adjuster.adjust_plan` automatically. Keep the low-confidence path → `pending_recommendation` banner. Gate behind a user setting `auto_adjust_enabled` (default `true` for new users, opt-out for existing). Fire a `PushNotification` for "your next workout changed."

### 5.2 Wellness-aware day swap — `new-model`, **M**
- **Why.** "Move today's quality to tomorrow because you slept badly" is what Runna and Garmin both do.
- **Where.** New `app/services/adaptation/day_swap_service.py`; called from a morning cron (the `schedule` skill already supports this).
- **Delta.** If today's `ReadinessLog.status == "rest"` and today's `DailyWorkout.workout_type` is quality (tempo/interval/hill/long), swap it with the next rest/easy day in the same week. Append a swap record to `adaptation_history` JSON.

### 5.3 Yesterday-influences-today coaching — `wire-up`, **S**
- **Where.** `app/core/coaching/coaching_notes_generator.py` (`generate_coaching_note`).
- **Delta.** Accept an optional `prev_run: RunLog` parameter. Prepend a dynamic clause: *"After yesterday's strong tempo, today's easy run is recovery — keep it conversational."* Pure rules, no LLM.

---

## 6. Coaching content upgrades

Section 6 presents **two tracks** that can ship together. The template DSL is the baseline; the LLM track is an option that requires an explicit cost/UX decision.

### 6.1 Track A — Template DSL with runtime variables — `wire-up`, **M**
- **Why.** The current 44 static templates in `coaching_notes_generator.py` (`_NOTES` dict) are keyed only by `(workout_type, phase)`. The render call already has access to far more context.
- **Where.** `app/core/coaching/coaching_notes_generator.py`; render path in `app/services/plans/plan_template_context.py`.
- **Delta.** Convert string templates to a tiny DSL with named variables: `{tsb_form}`, `{weeks_to_race}`, `{last_run_sentiment}`, `{readiness_status}`, `{prev_workout_type}`. Add a few branching templates per `(type, phase)` selected based on those variables. No LLM cost, fully deterministic, easy to test.

### 6.2 Track B — Targeted LLM per new run — `new-model`, **M** *(option, behind a flag)*
- **Why.** Even with a richer template DSL, the *narrative* coaching that Runna and Strava ship feels human in a way templates can't match.
- **Where.** New `app/services/coaching/llm_coach_summary.py`. Cache result on `RunFeedback.coach_summary`.
- **Delta.** **One** LLM call per *new run logged* — never per page render. Input context: the run's metrics + plan position + last 2 weeks of efforts + `tsb_form`. Output: a 2-sentence "what this run tells me" paragraph. Cached forever per run.
- **Cost/UX tradeoffs.** ~1 call per logged run → bounded cost (a typical user logs 3–6 runs/week). Latency hidden behind the existing post-run feedback animation. Failure mode: if the LLM call fails, fall back to Track A's template output — never block the run-logging response.

### 6.3 Effort-aware rationale — `wire-up`, **S**
- **Where.** `app/core/generators/workout_scaler.py` and the daily render path.
- **Delta.** If the last 3 runs have mean `perceived_effort ≥ 8` AND `RunFeedback.overall_sentiment == "warning"` for ≥ 2 of them, prefix the next quality workout's rationale with "consider easing this one." Lightweight signal independent of §5.1's full re-adjustment.

### 6.4 Nutrition feedback loop — *deferred*
- Nutrition (`app/core/nutrition/`) is currently a pure formula with no feedback from logged eating. Out of scope for this round; flagged here so it doesn't get lost.

---

## 7. Race prediction upgrades

### 7.1 GAP-corrected predictions — depends on §2.3
- **Why.** Current predictor uses raw pace + an elevation penalty during the prediction. For hilly trainers this *double-penalizes* (the input VDOT is already understated, then we add the course-elevation penalty on top).
- **Where.** `app/core/training/race_predictor.py` (`predict_time_for_distance`); `app/services/fitness/race_predictor_service.py`.
- **Delta.** Feed GAP-derived VDOT (from §2.3) as the input. The course-elevation penalty in `race_predictor.py` then applies cleanly to the course only.

### 7.2 Course-specific elevation profile — `new-data`, **M**
- **Where.** `app/core/training/race_predictor.py:predict_time_for_distance` currently accepts `elevation_gain_m` as a single scalar.
- **Delta.** Accept `elevation_profile: list[(km, grade_pct)]` from a GPX upload. Apply the existing piecewise grade-penalty tiers per segment instead of the current "50% applied at 2× avg" approximation. Surface a GPX upload in the race-profile UI.

### 7.3 Confidence range tightening — `wire-up`, **S**
- **Where.** `app/core/training/race_predictor.py:get_confidence_range`.
- **Delta.** Current margins are hardcoded (±1.5 / ±5.0). Tighten based on data quantity using `len(all_plan_runs)` already available in `RacePredictorService`. 50+ logged runs → ±1.0; <10 → ±2.5.

---

## 8. Prioritized roadmap

ROI ordering: cheap wire-ups of unused data first, then closing the feedback loop, then heavier ingestion / modeling.

| Phase | Theme | Items | Cumulative effort | User-visible win |
|-------|-------|-------|-------------------|------------------|
| **P1: Activate dead data** | Cheap wins from wired-but-unused signals | 2.1 ReadinessLog · 2.2 surface unused enrichment · 3.1 CTL/ATL/TSB wiring · 3.3 dynamic VDOT · 4.1 progressing pace zones | ~2 weeks | "The plan reflects how I actually feel" |
| **P2: Close the loop** | Auto-adjust + dynamic coaching | 5.1 auto-adjust · 5.3 yesterday-affects-today notes · 6.3 effort-aware rationale | ~2 weeks | "It changed my plan after my run, automatically" |
| **P3: Strava parity** | GAP + splits | 2.3 GAP · 2.4 splits/streams · 7.1 GAP-corrected prediction | ~3 weeks | Fair pacing on hilly runs; per-interval workout grading |
| **P4: Smarter coach** | Contextual content & wellness scheduling | 5.2 wellness day swap · 6.1 template DSL · 6.2 targeted LLM summaries *(flagged)* | ~3 weeks | Coach voice feels personal |
| **P5: Advanced modeling** | Heavier lifts behind flags | 2.5 HRV ingestion · 3.2 per-workout TSS · 4.2 individualized phase shapes · 4.3 smarter key-workout selection · 7.2 course-elevation profile · 7.3 confidence tightening | ~4–6 weeks | TrainingPeaks-level depth |

### Explicit non-goals

We are **not** changing these — they already work and a rewrite would only introduce regressions:

- The VDOT math (`vdot_calculator.py`).
- The phase-distribution model itself (just adding an experience axis in §4.2, not redesigning it).
- The 10% week-over-week cap.
- The curated key-workout library content.
- The beginner Couch-to-5K generator.
- The Tukey IQR outlier filter in race prediction.
- The 80/20 polarization enforcement.

The improvements in this document **layer around** the working core — they do not replace it.
