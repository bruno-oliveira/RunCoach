# RunCoach Code Quality Improvements

## Scope and intent

A code-quality review across **maintainability**, **extensibility**, **readability**, and **security**. Strictly structural — driven by SRP, DRY, low coupling, OWASP basics.

**Complementary, not overlapping** with:
- `CORE_IMPROVEMENTS.md` — domain/training correctness (signals, VDOT, pace zones).
- `P1_P2_PLAN.md` — execution roadmap for the domain work.

If a recommendation here changes *training behavior*, it does not belong in this file. Items below change *code shape*, *blast radius*, or *attack surface* only.

Findings were collected by four parallel review passes and then deduped, reranked by impact × effort, and trimmed. Each finding is concrete (file:line), with a short fix and the payoff after it lands. Total: 28 findings.

---

## Top wins (high impact, low effort)

The five items that compound the most across the codebase — start here.

### T1. Centralize `current_week` computation
**Where:** canonical helper exists at `app/services/plans/plan_date_utils.py:24` but inline duplicates live in `app/services/adaptation/plan_adjuster.py:70`, `recommendation_evaluator.py:58,227`, `alert_checker.py:39-44`, `recalibrator.py:38`, `type_swapper.py:96`, `vdot_recalibrator.py:56`, `run_mapper.py:133`, `missed_week_handler.py:33`, `routers/plan_list.py:59`, `services/plans/plan_view_service.py:99`, `services/plans/week_adjustment_service.py:117` (15+ call sites).
**Problem:** `(today - start).days // 7 + 1` is rewritten everywhere with subtly different clamps (`max(1, …)`, `min(…, total_weeks)`, pre-start handling).
**Fix:** Extend `compute_current_week` with `clamp_to_total: bool` and `pre_start_default: int | None` kwargs; replace every inline computation with a single call. Add a unit test fixing the off-by-one and timezone edge cases.
**Payoff:** One place to fix timezone, pre-start, and post-end edge cases; eliminates a class of off-by-one bugs across the adaptation pipeline.

### T2. Extract per-signal helpers from `compute_adjustment_signals`
**Where:** `app/services/adaptation/signal_computer.py:41` (~330-line function).
**Problem:** One function fuses six independent signal computations (volume, effort, HR, feedback, readiness, mountain), reweighting, three overreach branches, TSB clamps, hysteresis, and the assembly of a 45-field return dict. Hard to scan, hard to test, hard to add the next signal.
**Fix:** One `_compute_<signal>_factor()` per signal returning a small dataclass `(factor, weight_used, debug)`, plus `_apply_overreach_clamps()` and `_assemble_result()`. Top-level becomes a ~30-line dispatcher.
**Payoff:** Each signal becomes independently testable and tweakable; CORE_IMPROVEMENTS' planned signal additions stop being a merge-conflict minefield.

### T3. Make key workouts self-contained records
**Where:** `app/core/training/key_workout_library.py:92-331` (`_DISTANCE_REWRITES`), `:334-361` (`_STRUCTURE_REWRITES`), `:452-458` (`_KEY_WORKOUT_MIN_DISTANCE_KM`), `:461-468` (bracket restrictions); the `_`-prefixed dict is even cross-imported in `app/services/plans/plan_data_enricher.py:10`.
**Problem:** Each key workout's rendering logic is split across 4 dicts in 3 files. Adding one workout requires up to 4 simultaneous edits, and downstream code reaches across a private import.
**Fix:** Move `description_template` (callable), `structure_template`, `min_distance_km`, and bracket restrictions *into the workout dict itself* in `key_workout_data.py`. Replace `_DISTANCE_REWRITES.get(workout_id)` with `workout.get("render_description")`.
**Payoff:** New key workout = one self-contained record. Kills the cross-file private import in `plan_data_enricher.py`.

