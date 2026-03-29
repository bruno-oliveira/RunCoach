# RunCoach Code Review: Improvements Checklist

Reviewed: 2026-03-28. Focus: extensibility, correctness, readability, ease of understanding.
Methodology: 5 parallel review agents (core logic, API layer, models/services, frontend, tests/infra) + manual review.

---

## Critical -- Bugs & Security

- [x] **XSS in `auth.js:95`** -- error message injected directly into `innerHTML`. `showAuthError` does `errorDiv.innerHTML = '<strong>Error:</strong> ${message}'` where `message` comes from server responses or `err.message`. A crafted OAuth error can execute arbitrary HTML/JS. Fix: use `textContent` for the message portion.

- [x] **XSS in `plan.js:370,436-460`** -- API response fields (`pred.formatted`, `comp.predicted_formatted`, `verdictText`) injected raw into toast `innerHTML` in `showRacePredictionsToast` and `showRaceComparisonToast`. Fix: escape before interpolation or build elements with `textContent`.

- [x] **Google OAuth audience validation silently disabled** (`auth_service.py:71`). When `google_client_id` is empty (the default), `audience=settings.google_client_id or None` evaluates to `None`, and `python-jose` skips audience validation entirely. Any Google ID token from any OAuth client in the world is accepted. Fix: reject token verification when `google_client_id` is not configured.

- [x] **`NutritionEngine.__init__` mutates global `random` state** (`nutrition_engine.py:38`). `random.seed(random_seed)` affects every module using `random`, including `plan_generator.py`'s `random.uniform`/`random.choices`. Fix: use a private `self._rng = random.Random(random_seed)` instance.

- [x] **Carbohydrate calculation can go negative** (`nutrition_engine.py:60`). Formula `(calories - (protein * 4) - (fiber * 2)) / 4` double-counts fiber against the carb budget and uses a non-standard 2 kcal/g factor for fiber. For lighter athletes with low volume, carbs can be negative. Fix: compute carbs from what remains after protein and fat: `(calories - protein*4 - fat_kcal) / 4`.

- [x] **Missing key `total_runs_last_8_weeks` in early return** (`adaptive_plan_generator.py:50-56`). When a user has zero runs, the metrics dict omits this key, causing `KeyError` when `get_training_suggestions` accesses `metrics["total_runs_last_8_weeks"]` at line 409.

- [x] **`avg_weekly_km` inflated for sparse run data** (`adaptive_plan_generator.py:59-61`). When all runs fall on the same day, `weeks_span = max(1, 0) = 1`, attributing all distance to one week. A burst of 50km in a single day becomes `avg_weekly_km = 50.0`, driving the adaptive plan too aggressively. Fix: use `max(1, min(8, days/7))` or divide by 8 (the query window).

- [x] **`is_past` workout logic always evaluates to `workout.day <= 1`** (`plan.html:316`). The expression `today_iso | length and 1` in Jinja2 always returns `1` (since `today_iso` is always a non-empty string). This marks only the first workout of the current week as past, regardless of the actual day. Fix: use a proper day-of-week comparison.

- [x] **`delete_plan` orphans `RunFeedback.planned_workout_id` references** (`plan_service.py:307-339`). `DailyWorkout` rows are deleted but `RunFeedback` rows pointing to them via `planned_workout_id` are not NULLed out, leaving dangling FK references.

## Important -- Correctness

- [x] **`get_plan_or_404` returns 404 instead of 403 for another user's plan** (`plan_helpers.py:59-74`). When `require_user_match=True`, the query filters by both `plan_id` and `user_id`. If the plan exists but belongs to another user, the response is 404, creating an oracle for plan ID enumeration. Fix: fetch by ID first, then check ownership and return 403.

- [x] **`RunLogUpdate` has no `workout_type` validator** (`schemas.py:373-383`). `RunLogBase` validates workout types, but `RunLogUpdate` (a separate `BaseModel`) does not inherit the validator. Any string can be stored via `PUT /api/runs/{id}`.

- [x] **Float equality comparison for Trail distance is fragile** (`plan_generator.py:34`). `target_distance == 30.0` works only if the value arrives exactly as `30.0`. Any float arithmetic could yield `29.999...` and silently fall through to the Marathon category.

- [x] **Two conflicting `openModal`/`closeModal` implementations** (`modal.js` vs `modal.html`). `modal.js` uses class `is-open`; the `modal.html` macro uses class `active`. Whichever loads last wins, and the two implementations have incompatible class names.

- [x] **Improvement trend tip appended to every week** (`adaptive_plan_generator.py:268-272`). The "You're improving X%!" tip is inside the `for week in base_plan` loop, producing 12 identical tips in a 12-week plan. Fix: append only to week 1 or compute outside the loop.

