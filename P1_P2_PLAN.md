# P1 + P2 Implementation Plan

In-depth execution plan for the first two phases of `CORE_IMPROVEMENTS.md`.

## Scope

**In scope (8 items, ~4 weeks of work):**

P1 — Activate dead data:
- §2.1 Wire `ReadinessLog` into the multi-week signal pipeline
- §2.2 Surface unused run-log enrichment in adaptation
- §3.1 Wire CTL / ATL / TSB into the adjuster
- §3.3 Move VDOT recompute to the per-run hook
- §4.1 Pace-zone progression mid-plan

P2 — Close the loop:
- §5.1 Auto-adjust on run logging (flagship)
- §5.3 Yesterday-influences-today coaching notes
- §6.3 Effort-aware rationale

**Out of scope (by user direction):**
- §6.4 Nutrition feedback loop
- §2.5 HRV ingestion
- Any new third-party data source (no HealthKit, no Garmin Connect, no Whoop). **Strava remains the only external data source.** All wins here come from data we already have.

**Important nuance discovered during investigation:** `ReadinessLog` is not entirely unused. `app/routers/readiness.py:171-291` exposes a `POST /api/readiness/adapt` endpoint that swaps *today's* workout based on the morning check-in. What is missing is `ReadinessLog` feeding the **multi-week adaptation pipeline** (`signal_computer.py`, `plan_adjuster.py`). The single-day swap is preserved; we are adding it as a signal.

---

## Execution order

Three sprints, each with a coherent theme and shippable independently.

| Sprint | Theme | Items | Effort | Ship gate |
|--------|-------|-------|--------|-----------|
| **S1** | Cheap signal wires | 2.2, 2.1, 3.1 | ~1.5 wk | All three contribute to `compute_adjustment_signals` output; deploy as one batch with feature flag `RC_ENRICHED_SIGNALS` off → on |
| **S2** | VDOT-driven zone progression | 3.3, 4.1 | ~1 wk | One toast-visible UX moment ("VDOT 51 → 52, future paces updated"); deploy together |
| **S3** | Auto-adjust + coach voice | 5.1, 5.3, 6.3 | ~1.5–2 wk | Flagship UX change. Ship behind `auto_adjust_enabled` user setting; default `true` for new users, `false` for existing until they opt in |

Dependencies: 4.1 needs 3.3 (otherwise zones never refresh); 5.1 benefits from S1+S2 already shipped but does not strictly require them.

---

## Sprint 1 — Cheap signal wires

Goal: enrich `compute_adjustment_signals` output with three under-used inputs without changing any UX. The multiplier becomes more accurate; existing call sites need no changes.

### Item 2.2 — Surface unused run-log enrichment

**Why first.** Smallest blast radius. The fields (`effort_quality_score`, `hr_zone_deviation`, `effort_class`) already exist on every `RunLog` (`app/models/run_log.py:36-42`) and are populated by `app/routers/runs.py:84-91` and `app/services/integrations/strava_post_sync_service.py` ingest. We just need to read them in adaptation. Note: `quality_label` is already consumed by `app/services/adaptation/type_swapper.py:105,121` — leave that path alone.

**Files to change.**
- `app/services/adaptation/signal_computer.py`

**Step-by-step.**
1. In `compute_adjustment_signals` (`signal_computer.py:41`), after the existing effort-trend block (around lines 102-127), add a new "quality drift" sub-signal:
   - Loop over `all_plan_runs` ordered by date (last 8 runs only).
   - Take `effort_quality_score` where not null.
   - If at least 4 scores: split into first/second half, compute mean delta.
   - Map to `quality_drift_modifier`: `delta < -10` → `-0.02`, `delta > +10` → `+0.02`, else `0`.
2. Add `quality_drift_modifier` to `raw_multiplier` at line 262 alongside `trend_modifier`.
3. Add `effort_class` distribution check: count runs where `effort_class == "race_effort"` in the last 14 days. If ≥ 2 race-effort runs in 14 days, raise overreach risk by capping `raw_multiplier` at 0.95 (new clause near line 270).
4. Return new fields in the result dict: `quality_drift`, `quality_drift_modifier`, `recent_race_effort_count`.