### T4. Bind the anonymous-user cookie to a server-side secret
**Where:** `app/middleware.py:78-101` (cookie is a raw UUID4), `app/services/plans/merge_service.py:31-72` (account merge), `app/routers/plan_sharing.py:142-169` (plan claim).
**Severity:** medium-high (preconditions: attacker must obtain the victim's anonymous UUID via log leak, shared device, or other disclosure — `app/routers/plan_generation.py:117-124` logs it at INFO, see S5 below).
**Problem:** The anonymous cookie is unsigned, so its value alone is sufficient to authenticate as that anonymous identity. `MergeService.merge_anonymous_user` only refuses when the anon row has `google_id or email` — which anonymous rows always fail. An attacker holding a victim's cookie value can log in and absorb the victim's plans/runs/recipes into the attacker's Google account; the plan-claim endpoint has the same root cause.
**Fix:** Sign the cookie with `HMAC(SECRET_KEY, anon_id)` and verify on every read, OR store a server-side mapping `(cookie_id → anon_user_id)` with the cookie holding a server-issued opaque token. Reject cross-binding attempts. Stop logging the raw cookie value.
**Payoff:** Closes a no-auth horizontal takeover of orphan data and a quiet account-merge hijack.

### T5. Name the magic numbers in adaptation
**Where:** `app/services/adaptation/signal_computer.py:122,152-161,205-214,230,253-260,307-348`; cross-file repeats in `recommendation_evaluator.py:110-116`.
**Problem:** The deep adaptation math is full of bare literals: `0.85 / 1.10` effort clamp, `0.25 / 9.0` slope, `0.90/0.95/1.02/1.05` HR factors, `0.92/0.96/1.02/1.05` feedback factors, `0.92 + readiness_pct * 0.13`, `-25 / -10 / 5 / 10` TSB cutoffs. Same numbers appear in `recommendation_evaluator.py` with different meaning.
**Fix:** Lift to named module constants (`_HR_FACTOR_HARD_OVER`, `_TSB_OVERREACHED`, `_EFFORT_TREND_HIGH_RPE`, …). Group them at the top of the file so threshold drift across files is visible.
**Payoff:** A future tuner reads intent at the call site instead of decoding a number; cross-file inconsistencies become greppable.

---

## Maintainability (SRP, DRY)

### M1. Two plan generators duplicate the same weekly-schedule logic
**Where:** `app/core/generators/performance_plan_generator.py:122-253` and `app/core/generators/fitness_plan_generator.py:161-306`.
**Problem:** `_generate_weekly_plan` is reimplemented twice with near-identical bodies — long run on day 6, quality-day picks (2/4), `_spacing_score`, `_would_create_three_consecutive`, rest-fill, key-workout overlay, coaching-note loop. The Fitness variant silently skips `enforce_week_caps` and `_validate_week_plan` — exactly the drift duplication produces.
**Fix:** Extract `WeeklySkeletonBuilder` in `app/core/generators/` next to `weekly_plan_builder.py`. It accepts a `QualityTypeResolver` + `WorkoutGeneratorMap` and produces the day-keyed schedule. Both generators shrink to ~80-line classes declaring only phase metadata, priorities, and zone calculation.
**Payoff:** One place to fix spacing/recovery bugs; adding a third plan type stops copy-pasting 130 lines.

### M2. `plan_view` router does business logic that belongs in a service
**Where:** `app/routers/plan_view.py:98-159`.
**Problem:** The router instantiates `PerformancePlanGenerator` and `FitnessPlanGenerator`, calls `calculate_training_zones`, formats paces, computes phase durations, scans `plan_data` for time-trial weeks, and builds `vdot_zones` — all wrapped in two anonymous `except Exception`s that swallow failures.
**Fix:** Move both blocks into `PlanViewService.get_plan_view_data` (or a new `plan_type_context.py` helper keyed on `plan_type`). The router just passes `plan_type` and receives a finished context dict. Errors join the `partial_errors` list already in `plan_view_service.py:76`.
**Payoff:** Adding a new plan type stops requiring a router edit; partial-error handling becomes uniform.

### M3. `plan_data_enricher.py` owns three unrelated responsibilities
**Where:** `app/services/plans/plan_data_enricher.py:1-301`.
**Problem:** 300 lines in one file: (a) step repair / distance reconciliation for key workouts (44-189), (b) nutrition format conversion (192-265), (c) run/feedback DB lookups (268-300). It also reaches into private symbols `_compute_distance_from_steps`, `_parse_pace_str_to_min_per_km` from `workout_steps.py`.
**Fix:** Split into `key_workout_repair.py`, `nutrition_view_adapter.py`, `plan_run_lookups.py`. Promote the two `workout_steps` helpers to public names so the import surface is honest.
**Payoff:** Each module has one reason to change; the nutrition reshape stops hiding under a workout-related file name.

### M4. Parallel implementation of week overrides via Form-based `customize-plan`
**Where:** `app/routers/plan_generation.py:411-457` and `app/services/plans/plan_adjustments.py:1-143` (`adjust_intensity`, `swap_workout`, `adjust_distance`, `apply_ai_suggestions`).
**Problem:** This is a duplicate week-override pipeline. Strings like `"more_speed"` / `"more_endurance"` mutate `plan_data` in place, bypassing the modern `apply_week_action` flow in `week_adjustment_service.py:50` that handles baselines, safety, and `adaptation_revision`. Sole caller is `app/static/js/plan/plan_core.js:64`. The two systems can produce contradictory state.
**Fix:** Migrate the JS caller to the JSON `/api/plan/{id}/week/{n}/override` endpoint. Then delete `customize-plan`, `PlanService.customize_plan`, `plan_lifecycle_service.customize_plan`, and `plan_adjustments.py`.
**Payoff:** One mutation path for week-level changes; ~200 LoC and one router handler removed.

### M5. `_run_adjust` mixes orchestration, prose, logging, and persistence
**Where:** `app/services/adaptation/plan_adjuster.py:223-476` (~250 lines).
**Problem:** Early-return logic, before/after snapshot, ~150-line `reason_parts` headline-prose builder, multi-line `logger.info`, and the commit path all live in one function. `direction` vs `verb` are computed twice with subtly different rules (lines 338 and 351-356). Headline-string assembly parallels similar code in `recommendation_evaluator._run_accept` and `_build_auto_adjust_reason`.
**Fix:** Extract `_early_return_when_no_signals()`, `_build_headline_reason(signals, vdot_result, current_week)` into a new `change_reasons.py`, and `_persist_adjustment(...)`. Drop unused `direction`.
**Payoff:** Control flow drops to ~60 lines; the prose builder becomes unit-testable without a `Session`; copy/i18n changes stop requiring edits to the mutation service.

### M6. Distance-display fallback duplicated, plus 6 parallel distance→name maps
**Where:** Display fallback at `app/routers/plan_list.py:46-53`, `plan_sharing.py:124-132`, `analytics_pages.py:41-45`; distance-name maps at `app/constants.py:7-13` (canonical), `core/training/vdot_calculator.py:11-12`, `services/fitness/race_predictor_service.py:575-577`, `services/fitness/readiness_service.py:34-40`, `services/fitness/personal_records_service.py:18-21`, `services/runs/completion_stats.py:13-39`. Several disagree on Half (21.1 vs 21.0975) and Marathon (42.2 vs 42.195).
**Fix:** Add `format_plan_distance_label(plan) -> str` in `app/services/plans/plan_helpers.py` and use it everywhere; make `app/constants.DISTANCE_NAMES` and `RaceProfile.display_name` the single source for distance → name; add a `closest_distance(km)` helper for fuzzy match. Consider exposing `TrainingPlan.target_distance_display` as a `@property`.
**Payoff:** Adding a distance or renaming Half Marathon happens in one place; naming drift disappears.

### M7. Dead imports and parallel `race_predictor` modules
**Where:** Dead: `app/core/generators/performance_plan_generator.py:19,25` and `fitness_plan_generator.py:15,20` (`KeyWorkoutLibrary`, `format_pace as _shared_format_pace`). Parallel: `app/core/training/race_predictor.py` (254 LoC) lives alongside `app/services/fitness/race_predictor_service.py` (663 LoC); the former is reached only via lazy imports inside `vdot_calculator.py:149,316,330,347`.
**Fix:** Delete the four dead imports. Decide whether `race_predictor.py` is the low-level math layer (rename to `vdot_predictions.py`) or fold it into `vdot_calculator.py`.
**Payoff:** Stops the "which race predictor is canonical?" confusion; cleaner import graph.

---

## Extensibility

### E1. Per-distance settings fanned out instead of a registry
**Where:** `app/config.py:32-49,80-131` — five `*_5k`, `*_10k`, `*_half`, `*_30k`, `*_marathon` blocks for min/max weeks, min/max mileage, perf-min, and per-distance user-facing messages. Mirrored by lookup dicts in `app/schemas/plan_schemas.py:46-77,285-314,625`.
**Problem:** Adding a new race distance (50K, 5-mile) requires editing `config.py` plus every reassembling lookup dict in the schemas.
**Fix:** A single `DISTANCE_CONSTRAINTS: dict[float, DistanceConstraints]` (pydantic model) in `app/config.py`, owned by the `RaceProfile` from `app/core/race/race_profiles.py`. Drop the 20+ scalar fields; iterate the registry in `_MILEAGE_CONFIG` and `min_weeks_requirements`.
**Payoff:** Adding a new road distance = one registry row, not ~12 scalar fields.

### E2. `plan_type` is a stringly-typed dispatch branched in 6+ files
**Where:** `app/routers/plan_view.py:98,119`, `plan_list.py:48,50`, `plan_sharing.py:127,129`, `analytics_pages.py:42,44`; `app/core/export/pdf_plan_pages.py:20-21,94-95`; `app/services/fitness/fitness_service.py:87`.
**Problem:** Adding a fourth plan type (e.g. `c25k`, `triathlon`) requires touching every router and the PDF generator with another `elif`. Each branch instantiates its own generator inline (`plan_view.py:101-123`) — pure shotgun-edit pattern.
**Fix:** Introduce a `PlanTypeHandler` registry with `get_view_context(plan)`, `get_zones(plan)`, `get_pdf_section(plan)`. Routers call `HANDLERS[plan.plan_type].get_view_context(...)`. Register `RoadPlan`, `PerformancePlan`, `FitnessPlan` once.
**Payoff:** New plan type = one class registration; routers and PDF code stop branching.

### E3. `app/core/runner_profile.py` violates the core/services boundary
**Where:** `app/core/runner_profile.py:11,14-16` imports `sqlalchemy.orm.Session`, `app.models.RunLog`, `app.services.fitness.race_predictor_service`, `app.services.fitness.training_load_service`.
**Problem:** `app/core/` is the pure domain layer, but this module pulls in services and SQLAlchemy. Causes circular-import risk and makes `RunnerProfile` untestable without a DB.
**Fix:** Move `runner_profile.py` to `app/services/fitness/`. `core` keeps only the dataclass; the service assembles it from runs and other services.
**Payoff:** `app/core/` becomes pure library code — importable from a worker, CLI, or notebook without the FastAPI app.

### E4. PDF generator hardcoded to the SQLAlchemy `TrainingPlan`
**Where:** `app/core/export/pdf_generator.py:13,62`, `pdf_plan_pages.py:11,18,90,311,345`, `pdf_nutrition_pages.py:9,120`.
**Problem:** Every PDF mixin accepts a `TrainingPlan` ORM object directly. A second template, an HTML export, or a sharable PDF without a user cannot reuse the renderer.
**Fix:** Define `PlanExportDTO` (dataclass / TypedDict). Routers convert `TrainingPlan → DTO` once. PDF mixins consume the DTO; the `TrainingPlan` import disappears from `core/export/`.
**Payoff:** Lets you add a second template, ICS export, or markdown export without recoupling each to ORM. Makes the PDF unit-testable from fixtures.

### E5. No data-source abstraction — Strava is hardwired
**Where:** `app/services/integrations/strava_post_sync_service.py`, `strava_service.py`, `app/routers/strava.py`, plus hooks in `app/routers/runs.py:111-117` and `app/services/runs/run_enrichment_service.py`.
**Problem:** No `ActivityProvider` interface; the integration grows its own `*_post_sync_service`. Adding Garmin / HealthKit / Polar / CSV import would duplicate the sync → enrich → adapt wiring.
**Fix:** Define an `ActivityProvider` protocol (`fetch_recent_activities()`, `to_run_log(activity)`) and an `ActivityIngestPipeline` running the common post-ingest enrichment. Strava becomes one implementation.
**Payoff:** Adding a second source = one class, not a copy of `strava_post_sync_service.py`.

### E6. Routers issue ad-hoc ORM queries that belong in services
**Where:** `app/routers/runs.py:48-56,108-118,175,311,334`; `readiness.py:56,105,126,186,200,255,264`; `plan_adjustments.py:400-413`; `plan_view.py:82-115`.
**Problem:** Routers run cross-table `db.query` joins and import `AdaptationService` inline mid-handler. Ownership checks are inlined repeatedly instead of routed through services or the existing `validate_plan_ownership` dependency.
**Fix:** Move all `db.query` cross-table joins into the corresponding service (`RunService`, `ReadinessService`, `PlanAdjustmentsService`). Use `validate_plan_ownership` consistently. Import services at module top.
**Payoff:** Routes become thin HTTP adapters; query optimization (indexes, eager loading) happens once per domain.

---

## Readability

### R1. Four near-identical "verdict ladder" blocks in gap analysis
**Where:** `app/services/fitness/gap_analysis_service.py:267,321,367,417,450`.
**Problem:** Each `_compute_*_gap` hand-rolls `on_track / close / behind / far_behind` based on a `deficit_pct` cutoff, with thresholds as bare literals.
**Fix:** `VERDICT_BANDS = {"volume": (5,15,30), "elevation": (10,30,50), ...}` + a `verdict_for(deficit_pct, band)` helper.
**Payoff:** Thresholds become a single tunable table; four sites collapse to one line each.

### R2. Verbose interval-step builders with copy-pasted bodies
**Where:** `app/core/training/workout_steps.py:462-580`.
**Problem:** Each variant arm in `_build_interval_steps_high_base` / `_low_base` repeats the same warmup → run-step → recovery → cooldown shape, only varying rep distance, count, and pace zone — ~120 lines of near-duplication.
**Fix:** A small `_interval_set(rep_distance_m, count, zone, *, recovery, pace_zones)` builder. Each variant arm becomes a one-line call.
**Payoff:** Tuning or adding an interval variant becomes changing a tuple instead of a six-line block.

### R3. `_compute_effort_trend` thresholds are magic literals
**Where:** `app/services/adaptation/signal_computer.py:127-133,469-480`.
**Problem:** `trend_modifier` dict keys against function results; threshold `1.0` rise / fall is a magic literal at lines 476/478. `mid_point` divides cleanly only on even-length samples — readers must verify.
**Fix:** `_EFFORT_TREND_RISE_RPE = 1.0`, `_EFFORT_TREND_FALL_RPE = -1.0`; a one-line docstring noting half-split semantics.
**Payoff:** Trend rules are visible, tweakable, self-documenting.

### R4. `SignalSummary` dataclass for `signals` access
**Where:** `app/services/adaptation/plan_adjuster.py:330-396`; same pattern in `recommendation_evaluator.py:105-119`.
**Problem:** ~20 sequential `signals.get("xxx", default)` calls obscure which keys are required vs optional and bury typos as silent `None`s.
**Fix:** Have `compute_adjustment_signals` return a `SignalSummary` dataclass (or `TypedDict`); callers do `s.volume_ratio` and a type checker catches missing fields.
**Payoff:** Refactor-safe access, IDE autocomplete, single source of truth for the signals contract.

### R5. `get_race_history` mixes querying, windowed math, and view shape
**Where:** `app/services/fitness/race_predictor_service.py:465-569`.
**Problem:** ~100-line method does DB fetch + rolling-window VDOT median + prediction-vs-actual comparison + view-model assembly + accuracy aggregation. `WINDOW_WEEKS = 12` is declared mid-function (line 489) inconsistent with the file's top-of-module constants.
**Fix:** Extract `_rolling_vdot_for_run(prior_vdots, run_ts)` and `_build_history_entry(run, rolling_vdot)`. Promote `WINDOW_WEEKS` to a module constant alongside `TOP_N_VDOTS`.
**Payoff:** Each step testable in isolation; the body reads as a clear three-step pipeline.

---

## Security

Anonymous-cookie hardening already covered in **T4**. Severities reflect realistic attack preconditions, not worst-case theory.

### S1. Rate limiter trusts unverified `X-Forwarded-For`
**Where:** `app/rate_limit.py:18-21`.
**Severity:** medium.
**Problem:** `_client_ip` accepts the first value of `X-Forwarded-For`. Fly's proxy does set it, but if the client also sends one (and it's not stripped), the attacker controls it. Result: rotate the header per request to bypass 10/min on `/api/auth/google`, 5/min on `/api/strava/callback`, and the 3/hour account-deletion limiter.
**Fix:** Use `Fly-Client-IP` (Fly always sets this), or read the *last* trusted hop in `X-Forwarded-For` rather than the first.
**Payoff:** Restores brute-force / abuse protection on auth endpoints.