- [x] **Duplicate `id="recipe-N"` across meal categories** (`plan.html:573`). `loop.index` resets for each meal category, generating duplicate HTML IDs for breakfast, lunch, etc.

- [x] **`workout_card.html` uses "miles" instead of "km"** (line 15). The entire application uses kilometres, but this macro hardcodes `miles`. Also references undefined functions `editWorkout`/`deleteWorkout` (line 51, 54).

- [x] **`get_or_create_anonymous_user` silently creates ghost users** (`plan_service.py:59-65`). When `anonymous_user_id` is provided but the user is not found (deleted, DB wiped), a new user is created without clearing the stale cookie, accumulating orphan rows.

- [x] **Strava callback initial sync blocks HTTP response** (`strava.py:118-153`). For `INITIAL_SYNC_DAYS=365`, the sync can take 10-30+ seconds, exceeding Fly.io's 30s proxy timeout. Fix: use `BackgroundTasks` for the initial sync.

- [x] **`user_id` missing `nullable=False`** (`training_plan.py:16`, `run_log.py:18`). The two most critical ownership columns default to `nullable=True`, while minor models like `RunFeedback` and `FavoriteRecipe` correctly use `nullable=False`.

- [x] **Analytics endpoint unbounded query** (`analytics.py:45-71`). `/api/analytics/runs` fetches all `RunLog` rows for a user with no pagination. On a 512MB Fly machine, a Strava-connected user with thousands of runs could cause OOM.

- [x] **Internal exception messages leaked to clients** (`plans.py:337,412`, `nutrition.py:140`). Catch-all `except Exception as e` blocks pass `str(e)` into `HTTPException.detail`, potentially exposing table names, column names, and query fragments.

- [x] **Population variance instead of sample variance** (`adaptation_service.py:204`). `sum((p - avg_pace)**2) / len(paces)` underestimates variance for small samples (3-10 runs), causing false "consistent pacing" assessments. Fix: divide by `len(paces) - 1`.

## Important -- Security

- [x] **Default `secret_key` in config** (`config.py:51`). `"your-secret-key-change-in-production"` is checked at startup in non-debug mode (good), but in debug mode any JWT signed with this key is valid. Fix: use a random default via `default_factory`.

- [x] **`APP_CTX` values not `|tojson`-escaped** (`plan.html:900-907`). Server values like `share_token`, `plan_id`, `user_id` are embedded in JS string literals without the `|tojson` filter. While currently safe (UUIDs), this is a structural XSS vector if any field ever contains quotes or special characters.

- [ ] **Strava tokens stored in plaintext** *(skipped — encryption at rest is a separate initiative)* (`user.py:22-23`). `strava_access_token` and `strava_refresh_token` are plain strings. Encryption at rest would be better practice.

## Readability & Code Quality

- [x] **`plan_generator.py.backup` exists in `/app/core/`**. Remove this leftover backup file.

- [ ] **`plan_generator.py` is 1134 lines with 25+ methods** *(out of scope — large refactor)*. Handles phases, distributions, distances, workout generation, strength, validation, and progression. Consider extracting into focused modules.

- [x] **`_get_phase_distribution` has 4 large dict literals** (`plan_generator.py:501-554`). Static data that would be clearer as module-level constants.

- [x] **Magic numbers in fitness scoring** (`adaptive_plan_generator.py:108-146`). Named constants would make the scoring logic self-documenting.

- [x] **Confusing variable naming: `easy_distance` for quality workouts** (`plan_generator.py:413-420`). The variable is reused for tempo/interval/hill distances.

- [x] **Dead code: `has_recovery = True`** (`plan_generator.py:211`). Assigned but never read.

- [x] **Duplicate comment** (`adaptive_plan_generator.py:252-253`). Copy-paste leftover.

- [x] **`_wrap_text` in PDF is unnecessary** (`pdf_generator.py:354, 954-977`). Manual word-wrap before `Paragraph()` which already handles wrapping. The manual `\n` chars are treated as whitespace by ReportLab, so the wrapping has no visible effect.

- [x] **No ORM cascade delete on any relationship** (`models/__init__.py:15-40`). All cascade logic is hand-rolled in `delete_plan`, making it easy to miss new child tables (already failing for `RunFeedback`, see above).

- [x] **`FavoriteRecipe` uses Integer auto-increment PK** (`favorite_recipe.py:13`) while all other models use UUID strings. Creates inconsistency in serialization, routing, and logging.

- [x] **Boolean imported but unused** (`training_plan.py:1`).

- [x] **Scoped `<style>` blocks in `macros.html` and `modal.html` duplicate and contradict `components.css`**. Hardcoded hex colours (`#667eea`) override CSS custom properties (`var(--color-primary)`), breaking dark mode and design consistency.

