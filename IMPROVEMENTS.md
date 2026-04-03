# RunCoach — Improvement Checklist

Full quality review covering backend correctness, frontend UI/UX, architecture, maintainability, and extensibility.

---

## Dead Code — To Be Removed

### Critical Priority

- [ ] **Remove entire `adaptive.py` router** — All 4 endpoints are dead: `/api/adaptive/metrics`, `/api/adaptive/suggestions`, `/api/adaptive/performance-gaps`, `/api/adaptive/generate-plan`. Router registered in `main.py:238` but no frontend code calls any endpoint. The "Adjust" button in plan view uses `AdaptationService` instead. (`routers/adaptive.py:20-136`)
- [ ] **Remove `AdaptivePlanGenerator` class** — Entire class superseded by `AdaptationService`. Only used by the dead adaptive router. (`core/adaptive_plan_generator.py:17-448`)
- [ ] **Delete `templates/plan.html.backup`** — 2000+ line backup file with stale code and leaked implementation details. (`templates/plan.html.backup`)

### High Priority

- [ ] **Remove 5 unused endpoints in `runs.py`** — None are called from frontend:
  - `GET /api/runs` (list runs) — analytics uses `/api/analytics/runs` instead (`runs.py:172-218`)
  - `GET /api/runs/feedback/plan/{plan_id}` — no coaching feedback UI (`runs.py:300-325`)
  - `GET /api/runs/{run_id}` (get single run) — not exposed in UI (`runs.py:328-347`)
  - `PUT /api/runs/{run_id}` (update run) — no edit run UI (`runs.py:350-384`)
  - `GET /api/runs/{run_id}/feedback` — no run feedback UI (`runs.py:412-447`)
- [ ] **Remove unused nutrition endpoint** — `GET /nutrition-plan/{plan_id}` not called from JS; nutrition displayed inline in plan view. (`routers/nutrition.py:84-123`)
- [ ] **Remove unused ApiClient methods** — `put()`, `patch()`, `del()`, `showWarning()`, `showInfo()` defined but never called. (`static/js/api.js:232-318`)
- [ ] **Remove dead `randomizeMeals()` function** — Creates form for `/randomize-meals` but no UI button calls it. Feature appears abandoned. (`static/js/plan.js:110-170`)
- [ ] **Remove unused template macros** — `form_textarea`, `card`, `loading_spinner` defined in `macros.html` but never imported/used. (`templates/components/macros.html`)
- [ ] **Remove unused import in `runs.py`** — `calculate_quality_score` imported but never used. (`routers/runs.py:11`)
- [ ] **Remove `__all__` exports from `core/__init__.py`** — No code imports from `app.core` directly; all use specific submodule paths. (`core/__init__.py:3-15`)

### Medium Priority

- [ ] **Remove or implement Strava disconnect** — `POST /api/strava/disconnect` endpoint exists but no disconnect button in UI. Either add disconnect button or remove endpoint. (`routers/strava.py:267-275`)
- [ ] **Remove unused plan performance endpoint** — `GET /api/plan/{plan_id}/performance` not called from frontend; `AdaptationService.analyze_performance()` used internally only. (`routers/plans.py:419-433`)
- [ ] **Remove unused modal data attributes** — `[data-modal-open]` and `[data-modal-toggle]` listeners defined but no templates use these attributes. (`static/js/modal.js`)
- [ ] **Remove CommonJS export blocks** — `module.exports` checks for Node.js in browser-loaded files. (`static/js/api.js:325-327`, `static/js/modal.js:217-219`)
- [ ] **Remove `components/modal.html`** — Modals now implemented inline in `plan.html` and `performance_plan.html`; this component appears unused. (`templates/components/modal.html`)

---

## Critical — Bugs & Crashes

- [ ] **Guard against `IndexError` when `easy_runs == 0`** — `easy_distances` list is empty when no easy runs are scheduled, but the fallback `easy_distances[0]` at line 212 will raise `IndexError` if an easy workout slot is somehow assigned. (`core/plan_generator.py:209-212`)
- [ ] **Fix focus-trap listener leak in `ModalManager`** — every `openModal()` call adds a new `keydown` listener via `_trapFocus()`, but `closeModal()` never removes it. Listeners accumulate on repeated open/close cycles. (`static/js/modal.js:120-141`)
- [ ] **Resolve duplicate `@keyframes` with conflicting definitions** — `@keyframes spin` defined in 5 CSS files; `@keyframes toastSlideIn` in 3 files with different animations (`translateY` vs `translateX`). Last-loaded definition silently wins. Consolidate into `base.css`/`components.css`. (`base.css`, `nav.css`, `analytics.css`, `plan.css`, `plan-readiness.css`, `components.css`, `plan-toasts.css`)