### S2. Fernet key derived via plain SHA-256, no KDF, no version byte
**Where:** `app/models/encrypted_type.py:15-18`.
**Severity:** medium.
**Problem:** `_derive_fernet_key` does `urlsafe_b64encode(sha256(secret))`. Fernet is AEAD so live confidentiality is fine, but: (a) a weak operator-chosen `ENCRYPTION_KEY` isn't stretched — offline brute-force on a leaked DB is cheap; (b) no key-version byte means rotation requires re-encrypting every column.
**Fix:** Use `cryptography.hazmat.primitives.kdf.hkdf.HKDF` with a fixed app-salt; prepend a 1-byte key-version to ciphertext for future rotation.
**Payoff:** Limits damage from a leaked DB + low-entropy key; unlocks safe key rotation.

### S3. JWT lacks `iss` / `aud`, session and OAuth-state share the same secret
**Where:** `app/services/auth/auth_service.py:29-45`.
**Severity:** medium.
**Problem:** Session JWTs and Strava OAuth `state` JWTs are both HS256-signed with `SECRET_KEY`; `pyjwt.decode` is called without `audience=` or `issuer=`. Only an unenforced `purpose` field separates them. If `SECRET_KEY` ever leaks or is reused, the contexts can be cross-replayed.
**Fix:** Add `iss="runcoach"` and `aud` (`"session"` vs `"strava_state"`) in `create_access_token`; pass `audience=` and `issuer=` to every `pyjwt.decode`. Reject session lookups whose `aud != "session"`.
**Payoff:** Defense-in-depth against cross-context token reuse.

