# RunCoach Code Review: Improvements Checklist

Reviewed: 2026-03-29. Focus: correctness, edge cases, security, UI, modularity, testability.
Methodology: 5 parallel review agents (core logic, API layer, models/services, frontend/UI, tests/infra) + dedup/merge pass.

---

## 1 -- Security (Critical / High)

- [x] **`secret_key` regenerates on every Fly.io cold start** (`config.py:52`). `default_factory=lambda: secrets.token_urlsafe(32)` produces a new key each time the machine wakes from `auto_stop_machines='stop'`, invalidating all existing JWTs/sessions. Fix: set `SECRET_KEY` as a persistent Fly.io secret.

- [x] **Strava tokens stored in plaintext** (`user.py:22-23`). `strava_access_token` and `strava_refresh_token` are plain strings. Encryption at rest would be better practice.

- [x] **XSS in `readiness.js` innerHTML** (`readiness.js:33,57,82-84,125-129`). Server-provided strings (`overall_label`, `distance_label`, `comp.detail`, `s.description`, etc.) are interpolated directly into `innerHTML` without escaping. Fix: use `escapeHtml()` (already exists in `plan.js`) or build DOM nodes with `textContent`.

- [x] **Strava OAuth state token valid for 24h** (`routers/strava.py:88-92`). The JWT state has no short expiry, creating a CSRF replay window. Fix: pass `expires_delta=timedelta(minutes=5)` when minting.

- [x] **Latent authorization bypass in `get_plan_or_404`** (`routers/plan_helpers.py:66`). When `require_user_match=True` but `current_user` is `None`, the ownership check is skipped. Not currently triggerable but fail-unsafe. Fix: raise 403 when `current_user is None` and `require_user_match=True`.

- [x] **Raw SQLAlchemy exception message exposed in `/randomize-meals` 500 response** (`routers/nutrition.py:97-101`). `str(e)` may contain table names, column names, and SQL fragments. Fix: return a generic message and log the original.

---

## 2 -- Correctness: Critical Bugs

- [x] **`current_km=0` with Half Marathon/Marathon/Trail produces all-zero weekly plans** (`plan_generator.py:957-979,1111`). The beginner-plan shortcut only fires for 5K/10K. For longer distances, `_calculate_weekly_progression(current_km=0)` sets `high_water=0`, and `_apply_10pct_cap(ideal, 0)` returns 0 for every base/build week. Fix: extend the beginner guard or raise `InadequateBaseException` for unsupported 0-mileage distances.

- [x] **`NameError` crash in `generate_performance_plan` error handlers** (`routers/performance.py:205,257,283`). `goal_pace` is assigned inside the `try` block. If `_parse_time_to_pace` raises `ValueError`, both `except` handlers reference `goal_pace` which was never assigned, causing a secondary `NameError` masked by `except Exception`. Fix: initialize `goal_pace = None` before the `try`.

- [x] **Unguarded `json.loads` on nullable `plan_data` fields** (`plan_service.py:134,276`, `adaptation_service.py:79`, `performance_service.py:359,401,460`). `plan_data`, `nutrition_plan_data`, `hr_zones_data`, `nutrition_phases_data`, and `race_protocol_data` are all nullable `Text` columns. `json.loads(None)` raises `TypeError`. Fix: use `json.loads(x) if x else []` consistently (pattern already exists in `readiness_service.py`).

- [x] **`workout["notes"].replace()` crashes when notes is `None`** (`plan_service.py:615-625`). `_adjust_intensity` calls `.replace()` on `workout["notes"]`, but `DailyWorkout.notes` is nullable. Fix: `notes = workout.get("notes") or ""`.

- [x] **`_adjust_distance` produces negative distances** (`plan_service.py:670-677`). When `distance_change` exceeds `current_total`, `ratio` goes negative and all workout distances become negative, persisted to DB. Fix: `ratio = max(0.0, (current_total + distance_change) / current_total)`.

- [x] **`float(target_distance)` crashes on non-numeric stored values** (`performance_service.py:370`, `pdf_generator.py:238`). `target_distance` is a `String` column; legacy data could contain `"Trail Running"`, `""`, or `None`. Fix: use the existing `_parse_float()` utility or `try/except`.

- [x] **Lambda closure-in-loop bug: all quality workouts get the same type** (`performance_plan_generator.py:719-730`). Python lambdas capture variables by reference. When `quality_workouts_needed >= 2`, both generators point to the last iteration's `workout_type`. Fix: capture via default arguments or use `functools.partial`.

---

## 3 -- Correctness: High-Priority Bugs