**Tests.**
- `tests/test_signal_computer.py` (new or extend): synthetic runs with declining `effort_quality_score` → expect negative modifier; runs with two `race_effort` classes within 14 days → expect cap.

**Migration.** None.

**Rollback.** Single revert of `signal_computer.py`. Output is additive — existing fields unchanged.

**Effort: S (~1–2 days).**

---

### Item 2.1 — Wire ReadinessLog into the multi-week signal pipeline

**Why now.** Free signal: data already collected via the existing `POST /api/readiness` endpoint and used for single-day swaps, but never blended into `compute_adjustment_signals`.

**Files to change.**
- `app/services/adaptation/plan_adjuster.py` (`gather_signals` at line 29)
- `app/services/adaptation/signal_computer.py` (`compute_adjustment_signals` at line 41)

**Step-by-step.**
1. In `gather_signals` after line 76 (`run_feedback_list` fetch), add a parallel query:
   ```text
   readiness_logs = db.query(ReadinessLog)
       .filter(ReadinessLog.user_id == user_id,
               ReadinessLog.log_date >= today - timedelta(days=14))
       .order_by(ReadinessLog.log_date.desc())
       .limit(14).all()
   ```
   (no code in the doc; this is the shape.)
2. Pass `readiness_logs` through to `compute_adjustment_signals` as a new keyword argument (extend the signature at `signal_computer.py:41`).
3. Inside `compute_adjustment_signals`, after the feedback-sentiment block (around line 211), compute:
   - `readiness_factor`: mean of `score / 100` across logs in [0, 1]; map to multiplier in [0.92, 1.05] via `0.92 + readiness_pct × 0.13`.
   - If `< 3` logs in window: `readiness_factor = 1.0`, weight = 0 (mirror the no-HR path at lines 153-163).
4. Add a phase-aware weight `readiness_weight` to `_PHASE_WEIGHTS` (line 12). Suggested tuples (rebalanced so each sums to 1.0):
   - `base`:   (0.38, 0.18, 0.18, 0.11, 0.07, 0.08)
   - `build`:  (0.33, 0.20, 0.16, 0.14, 0.09, 0.08)
   - `peak`:   (0.28, 0.20, 0.16, 0.16, 0.10, 0.10)
   - `taper`:  (0.10, 0.20, 0.22, 0.22, 0.14, 0.12)
   (Sixth slot is readiness; taper weights it higher because acute fatigue matters most then.)
5. Update the unpack at line 57 to include `readiness_weight`.
6. Add `readiness_factor * readiness_weight` to `raw_multiplier` at line 254.
7. Return `readiness_factor`, `readiness_weight`, and `readiness_log_count` in the result dict (line 293).
8. Update the no-HR rebalance at lines 153-163 to include `readiness_weight` in the redistribution math.

**Tests.**
- `tests/test_signal_computer.py`: three readiness scores at 30 → expect `readiness_factor < 1.0` and a reduced multiplier; three scores at 90 → expect mild boost.
- `tests/test_plan_adjuster.py`: end-to-end with seeded `ReadinessLog` rows; assert `adjust_plan` result includes `readiness_factor`.

**Migration.** None. `ReadinessLog` table already exists.

**Rollback.** Set `readiness_weight = 0` in the phase tuples; takes one commit. Or revert both files.

**Effort: S (~2 days).**

---

### Item 3.1 — Wire CTL / ATL / TSB into the adjuster

**Why.** `TrainingLoadService.get_training_load` (`app/services/fitness/training_load_service.py`) already computes the full Performance Management Chart. Only caller today is `app/routers/analytics.py:140-146`. The adapter is flying blind on accumulated load.

**Files to change.**
- `app/services/adaptation/plan_adjuster.py`
- `app/services/adaptation/signal_computer.py`