### S4. `GET /api/strava/callback` writes state without origin check
**Where:** `app/middleware.py:106-128` (CSRF only on POST/PUT/PATCH/DELETE), `app/routers/strava.py:43`.
**Severity:** medium.
**Problem:** The endpoint writes the user's Strava tokens and triggers a `BackgroundTask` initial sync, but CSRF middleware skips GET. The `state` JWT prevents purely cross-origin forgery, but combined with any open redirect / phish that surfaces a valid `code`+`state`, an attacker can trigger writes.
**Fix:** On `/strava/callback`, require the `state` JWT's user-id to match the logged-in session cookie. Treat any GET that mutates state as origin-restricted.
**Payoff:** Closes a CSRF sidewise surface around the OAuth callback.

### S5. Anonymous-cookie endpoints log raw cookie values at INFO
**Where:** `app/routers/plan_generation.py:117-124`.
**Severity:** low.
**Problem:** `logger.info` writes the raw `anonymous_user_id` UUID and a boolean for `access_token` presence. Combined with **T4**, any log leak hands an attacker the value needed to take over the corresponding anonymous data.
**Fix:** Drop these debug lines or mask the UUID (`first 4 chars + "..."`).
**Payoff:** Reduces blast radius of any log disclosure.

### S6. CSP allows `'unsafe-inline'` for scripts
**Where:** `app/middleware.py:17-29`.
**Severity:** low.
**Problem:** `script-src 'self' 'unsafe-inline'` defeats CSP's primary value — any future stored/reflected HTML injection becomes executable. Today autoescape is on and there's no `|safe`, but this is a tripwire waiting to fire.
**Fix:** Move inline bootstrap scripts to external files or use nonce-based CSP (`'nonce-<rand>'` per request).
**Payoff:** Real XSS mitigation if a future template change ever bypasses autoescape.