- [x] **`_validate_week_plan` is a no-op** (`plan_generator.py:1071-1082`). The validator receives `actual_total_km` (computed from workouts) as `total_km`, then re-computes the same sum and compares -- always passes. Fix: pass the original target `week_km` from `weekly_progression`.

- [ ] **Very low mileage (1-3 km/week) for long distances: long run minimum exceeds weekly budget** (`plan_generator.py:975-979`). For a marathon, `target_distance * 0.25 = 10.5 km` long-run minimum exceeds the total weekly km of ~1.1 km. Fix: add minimum base mileage check for longer distances, consistent with `config.py` constraints.

- [x] **`body_weight=0` produces zero-calorie nutrition plan, cached permanently** (`nutrition_engine.py:14,27`). `base_calories = 0 * 22 = 0`. The `lru_cache` then poisons future calls. Fix: `if body_weight <= 0: raise ValueError(...)`.

- [x] **Negative `taper_weeks` risk in performance plan** (`performance_plan_generator.py:228-242`). Phase allocation uses `max()` floors that can sum to more than `weeks`. No guard on `taper_weeks = weeks - sum(others)`. Fix: `taper_weeks = max(0, ...)`.

- [x] **Single-run edge case gives wrong weekly average** (`adaptive_plan_generator.py:61`). With one run, `weeks_span=1`, treating one run's distance as full-week volume. A 5 km run = "5 km/week". Fix: flag single-run data as low-confidence or return no-data default.

- [x] **Partial flush-then-commit in `create_plan` with no rollback** (`plan_service.py:160-255`). Multiple `db.flush()` calls; if HR-zone injection fails after the first flush, the session is dirty. Fix: wrap entire body in `try/except` with `db.rollback()`.

- [x] **`FavoriteRecipe` and `TriathlonPlan` missing cascade on User delete** (`models/__init__.py:36-40`). `FavoriteRecipe.user_id` is `nullable=False`; deleting a user raises `IntegrityError`. Fix: add `cascade="all, delete-orphan"`.

- [x] **`merge_anonymous_user` leaves `RunFeedback`, `FavoriteRecipe`, `TriathlonPlan` orphaned** (`merge_service.py:44-68`). Only `TrainingPlan` and `RunLog` are re-parented. Fix: re-parent or delete all related rows before `db.delete(anonymous_user)`.

- [x] **FK columns `WeeklyPlan.training_plan_id` and `DailyWorkout.weekly_plan_id` missing `nullable=False`** (`weekly_plan.py:14`, `daily_workout.py:14`). Orphaned rows with `NULL` FK can be silently created.

- [x] **`PlanCustomization` FK and payload columns missing `nullable=False`** (`plan_customization.py:12-15`). Half-formed customization records can be persisted.

- [x] **`get_logged_runs_map` dict silently drops all-but-last run per workout** (`plan_service.py:494-498`). Dict comprehension keeps only the last run per `daily_workout_id`. Fix: sort by `date.desc()` and keep first, or disallow duplicates at the model level.

- [x] **`customize_plan` swallows `HTTPException` from service layer as 200** (`routers/plans.py:243-263`). `except HTTPException: raise` only covers `get_plan_or_404`; service-layer HTTPExceptions become 200 with error string. Fix: propagate all `HTTPException` before the generic handler.

- [x] **`/api/recipes` has no Query bounds** (`routers/recipes.py:110-119`). `page=0` gives negative slice index (returns last N recipes); `page_size=10000` loads entire dataset. Fix: `page: int = Query(1, ge=1)`, `page_size: int = Query(50, ge=1, le=200)`.

- [x] **`bulk_insert_mappings` deprecated and skips `baseline_distance_km`** (`performance_service.py:338-340`). Performance-created plans lack `baseline_distance_km`, forcing a backfill query on every adjustment. Fix: use ORM `db.add_all()` with explicit field.

---

## 4 -- Correctness: Medium-Priority Bugs

- [x] **`generate_phased_nutrition_plan` returns `{}` for beginner plans** (`nutrition_engine.py:132-137`). Beginner plans use `phase="beginner"` which is not in `phase_weeks`. Fix: add fallback for unrecognized phases.

- [x] **All Couch-to-5K weeks report `total_km=0`** (`beginner_plan_generator.py:99-107`). Propagates into nutrition calculations as `peak_km=0`, halving nutrition targets. Fix: compute estimated `total_km` from `base_duration` and assumed pace.

- [x] **`_calculate_phases` can decrement `peak` to 0** (`plan_generator.py:111-120`). While-loop trimming overage has no floor on `peak`. For very short plans, result is a plan with no peak phase.