**Step-by-step.**
1. In `gather_signals` (`plan_adjuster.py:29`), after the `vdot_trend` block (~line 116), call `TrainingLoadService.get_training_load(user_id, db, lookback_days=42)`. Wrap in try/except — same pattern as the existing VDOT try/except — and pass through as `training_load` keyword arg to `compute_adjustment_signals`.
2. In `compute_adjustment_signals`, extract `tsb = training_load.get("current", {}).get("tsb")` (the existing `TrainingLoadService` return shape).
3. After the existing `vdot_trend == "declining"` clamp (line 280), add two new clauses (preserve clamp ordering — apply tightest cap first):
   - If `tsb is not None and tsb <= -25`: `raw_multiplier = min(raw_multiplier, 0.92)`; set `tsb_form = "overreached"`.
   - If `tsb is not None and tsb >= 10` and `current_phase == "peak"`: extend the upper clamp from `_STANDARD_MAX` to `_EXPANDED_MAX` (replicate the `consecutive_same_direction` clamp logic at lines 283-289 with a `peak_primed` branch). Set `tsb_form = "primed"`.
   - Otherwise: `tsb_form = "neutral"` if `tsb between -10 and +5`, else `tsb_form = "fresh"` or `"loaded"` accordingly.
4. Return `tsb`, `ctl`, `atl`, `tsb_form` in the result dict.
5. Surface `tsb_form` in the `plan_adjuster.adjust_plan` `reason_parts` list at `plan_adjuster.py:237-253` so the user-facing reason string mentions "form: primed" or "form: overreached".

**Tests.**
- `tests/test_signal_computer.py`: synthetic `training_load` with `tsb=-30` → expect `raw_multiplier ≤ 0.92`; with `tsb=+12` in peak phase → expect access to `_EXPANDED_MAX`.
- Integration test in `tests/test_plan_adjuster.py`: seed 6 weeks of varied runs, mock `TrainingLoadService.get_training_load`, assert returned dict includes `tsb_form`.

**Migration.** None.

**Rollback.** Revert both files. `TrainingLoadService` itself is untouched.

**Effort: M (~3 days).** Most effort goes into the clamp-ordering test matrix.

---

### Sprint 1 ship checklist

- [ ] Feature flag `RC_ENRICHED_SIGNALS` (env var, default `false`) gates the three new signals so we can roll back without redeploy
- [ ] `plan_adjuster.adjust_plan` reason string includes the new fields when flag is on
- [ ] Dashboard panel (existing analytics page) gets a "Form" badge reading `tsb_form` — small frontend touch, ~2h
- [ ] Snapshot regression test: run the adaptation on 5 real production plans before/after, eyeball multiplier deltas, document them

---

## Sprint 2 — VDOT-driven zone progression

Goal: when a user's VDOT improves mid-plan, their remaining workouts immediately reflect the new pace zones, with a visible toast.

### Item 3.3 — Move VDOT recompute to the per-run hook

**Current state.** `check_vdot_recalibration` (`app/services/adaptation/vdot_recalibrator.py:19`) is called only from inside `plan_adjuster.adjust_plan` (`plan_adjuster.py:220`) and `recommendation_evaluator.accept_recommendation` (`recommendation_evaluator.py:188`). It never fires on a single new run — only on full adjust.

**Files to change.**
- `app/services/runs/run_enrichment_service.py` (the `enrich_vdot_and_prediction` function called from `app/routers/runs.py:93`)
- `app/services/integrations/strava_post_sync_service.py` (`auto_map_and_adjust` at line 16)
- `app/services/adaptation/vdot_recalibrator.py` — add a lighter `recalibrate_zones_only` variant
- `app/routers/runs.py` — return recalibration result in the response