## High — Correctness & Security

- [ ] **`plans_generated` counter is never incremented** — field is always 0 for all users. Plan limit enforcement uses a direct query so limits still work, but the counter displayed to users is wrong. (`models/user.py:19`)
- [ ] **Temp directory leaked on PDF generation exception** — `tempfile.mkdtemp()` is never cleaned up if `doc.build(story)` raises. Wrap in `try/finally`. (`core/pdf_generator.py:142-215`)
- [ ] **`avg_weekly_km` over-estimated for burst runners** — a user who ran 100km in 3 days gets `weeks_span` clamped to 1, producing a wildly inflated weekly volume that drives the adaptive plan to assign injury-risk mileage. (`core/adaptive_plan_generator.py:61-66`)
- [ ] **JWT expiry uses naive datetime** — `datetime.now(timezone.utc).replace(tzinfo=None)` strips timezone info before encoding as `exp` claim. Use Unix epoch integer instead for safety. (`auth_service.py:30-34`)
- [ ] **PDF cache written to ephemeral filesystem** — `./pdf_cache` resolves to `/app/pdf_cache` in the container, which is lost on every Fly.io cold start. Move to the persistent volume or remove the caching layer. (`core/pdf_generator.py:28`)
- [ ] **IDOR: any authenticated user can claim orphaned anonymous plans** — if the plan owner was deleted (NULL FK), the ownership check in `save_plan_to_account` is bypassed. (`routers/plans.py:586-609`)
- [ ] **`strength` workout type registered but not handled in dispatch** — listed in `TrainingPlanGenerator.workout_types` but the dispatch chain falls through to `raise ValueError`. (`core/plan_generator.py:224-242`)
- [ ] **Anonymous cookie deletion may fail in Safari** — `delete_cookie` missing `httponly=True` and `secure=not settings.debug` to match the attributes set during creation. (`routers/auth.py:71`)
- [ ] **`vdot` and `effort_quality_score` not recalculated on run update** — `PUT /api/runs/{run_id}` recalculates pace but leaves VDOT stale, affecting race predictions. (`routers/runs.py:370-383`)
- [ ] **`cryptography` used directly but not listed in `requirements.txt`** — `EncryptedString` imports Fernet; it arrives only transitively via `python-jose[cryptography]`. Must be a direct dependency. (`models/encrypted_type.py:8`)

## High — Architecture & Maintainability

- [ ] **Move startup side-effects into `lifespan`** — `create_all`, `_run_migrations`, and `_backfill_vdot` run at module-import time, contaminating tests and creating startup ordering dependencies. (`main.py:126-219`)
- [ ] **Module-level singleton bypasses DI** — `AdaptivePlanGenerator()` at module scope in `routers/adaptive.py:17`. All other generators use `dependencies.py`. Make it injectable.
- [ ] **`AdaptationService` instantiated ad-hoc in 5 places** — constructed inline in `plans.py`, `strava.py`, and `PlanService.__init__`. Add `get_adaptation_service()` to `dependencies.py`. (`routers/plans.py:284,430,466,479`, `routers/strava.py:36`)
- [ ] **Schema migrations are raw SQL in a silent try/except loop** — 19 `ALTER TABLE` statements with all `OperationalError` swallowed (including serious ones like disk full). No record of applied migrations. Consider adopting Alembic. (`main.py:134-178`)
- [ ] **Cookie/JWT lifetime hardcoded, ignoring `config.session_timeout_minutes`** — cookie `max_age` in `auth.py:21`, JWT `exp` in `auth_service.py:32`, and anonymous cookie in `main.py:117` are all independent of the config value. (`config.py:59`)
- [ ] **Adding a new race distance requires changes in 8+ files** — business rules (min weeks, mileage floors, phase ratios) scattered across `config.py`, `schemas.py`, `mileage_progression.py`, `phase_calculator.py`, `pdf_generator.py`. Consolidate into a `DistanceConfig` dataclass.

## High — Testing Gaps