- [x] **`rest_days` can go negative if `max_runs > 6`** (`plan_generator.py:266`). `7 - (max_runs + 1)` with `max_runs=7` gives `-1`. Fix: `max_runs = min(max_runs, 6)`.

- [x] **VDOT binary search returns unconverged result silently** (`vdot_calculator.py:247-265`). After 100 iterations without converging within 0.01, `mid` is returned with no warning. Fix: log a warning on non-convergence.

- [x] **Naive/aware datetime mismatch risk** (`coaching_feedback_engine.py:228-230`). `run_log.date - plan.start_date` will raise `TypeError` if timezone awareness differs. `adaptive_plan_generator.py` strips timezone; `coaching_feedback_engine.py` does not.

- [x] **`week["total_km"]` accumulates drift after modifications** (`plan_service.py:712-720`). Incremental delta updates diverge from actual workout sum over time. Fix: recompute `sum(w["distance"] for w in workouts)` after any modification.

- [x] **`randomize_meals` builds template context manually, missing keys** (`routers/nutrition.py:72-92`). Omits `start_date`, `current_week_number`, `vdot`, `nutrition_phases`, `race_protocol`, etc. that `plan_view_context()` provides. Fix: use `plan_view_context`.

- [x] **`RunLogUpdate` has no upper bounds on `distance_km`/`duration_minutes`** (`schemas.py:383-401`). `distance_km=99999` is accepted, corrupting VDOT/analytics. Fix: `Field(None, gt=0, le=1000)`.

- [x] **`%-d` strftime format is Linux-only** (`routers/plans.py:383`, `plan_helpers.py:88,120`). Crashes on macOS dev environment. Fix: use `str(dt.day)` instead.

- [x] **98th-percentile HR index is wrong for small lists** (`performance_service.py:73`). For 5-6 values, always returns the absolute max, defeating outlier protection. Fix: use `statistics.quantiles` or require >= 10 runs.

- [x] **`race_predictor_service` `db=None` default masks required param** (`race_predictor_service.py:41,72`). Calling without `db` gives `AttributeError`. Fix: make `db: Session` required.

- [x] **`.timestamp()` on naive datetime uses local timezone** (`race_predictor_service.py:226`). Correct on UTC Fly.io container, wrong in non-UTC environments. Fix: use `(dt - datetime(1970,1,1)).total_seconds()`.

- [x] **Division-by-zero risk in `_calculate_quality_distances`** (`plan_generator.py:526-530`). Safe with current `PHASE_DISTRIBUTIONS` but no guard if `phase_dist['long']` ever reaches `1.0`. Fix: `safe_denom = max(0.01, 1 - long_pct)`.

---

## 5 -- UI / Frontend

### Critical
- [ ] **Duplicate `window.logout` definition** (`auth.js:207`, `api.js:328`). Last-loaded file wins. If loading order changes, logout silently breaks. Fix: remove `window.logout` from `api.js`.

- [ ] **`onclick` regex parsing in `plan.js` is fragile and broken** (`plan.js:816-820`). `dayName` is always `undefined` because `String.match()` without `g` flag returns only one match, so `[2]` is always `undefined`. Touch-path `openLogModal` never fires. Fix: use `data-*` attributes instead of regex on `onclick`.

### High
- [ ] **Chart.js loaded from CDN without integrity or version pin** (`plan.html:961`). `chart.js@4` auto-resolves to any 4.x release. Fix: pin version, add `integrity` + `crossorigin`, or self-host.

- [ ] **Tab panel keyboard navigation missing** (`plan.html:210-234`, `plan.js:720-731`). ARIA tab pattern requires arrow key navigation between tabs. Fix: add `keydown` handler for `ArrowLeft`, `ArrowRight`, `Home`, `End`.

- [ ] **`workout_card.html` component is unused and has conflicting styles** (`components/workout_card.html`). Never imported; its `<style>` block defines `.btn-primary` etc. with hardcoded colors that conflict with the design system. Fix: delete or rewrite.

- [ ] **`nav.html` contains 312 lines of inline `<script>`** (`nav.html:126-437`). Re-parsed on every page. Strava sync logic runs even for non-Strava users. Fix: extract to `nav.js` with `defer`.

- [ ] **`ModalManager` in `modal.js` never used for log-run modal** (`modal.js`, `plan.js`). `openLogModal`/`closeLogModal` use `style.display` directly, missing focus trapping and scroll-lock. Fix: use `ModalManager.openModal('logRunModal')`.