**Step-by-step.**
1. In `vdot_recalibrator.py`, extract the pace-zone-rewrite loop (lines 53-89) into a standalone helper `recalibrate_zones_only(training_plan, user_id, db) -> Optional[Dict]`. Keep `check_vdot_recalibration` as the existing entrypoint — it now wraps `recalibrate_zones_only` and additionally returns the delta info for inclusion in adjustment metadata.
2. In `enrich_vdot_and_prediction` (called at `runs.py:93`), after VDOT is updated on the new run, if the run has `training_plan_id`, call `check_vdot_recalibration` for that plan. Catch and log exceptions — never fail the run-logging request.
3. Gate recalibration to only fire for runs of type `tempo`, `long`, `race`, `vo2max`, or any run with `effort_class == "race_effort"`. This prevents an easy run from triggering a VDOT bump.
4. In `auto_map_and_adjust` (`strava_post_sync_service.py:46-49`), the existing `evaluate_recommendation` call already runs. Add a second call to `check_vdot_recalibration` for each active plan after sync, gated on the same workout-type filter.
5. In the `create_run_log` response builder (`runs.py:116-136`), add `vdot_recalibration` field if recalibration occurred, so the frontend can show the toast.

**Tests.**
- `tests/test_vdot_recalibrator.py`: simulate a user with VDOT 50 plan, log a tempo run that yields VDOT 52, assert pace zones on future workouts rewrite.
- Negative test: log an easy run with the same VDOT delta → no recalibration.

**Migration.** None.

**Rollback.** Remove the `check_vdot_recalibration` call from `enrich_vdot_and_prediction` and `auto_map_and_adjust`. Original call sites in `plan_adjuster` and `recommendation_evaluator` remain.

**Effort: S (~2 days).**

---

### Item 4.1 — Pace-zone progression mid-plan

**Current state.** `check_vdot_recalibration` already rewrites `target_pace` and `segments[].pace_raw` in `plan_data` (lines 53-89 of `vdot_recalibrator.py`). It does **not** touch the `DailyWorkout` DB rows or any structured pace-zones field. The frontend reads from `plan_data` JSON for some views and from `DailyWorkout` for others — the inconsistency means stale zones can still be displayed.

**Files to change.**
- `app/services/adaptation/vdot_recalibrator.py` — extend `recalibrate_zones_only` to also update DB rows
- `app/models/weekly_plan.py` — add `pace_zones_updated_at` timestamp column (Alembic migration)
- `app/templates/components/workout_card.html` — add a "Paces updated" badge when `pace_zones_updated_at` is recent