- [ ] **No tests for any authenticated endpoint** — the test `client` fixture never sets up auth. Run logging, plan adjustment, Strava sync, analytics all have zero coverage. (`tests/test_api.py`)
- [ ] **No tests for 5 major services** — `AdaptationService`, `StravaService`, `FeedbackService`, `RacePredictorService`, `ReadinessService` are entirely untested.
- [ ] **`test_create_and_view_plan` asserts 200 but never verifies plan content** — comment says "in real tests we'd parse the HTML". (`tests/test_api.py:179-195`)
- [ ] **`conftest.py` `test_db` session shared across requests** — state accumulates and rollbacks inside route handlers affect subsequent calls. (`tests/conftest.py:46-58`)

## Medium — Frontend / UI/UX

- [ ] **Modals missing `role="dialog"` and `aria-modal="true"`** — screen readers don't announce dialog context. Also missing `aria-labelledby`. (`templates/plan.html:445-517`, `templates/components/modal.html`)
- [ ] **Close button on adaptation banner has no accessible label** — `×` character announced as "times" by screen readers. Add `aria-label="Dismiss"`. (`templates/plan.html:50`)
- [ ] **No `prefers-reduced-motion` support anywhere** — continuous animations (20s orb floats, pulses, transitions) affect users with vestibular disorders. Add global reduced-motion media query to `base.css`.
- [ ] **Tab panel keyboard navigation incorrect** — inactive tabs missing `tabindex="-1"` at render time; keyboard users visit all tabs before reaching panel content. (`templates/plan.html:223-247`, `static/js/plan.js:696-722`)
- [ ] **Native `confirm()`/`alert()` used for 6+ destructive actions** — thread-blocking, unstyled, poor mobile UX. Replace with existing `ModalManager` and toast system. (`static/js/plan.js:50,454,570,613`, `static/js/nav.js:127`, `templates/index.html:275,282`)
- [ ] **Warning color `#D97706` fails WCAG AA contrast** — 3.1:1 ratio on `#FFFBEB` background (requires 4.5:1). Affects warning alerts, tempo badges, toast text. Darkens needed. (`static/css/base.css:47`)
- [ ] **No `<meta name="description">` or Open Graph tags** — no search snippets, no social sharing previews. (`templates/base.html:1-47`)
- [ ] **PDF template has no styles and uses unsupported emoji** — all class-based layout renders unstyled; ReportLab can't render color emoji. (`templates/pdf_template.html`)
- [ ] **Analytics dashboard hardcodes light-mode colors for charts** — `COLORS` object uses hex values that don't follow CSS variables; charts render wrong colors in dark mode. (`static/js/analytics_dashboard.js:13-24`)
- [ ] **Duplicate CSS in Jinja2 macro `<style>` blocks** — `macros.html` and `modal.html` re-define `.btn`, `.modal`, `.alert-*`, `.badge-*` etc. already in `components.css`. Can be emitted multiple times per page. (`templates/components/macros.html:122-361`, `templates/components/modal.html:21-153`)
- [ ] **`z-index: 9999` in `plan-toasts.css` overrides entire stacking system** — design system defines `--z-toast: 800`. Prediction toast renders above modals. (`static/css/plan-toasts.css:9`)
- [ ] **Click-outside-to-close broken for Log Run modal** — `ModalManager` handler checks for `.modal-backdrop` class which `plan.html`'s modal doesn't have. (`static/js/modal.js:156-165`)
- [ ] **No loading/retry state on Race Readiness tab** — if API fails, only a plain `<p>` with no retry affordance. (`static/js/readiness.js:13-47`)
- [ ] **`triggerGoogleSignIn` silently fails if GSI not loaded** — one retry after 500ms with no user feedback on slow networks. (`static/js/nav.js:26-37`)

## Medium — Code Quality & Patterns