- [ ] **`run_walk` workout type missing from log-run modal select** (`plan.html:856-863`). Beginners get `run_walk` workouts but can't log them correctly. Fix: add `<option value="run_walk">Run/Walk</option>` and `recovery`.

- [ ] **Strava last-synced timestamp format mismatch** (`nav.html:46`). SQLAlchemy returns a `datetime` object; `parseInt()` produces `NaN`, showing "Never synced" even after sync. Fix: pass as Unix timestamp in template context.

### Medium
- [ ] **`scroll-to-top` button has no accessible label** (`plan.html:830`). A `<div>` with no `role`, `aria-label`, or `tabindex`. Fix: change to `<button aria-label="Scroll to top">`.

- [ ] **`toggleRecipe` relies on `nextElementSibling`** (`plan.js:733-745`). Fragile to any markup change. `mealName` parameter is unused. Fix: use `data-target` attribute pointing to recipe div ID.

- [ ] **`@keyframes fadeIn` injected at runtime** (`plan.js:768-776`). Collides with any CSS `fadeIn` and forces style recalculation. Fix: move to `plan.css`.

- [ ] **Dead `today_weekday` variable in plan template** (`plan.html:321-322`). Computed but never used. Fix: remove.

- [ ] **Multiple `console.log` debug statements in production** (`plan.js:9,793-794`, `auth.js:52,148,181,213`). Fix: remove or wrap behind DEBUG flag.

---

## 6 -- Modularity: Large Files to Split

- [x] **`plan.css` is 3,078 lines** -- split into:
  - `plan-core.css` -- header, summary, progress, week cards, workout grid (~600 lines)
  - `plan-nutrition.css` -- nutrition tab, meals, hydration (~400 lines)
  - `plan-raceday.css` -- race day tab, splits, timeline (~400 lines)
  - `plan-readiness.css` -- readiness dashboard, volume chart (~450 lines)
  - `plan-toasts.css` -- race prediction/comparison toasts (~200 lines)
  - `plan-modal.css` -- log-run modal overrides (~100 lines)
  Only `plan-core.css` loaded unconditionally; others conditional on tab data.

- [x] **`plan.html` is 967 lines** -- extract:
  - `components/nutrition_panel.html` -- nutrition tab content
  - `components/raceday_panel.html` -- race day tab content
  - `components/workout_item.html` -- workout rendering macro
  Keep `plan.html` as the orchestrating layout (~200 lines).

- [x] **`plan_generator.py` is 1,133 lines with 25+ methods** -- split into:
  - `phase_calculator.py` -- `_calculate_phases`, `_get_phase`, `_is_recovery_week`, `PHASE_DISTRIBUTIONS`
  - `mileage_progression.py` -- `_calculate_weekly_progression`, `_get_peak_mileage`, `_get_ideal_peak`
  - `workout_distribution.py` -- `_get_workout_distribution`, `_schedule_workout_types`
  - `workout_builders.py` -- `_generate_rest_day`, `_generate_easy_run`, `_generate_tempo_run`, `_generate_interval_run`, `_generate_hill_workout`, `_generate_long_run`, etc.
  - `long_run_calculator.py` -- `_calculate_long_run_distance`, `_calculate_long_run_ratio`
  `TrainingPlanGenerator` becomes a thin orchestrator.

- [ ] **`nav.html` is 438 lines (312 lines of script)** -- extract JS to `nav.js`.

- [ ] **`plan_service.py` private helpers could be extracted** -- `_adjust_intensity`, `_adjust_distance`, `_swap_workout`, `_apply_ai_suggestions` are self-contained and independently testable. Consider `plan_adjustments.py`.

---

## 7 -- Testing

- [ ] **Zero-mileage / beginner plan path has no test coverage** (`beginner_plan_generator.py`). Need tests for: `current_km=0, target=5K, weeks=8` succeeds; `current_km=0, target=42.2K` raises `ZeroMileageUnsupportedException`; `current_km=0, target=5K, weeks=6` raises `InsufficientTimeException`.

- [ ] **No tests for `/api/auth/google` (Google login flow)** (`routers/auth.py`, `auth_service.py`). Need: valid token creates user + JWT cookie; invalid token returns 401; anonymous-user merge on login.

- [ ] **No tests for `/api/strava/callback` (OAuth callback)** (`routers/strava.py:95-158`). Need: valid state + code stores tokens; invalid/expired state returns 400; Strava exchange failure returns 502.

- [ ] **`sport_type`-only Strava activity not tested** (`test_strava_service.py`). Known production bug (MEMORY.md). Need: `{"type": None, "sport_type": "Run"}` gets synced; `{"type": None, "sport_type": "Ride"}` skipped.