**Step-by-step.**
1. Add Alembic migration: `add_pace_zones_updated_at_to_weekly_plan` — single nullable `DateTime` column on `weekly_plans`.
2. In `recalibrate_zones_only`, after the `plan_data` update loop, query `WeeklyPlan` rows for the plan where `week_number >= current_week`, and update their `pace_zones_updated_at` to `now`. If `DailyWorkout` carries a `planned_pace_min_km` column (verify; it's referenced in `runs.py:88`), rewrite that too for future workouts.
3. Surface `pace_zones_updated_at` in the plan template context (`app/services/plans/plan_template_context.py`) so the badge can render.
4. The badge: small text below the workout title — "Paces updated {n} days ago after your last tempo" — visible for 7 days after recalibration.

**Tests.**
- `tests/test_vdot_recalibrator.py` (extend Sprint-2 test above): assert `WeeklyPlan.pace_zones_updated_at` is set; assert `DailyWorkout.planned_pace_min_km` reflects new VDOT.
- E2E test: load the plan page in a test client after recalibration, assert badge HTML is present.

**Migration.** One Alembic step; backwards-compatible (column is nullable). Deploy migration before code change.

**Rollback.** Remove badge from template; column stays (harmless).

**Effort: S (~2 days).**

---

### Sprint 2 ship checklist

- [ ] Migration deployed and verified on the Fly volume DB (`/data/runcoach.db`)
- [ ] One real end-to-end run-of-tempo on a staging plan produces the toast
- [ ] Plan page shows the "Paces updated" badge correctly
- [ ] Log line `VDOT recalibration: plan=… old=… new=…` appears in Fly logs

---

## Sprint 3 — Auto-adjust + coach voice (the loop closes)

The flagship change. After this ships, logging a run can directly mutate next week's workouts with no user click.

### Item 5.1 — Auto-adjust on run logging

**Current state — three call paths for `evaluate_recommendation`:**

1. `app/routers/runs.py:108` after a manual run-log POST.
2. `app/services/integrations/strava_post_sync_service.py:49` after Strava sync.
3. (None for the `/api/runs/{id}` update path — out of scope for this sprint.)

All paths today only **write** `training_plan.pending_recommendation` (`recommendation_evaluator.py:125`). The user must visit the plan page and click "Accept" to actually mutate the plan.

**Files to change.**
- `app/services/adaptation/recommendation_evaluator.py` — split `evaluate_weekly_recommendation` into compute + decide
- `app/models/user.py` — add `auto_adjust_enabled` column (Alembic migration)
- `app/routers/runs.py` and `strava_post_sync_service.py` — invoke the new decide step
- `app/routers/auth.py` (or settings router) — expose toggle endpoint
- `app/templates/` — toggle UI in user settings

**Step-by-step.**

1. **Migration.** Add `auto_adjust_enabled: Boolean, default False` to `users` table. New signups will be defaulted to `True` in the signup flow (`app/routers/auth.py`). Existing users default `False`; we surface a one-time prompt on the plan page asking them to opt in.

2. **Split the evaluator.** In `recommendation_evaluator.py`, keep `evaluate_weekly_recommendation` (it currently fires on week boundary). Add a new function `evaluate_on_run_logged(plan_id, user_id, db) -> Optional[Dict]` that:
   - Calls `gather_signals` (run_map=False since the run is already mapped by the caller).
   - If `gathered is None` → return None.
   - Computes `confidence` from the signal:
     - High confidence if `abs(multiplier - 1.0) >= 0.05` AND (`signals["overreach_detected"]` OR `signals["readiness_factor"] < 0.95` OR `signals["tsb_form"] == "overreached"`).
     - Medium confidence if `abs(multiplier - 1.0) >= 0.05`.
     - Low otherwise.
   - Returns `{"confidence": ..., "multiplier": ..., "signals": ...}` (no DB write).

3. **The decision.** Add `apply_or_park(plan_id, user_id, db, evaluation, auto_enabled: bool)`:
   - High confidence + `auto_enabled` → call `plan_adjuster.adjust_plan` directly. Record event as `auto_adjust` in `adaptation_history`. Schedule a `PushNotification` (deferred — best-effort, ignore if not configured) reading "Your next workout was eased — high effort detected" (positive variant for boosts).
   - Medium confidence OR `auto_enabled == False` → write `pending_recommendation` (existing path).
   - Low confidence → no-op.

4. **Wire into `runs.py:105-112`.** Replace the existing `evaluate_recommendation` call with:
   - Call `evaluate_on_run_logged`.
   - If non-None, look up `current_user.auto_adjust_enabled` and call `apply_or_park`.

5. **Wire into `strava_post_sync_service.py:49-51`.** Same change. The Strava sync path can fire `apply_or_park` multiple times per sync (one per active plan) — that's fine; each plan is independent.

6. **Throttle.** Add a guard: if `training_plan.last_adjusted_at` is within the last 24h, do not auto-adjust. Update `last_adjusted_at` setting in `plan_adjuster.adjust_plan` (line 225) is already in place. Read it in `apply_or_park` to gate.

7. **Toggle UI.** Add a settings panel entry "Auto-adjust my plan after each run" with on/off toggle. POST to `/api/me/settings` (or wherever the user-settings router lives — check `app/routers/auth.py` for `GET /me`; add a new `PATCH /me/settings`).

**Tests.**
- `tests/test_recommendation_evaluator.py`: confidence classification tests covering each rule.
- `tests/test_auto_adjust.py` (new): full E2E with seeded plan + 3 runs that trigger overreach → assert `plan_adjuster.adjust_plan` is called, `pending_recommendation` is NOT written, `adaptation_history` has an `auto_adjust` event.
- Negative: with `auto_adjust_enabled=False`, same scenario → `pending_recommendation` is written.
- Throttle test: log two runs back-to-back; second one must not re-adjust.

**Migration.** One Alembic step on `users` table.

**Rollback.** Set `auto_adjust_enabled` default to `False` globally; existing accepted paths (`pending_recommendation` UI) keep working.

**Effort: M (~4–5 days).**

---

### Item 5.3 — Yesterday-influences-today coaching notes

**Current state.** `generate_coaching_note` (`app/core/coaching/coaching_notes_generator.py:198`) takes `workout_type, phase, week_number, target_distance, is_recovery_week` and returns a templated string from a 44-entry dict keyed by `(workout_type, phase)`.

**Files to change.**
- `app/core/coaching/coaching_notes_generator.py`
- Caller sites — find them: anywhere `generate_coaching_note` is invoked. Most likely `app/core/generators/plan_generator.py` for build-time notes; check `app/services/plans/plan_template_context.py` for render-time notes.

**Step-by-step.**
1. Extend `generate_coaching_note` signature with `prev_run: Optional[RunLog] = None`. Keep existing call sites working (default arg).
2. After the base template is fetched (line 217-221), if `prev_run` is provided and the previous run was logged within the last 2 days, prepend a dynamic prefix based on `prev_run.workout_type` and `prev_run.perceived_effort`:
   - `prev_run.workout_type in ("tempo", "interval", "vo2max")` and `perceived_effort >= 7` → "After yesterday's hard {prev_type}, "
   - `prev_run.workout_type == "long"` and `perceived_effort >= 6` → "After yesterday's long run, "
   - `prev_run.workout_type == "easy"` and `perceived_effort <= 4` → "Yesterday was easy and well-controlled — "
   - Otherwise: no prefix.
3. The prefix only applies to today-rendered cards. **Do not** persist the prefix into stored `coaching_rationale` on `DailyWorkout` — it would go stale immediately. Apply at render time only.
4. Find the render-time path. Likely `app/services/plans/plan_template_context.py` builds the daily card context — that's where to look up the user's most recent `RunLog` and pass it as `prev_run`. If the path is build-time only, add a thin render-time post-processor in the template context builder.

**Tests.**
- `tests/test_coaching_notes_generator.py`: provide a hard tempo `prev_run` from yesterday → assert prefix starts with "After yesterday's hard tempo". No `prev_run` → original string returned unchanged.

**Migration.** None.

**Rollback.** Revert one file.

**Effort: S (~1 day).**

---

### Item 6.3 — Effort-aware rationale

**Current state.** `coaching_rationale` is set at plan generation and never updated. There's no signal that flags "your last few runs were brutal — go easy today" in the coach voice.

**Files to change.**
- `app/services/plans/plan_template_context.py` (render-time augmentation, same file as 5.3)
- Optionally `app/core/generators/workout_scaler.py` if there's a similar render path

**Step-by-step.**
1. In the daily-card context builder, fetch the last 3 `RunLog` rows for the user.
2. Compute: mean `perceived_effort` across non-null values; count of those 3 where `RunFeedback.overall_sentiment == "warning"` (join via `run_feedback` relationship).
3. If `mean_effort >= 8` AND `warning_count >= 2` AND today's workout `workout_type in ("tempo", "interval", "vo2max", "hill", "long")`:
   - Prepend "Consider easing this one — your last few runs have been costly. " to the rendered rationale.
   - Also set a flag in the template context `is_fatigue_softened: True` so the UI can render a small icon.
4. This is a *display-time* hint only. Does **not** mutate `DailyWorkout.distance_km` (that's 5.1's job).

**Tests.**
- `tests/test_template_context.py` (new or extend): seed 3 runs with effort=8, 9, 8 and matching warning feedback → today's tempo gets the prefix.
- Negative: easy workout today → no prefix even if same signal.

**Migration.** None.

**Rollback.** Revert template-context file.

**Effort: S (~1 day).**

---

### Sprint 3 ship checklist

- [ ] Alembic migration for `users.auto_adjust_enabled` deployed on Fly volume DB
- [ ] Toggle UI live in user settings, tested with both `True` and `False`
- [ ] One real end-to-end Strava sync produces auto-adjust on a staging plan
- [ ] Push notification dispatched (or gracefully no-op if not configured)
- [ ] Verify throttle: two runs in 1h do not re-adjust twice
- [ ] Verify "yesterday hard → today easy" prefix renders correctly on plan page
- [ ] Verify fatigue-softened prefix renders only for quality workouts

---

## Critical files referenced (single index)

| File | Used in items |
|------|---------------|
| `app/services/adaptation/signal_computer.py` | 2.1, 2.2, 3.1 |
| `app/services/adaptation/plan_adjuster.py` | 2.1, 3.1 |
| `app/services/adaptation/recommendation_evaluator.py` | 5.1 |
| `app/services/adaptation/vdot_recalibrator.py` | 3.3, 4.1 |
| `app/services/adaptation/__init__.py` (facade) | 5.1 |
| `app/services/runs/run_enrichment_service.py` | 3.3 |
| `app/services/integrations/strava_post_sync_service.py` | 3.3, 5.1 |
| `app/services/fitness/training_load_service.py` | 3.1 (read-only) |
| `app/services/plans/plan_template_context.py` | 4.1, 5.3, 6.3 |
| `app/core/coaching/coaching_notes_generator.py` | 5.3 |
| `app/routers/runs.py` | 3.3, 5.1 |
| `app/routers/readiness.py` | 2.1 (read-only — existing single-day swap stays) |
| `app/models/run_log.py` | 2.2 (read-only) |
| `app/models/readiness_log.py` | 2.1 (read-only) |
| `app/models/weekly_plan.py` | 4.1 (migration) |
| `app/models/user.py` | 5.1 (migration) |

---

## Verification plan

End-to-end smoke test on a staging plan with seeded data, after all three sprints ship:

1. Create a plan, mark `auto_adjust_enabled = True`.
2. Log 3 morning `ReadinessLog` entries with scores 35, 40, 38 (low) over 3 consecutive days.
3. Log 3 tempo runs in those days with `perceived_effort = 9` each, paces 5 sec/km slower than target.
4. Expect, after the third run is logged:
   - `signal_computer` output: `readiness_factor < 0.95`, `effort_factor < 0.95`, `tsb_form` ∈ {`overreached`, `loaded`}, `quality_drift_modifier ≤ 0`.
   - `apply_or_park` selects "high confidence" path, calls `adjust_plan`, multiplier ≤ 0.92.
   - `adaptation_history` shows `type: "auto_adjust"` event.
   - Plan page next-7-days view shows reduced distances, and `pace_zones_updated_at` is fresh (from a parallel VDOT bump if any).
   - Today's workout card prefix reads "Consider easing this one…"
   - Tomorrow's coaching note prefix reads "After yesterday's hard tempo, …"
   - Push notification fired (or no-op if not configured).

5. Snapshot regression: run the new pipeline against 5 real production plans and document the multiplier deltas vs. the previous pipeline. Reject the deploy if any plan moves by more than 10 % in multiplier — that signals an over-eager weight.

6. **Production DB queries** (per saved memory — use Fly DB for user-facing debugging):
   ```text
   fly ssh sftp shell -a runcoach
   get /data/runcoach.db local.db
   sqlite3 local.db "SELECT plan_id, multiplier, adjustment_multiplier, last_adjusted_at FROM training_plans WHERE last_adjusted_at > date('now', '-7 days');"
   ```

---

## What we explicitly are *not* doing

- No HRV, HealthKit, Garmin Connect, or any other third-party data source. Strava only.
- No nutrition feedback loop changes (`app/core/nutrition/` untouched).
- No new wearable streams or split/lap ingestion (that's P3).
- No LLM-driven coaching (that's P4).
- No re-design of the existing `POST /api/readiness/adapt` single-day-swap endpoint — it keeps working as is.
- No changes to VDOT math, phase distributions, the 10 % cap, the curated key-workout library, the beginner generator, or the race predictor's outlier filter.

The improvements layer around the working core — they do not replace it.