- [x] **`nav.html` embeds ~580 lines of CSS inline** (lines 125-710). Re-emitted on every page render; not cacheable by the browser. Should be in a stylesheet.

- [x] **`window.onerror` in `base.html` calls `alert()` on any `ReferenceError`** (lines 25-29). Too aggressive -- blocks the main thread during development and when third-party scripts fail.

- [x] **`plan.js:549-575` save button uses stale `localStorage` for auth state** instead of the server-rendered `{% if user %}` pattern used elsewhere.

## Extensibility

- [x] **Race distances hardcoded in 10+ places as float literals**. `5.0, 10.0, 21.1, 30.0, 42.2` scattered across schemas, generators, services, and templates. A single `SUPPORTED_DISTANCES` enum would make adding a new distance a one-line change.

- [ ] **`target_distance` stored as `String` in DB but used as `float` everywhere** *(out of scope — requires migration)* (`training_plan.py:18`). Requires `parse_target_distance()` at every read site.

- [x] **No abstraction for workout types**. String literals `"easy"`, `"tempo"`, etc. scattered across the codebase. Note: `"recovery"` is emitted by the generator (`plan_generator.py:276`) but is not in `self.workout_types` dict (lines 16-24).

- [ ] **`PlanService` uses all static methods** *(skipped — large cross-cutting refactor)*. Can't be subclassed or dependency-injected. Consider instance methods or plain module-level functions.

## Testing

- [ ] **No tests for most routers** *(out of scope — new test creation)* (auth, runs, strava, analytics, performance, adaptive, nutrition).

- [ ] **No tests for `AdaptationService`, `PDFGenerator`, or `AuthService`** *(out of scope — new test creation)*.

- [x] **Plan generator tests hit backward-compat shim, not production code** (`test_plan_generator.py:227-249`). Calling `_get_workout_distribution(10, 3)` with only positional args triggers `_get_workout_distribution_simple` instead of the real logic.

- [x] **Recovery week pattern test uses wrong taper window** (`test_plan_generator.py:295-317`). Assumes 3-week taper for half marathon, but `_calculate_phases` sets `taper=2` for `Half`.

- [x] **Nutrition info test is a near no-op** (`test_api.py:194-209`). `assert "nutrition" in html` matches any occurrence of the word in navigation or CSS classes, not actual nutrition data.

- [x] **Error path tests don't verify the error is shown** (`test_api.py:89-116`). Both assert `status_code == 200` but never check the error message is in the response body.

- [x] **`test_different_seeds_produce_different_results` doesn't test what it claims** (`test_nutrition_engine.py:103-119`). Only asserts both lists are non-empty; never asserts they differ.

## Infrastructure

- [ ] **No database migration tool** *(out of scope — Alembic setup is a separate initiative)*. Adding Alembic would make schema evolution safe.

- [ ] **PDF cache grows unboundedly** *(out of scope — cache eviction is a separate initiative)*. No eviction policy on `./pdf_cache`.

- [x] **`fly.toml:12` leading space in `[env]`**. Could cause `DATABASE_URL` to not be set depending on the TOML parser, silently falling back to the local SQLite path and losing production data on deploy.

- [x] **Dockerfile uses floating `python:3.11-slim` tag**. Pin to a specific patch version for reproducibility.

- [x] **`python-jose` and `cachetools` missing from `pyproject.toml`** but present in `requirements.txt`. Installing via `pip install .` will fail at runtime on auth endpoints.

- [x] **No graceful shutdown timeout in `start.sh`**. `exec uvicorn ... --host 0.0.0.0 --port 8000` has no `--timeout-graceful-shutdown`. With `auto_stop_machines = 'stop'`, in-flight requests are dropped when the machine stops. Fix: add `--timeout-graceful-shutdown 30`.

---

## Summary

The codebase is well-structured for a solo project: clear router/service/core separation, good Pydantic validation, sensible SQLAlchemy modeling, and a thoughtful training plan algorithm. The main areas to address:

1. **XSS vulnerabilities** in `auth.js` and `plan.js` innerHTML injection -- the highest-priority fixes.
2. **OAuth audience bypass** when `google_client_id` is unconfigured.
3. **Global random state mutation** -- genuine bug causing non-deterministic behavior.
4. **Negative carb calculation** and **missing dict key** -- runtime bugs in the nutrition/adaptive engines.
5. **Hardcoded distance literals** -- the biggest extensibility bottleneck.
6. **Test coverage gaps** -- most of the application surface area beyond plan generation is untested.
7. **Frontend logic bugs** -- `is_past` always wrong, conflicting modal implementations, duplicate IDs.