- [ ] **Nutrition data transformation duplicated** — `plan_service.nutrition_for_template` and `performance.py:349-369` implement the same JSON-to-template conversion with different field names (`protein_grams` vs `protein_g`).
- [ ] **Plan-limit magic number `3` duplicated** — hardcoded in template context, error strings, and HTML. Should use `PlanService.MAX_PLANS_PER_USER` everywhere. (`routers/plans.py:136-145`, `routers/performance.py:188-203`)
- [ ] **Dual time-parsing utilities** — `utils.py:parse_race_time_to_seconds`, `performance.py:_parse_time_to_pace`, and `vdot_calculator.py:parse_time_to_seconds` all parse `MM:SS`/`HH:MM:SS` with different error handling. Consolidate.
- [ ] **`Jinja2Templates` instantiated 8 times at module load** — each router creates its own instance via `create_templates()`. Use a single app-level instance. (`plans.py`, `performance.py`, `analytics.py`, `nutrition.py`, `recipes.py`, `plan_helpers.py`, `triathlon.py`, `main.py`)
- [ ] **Carbs macro calculation re-derives fat inline** — two `round()` calls can diverge, causing macros not to sum to total calories. Use the already-computed `fat` variable. (`core/nutrition_engine.py:62`)
- [ ] **No input validation on `adjustment_type` or `adjustment_value`** — unknown types silently produce no change but still persist a `PlanCustomization` record. (`services/plan_service.py:286-308`)
- [ ] **Nutrition endpoint bypasses DI** — constructs `NutritionEngine` inline instead of using `get_nutrition_engine()`. (`routers/nutrition.py:47-48`)
- [ ] **`get_plan_or_404` has inconsistent parameter handling** — `anonymous_user_id` is positional when it should be keyword-only. Callers pass it differently. (`routers/plans.py`)
- [ ] **`DISTANCE_NAMES` imported from `schemas.py` instead of `constants.py`** — creates indirect dependency through the wrong module. (`routers/plans.py:40`, `routers/performance.py:20`)
- [ ] **`workout_types` dict in `TrainingPlanGenerator.__init__` is dead code** — never read by the class; real definitions live in `constants.py` and `workout_builders.py`. (`core/plan_generator.py:31-39`)
- [ ] **`requests` library appears unused** — only `httpx` is imported in application code. Remove to reduce dependency surface. (`requirements.txt`)
- [ ] **`requirements.txt` versions are 18+ months old** — `python-jose==3.3.0` (2021) has known CVEs. Update pinned versions. (`requirements.txt`)
- [ ] **f-string interpolation in `logger.info`/`logger.error`** — 24+ occurrences bypass lazy formatting. Use `%s` style. (`routers/auth.py:36,41,48,55` and 12 other files)
- [ ] **Cached cert log at INFO level creates noise** — `"Using cached Google OAuth certificates"` fires on every authenticated request. Should be `DEBUG`. (`auth_service.py:52`)
- [ ] **Plan generator tests access private `_` methods directly** — will break if internal refactoring continues. Test public `generate_plan` output instead. (`tests/test_plan_generator.py:219-453`)

## Low — Polish

- [ ] **`!important` overuse in `mobile.css`, `nav.css`, `index.css`** — 12 declarations fighting specificity instead of using structured selectors. (`mobile.css:38-39,44-45,172-174,184`, `nav.css:186-188,320,324`, `index.css:257`)
- [ ] **Inline `style=""` for show/hide prevents CSS transitions** — use `.is-visible`/`.is-hidden` class toggles instead. (`plan.html:40,259,409,410,430,433`, `analytics.html:36,41,55,62`)
- [ ] **`.btn-small` has no `min-height`** — computed height ~25px, below 44px touch target. (`plan-core.css:1144-1147`)
- [ ] **Strava sync fires automatically on analytics page load** — adds latency and may hit rate limits. Should be user-initiated only. (`static/js/analytics_dashboard.js:36-39`)
- [ ] **`TrainingPlan.target_distance` stored as `String`** — requires string comparison and a `target_distance_km` property to parse back to float. Should be `Float`. (`models/training_plan.py:18`)
- [ ] **No composite index on `daily_workouts(weekly_plan_id, day_of_week)`** — plan view queries scan all workouts to find each specific day. (`models/daily_workout.py`)
- [ ] **No API versioning** — all endpoints at `/api/*` with no version prefix. Breaking changes have no migration path for future clients.
- [ ] **`pytest-asyncio` listed as test dependency but no async tests exist** — unused. (`pyproject.toml:23`)
- [ ] **Naive datetime pattern used throughout (16+ occurrences)** — `datetime.now(UTC).replace(tzinfo=None)`. Will silently break if database migrates to PostgreSQL.
- [ ] **`"strength"` in test `valid_types` but absent from `constants.WORKOUT_TYPES`** — users can't log strength workouts even though plans mention them. (`tests/test_plan_generator.py:116`, `constants.py`)