- [ ] **No router-level tests for runs, analytics, performance, adaptive, triathlon, recipes** -- at minimum one authenticated success + one 401 smoke test per router.

- [ ] **Test DB missing `PRAGMA foreign_keys=ON`** (`conftest.py:19-23`). Production enables it via `dependencies.py:36-44`. Tests can insert dangling FK rows without error. Fix: add `event.listens_for` on the test engine.

- [ ] **`dependency_overrides` leak in `test_strava_router.py`** (`test_strava_router.py:45-60`). `_make_client()` sets overrides but never clears them, causing test order-dependence. Fix: use a fixture with teardown.

- [ ] **`test_plan_generator.py` and `test_plan_generator_v2.py` overlap** -- duplicate tests and fixtures. Fix: consolidate into a single file using shared `conftest.py` fixture.

- [ ] **Not-found tests accept 500 as valid** (`test_api.py:141-155`). `assert response.status_code in [404, 500]` masks unhandled exceptions. Fix: assert 404 only.

---

## 8 -- Infrastructure

- [ ] **`httpx` missing from runtime `pyproject.toml` dependencies** (`pyproject.toml:20-25`). Listed only under `[test]` extras, but `strava_service.py` and `auth_service.py` import it at runtime. Fix: move to `[project.dependencies]`.

- [ ] **`requirements.txt` vs `pyproject.toml` version mismatch** (`requirements.txt`, `pyproject.toml`). `requirements.txt` pins exact versions; `pyproject.toml` uses `>=` lower bounds. `pytest-asyncio` is 0.21.1 in requirements but 1.3.0 locally (breaking changes). Fix: align or use a lock file.

- [ ] **`start.sh` does not verify seed file exists** (`start.sh:14`). If `runcoach.db.seed` is absent, `cp` fails and server never starts. Fix: add `[ -f "$SEED_PATH" ]` guard with fallback.

- [ ] **Fly.io health check `grace_period` too short for cold-start** (`fly.toml:23-24`). 10s grace period may not cover volume mount + migration + uvicorn startup. Fix: set `grace_period = '30s'`.

- [ ] **No database migration tool** *(out of scope)*. Inline `_run_migrations()` uses `try/except OperationalError: pass` for 17 `ALTER TABLE` statements. Genuine errors are silently swallowed. Fix: at minimum, log suppressed errors at DEBUG level.

- [ ] **PDF cache grows unboundedly** (`pdf_generator.py:25-27,119`). No eviction policy on `./pdf_cache`. On 1GB Fly.io volume, will eventually exhaust disk. Fix: use `BackgroundTask(os.unlink, pdf_path)` after response, or implement TTL eviction.

- [ ] **Superseded `migrate_add_start_date.py` checked into repo root**. Now handled by `_run_migrations()` in `main.py`. Fix: delete or move to `scripts/archived/`.

---

## 9 -- Low Priority / Code Quality

- [ ] **`target_distance` stored as `String` but used as `float` everywhere** (`training_plan.py:18`). Requires `parse_target_distance()` at every read site.

- [ ] **`PlanService` uses all static methods** (`plan_service.py`). Can't be subclassed or dependency-injected. Also instantiates `AdaptationService()` on every call (lines 515, 567).

- [ ] **Anonymous user cookie set twice on plan generation** (`main.py:90-116`, `routers/plans.py:174-183`). Middleware sets it, then route sets it again with potentially different user ID.

- [ ] **`performance_plan_generator.py` has dead wrapper `_format_pace`** (lines 191-208). One-line wrapper over `_shared_format_pace` adding no value. `_estimate_duration_min` is a pure utility living in a domain class.

- [ ] **`adaptive_plan_generator.py` silent fallback to 10 km/week** (lines 190-193). Users with no run data silently assigned 10 km/week as "current fitness". Should be `logger.warning`.

- [ ] **`quality_scorer.py` docstring lists "Unscored" label that is never returned** (lines 51, 84-95). Misleading documentation.

- [ ] **`recipe_data = Column(String)` in `FavoriteRecipe`** (`favorite_recipe.py:19`). `String` without length maps to `VARCHAR(255)` on PostgreSQL/MySQL, truncating large recipes. Fix: use `Column(Text)`.

- [ ] **`TriathlonPlan.user_id` is `nullable=True`** (`triathlon_plan.py:13`). Inconsistent with all other plan models which require a user.

- [ ] **No JSON schema version on `plan_data` Text columns** (`training_plan.py:23,24,47,50,53`). If the JSON schema changes, old rows are silently incompatible.