### Verified OK during the review
- **SQL injection:** no raw SQL surface — only `.execute()` calls are PRAGMA literals in `dependencies.py:41-46`; all data queries go through SQLAlchemy ORM filters.
- **Templates:** no `|safe`, autoescape on by default.
- **Cookie flags:** every `set_cookie` (auth.py:65, middleware.py:94) sets `httponly`, `samesite="lax"`, and `secure` (gated by `force_secure_cookies and not debug`).
- **Google ID-token verification:** RS256, JWKS-pinned by `kid`, `audience=GOOGLE_CLIENT_ID`, issuer whitelist (`auth_service.py:85-91`).
- **Strava `scope`:** correctly never validated from the token body (matches the known caveat).
- **Production secret hygiene:** `main.py:_validate_production_secrets` rejects weak `SECRET_KEY`, requires a separate `ENCRYPTION_KEY`, and refuses startup if they match.
- **Container:** Dockerfile runs as non-root `appuser`; `/data/pdf_cache` 0700; `force_https=true` in fly.toml; HSTS on non-debug responses.

---

## Explicitly out of scope

- **Any change to training behavior** — see `CORE_IMPROVEMENTS.md` and `P1_P2_PLAN.md`.
- **`signal_computer.py` further splitting beyond T2/R3/R4** — CORE_IMPROVEMENTS' Sprint 1 is actively adding signals there; deeper refactors would conflict.
- **`strava_service.py` split** — 380 LoC, but a single cohesive OAuth+sync responsibility; not worth disturbing.
- **Splitting `key_workout_library.py` / `key_workout_data*.py` size** — these are data tables, length is appropriate (logic split is T3 above).
- **`phase_calculator.py:83-105` per-distance phase distribution** — clean dispatch already; CORE_IMPROVEMENTS §4.2 proposes the next axis here.
- **Cosmetic items**: trailing whitespace, import ordering, single-letter loop vars in short blocks, docstring punctuation.
- **`adaptation_history` `direction` rename** — persisted in stored JSON; rename ripples into data, not worth the churn.
