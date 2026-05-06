# RunCoach - Codebase Improvements

> Comprehensive analysis covering maintainability, readability, extensibility, and security.

---

## 1. Maintainability

### Strengths

- **Modular architecture with clear separation of concerns**
  - `app/core/` contains pure business logic decoupled from the web layer
  - `app/services/` handles service-layer orchestration
  - `app/routers/` handles HTTP concerns only
  - Schemas split into domain-specific modules (`plan_schemas.py`, `auth_schemas.py`, `run_schemas.py`)
  - `app/routers/plans.py` acts as an aggregator for sub-routers

- **Facade pattern for AdaptationService**
  - `app/services/adaptation/__init__.py` delegates to 17 focused sub-modules
  - Makes adaptation logic highly testable and independently modifiable

- **TrainingPlanGenerator as thin orchestrator**
  - `app/core/generators/plan_generator.py` delegates to focused modules (phase_calculator, mileage_progression, workout_distribution, etc.)

- **Good test coverage for core logic**
  - `tests/test_core/test_plan_generator.py` (591 lines) thoroughly tests plan generation
  - `tests/test_security/test_p1_bugs.py` documents regression tests for critical bug fixes
  - Tests organized by domain: `test_core/`, `test_routers/`, `test_services/`, `test_security/`

- **Alembic migrations for schema evolution**
  - Proper migration framework with graceful error handling on startup

### Areas for Improvement

#### High Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| M1 | **Remove pass-through delegation methods** - `TrainingPlanGenerator` has ~30 one-line methods that just delegate to module functions. Remove them and let callers import modules directly. | `app/core/generators/plan_generator.py:58-240` | Reduces class size, eliminates indirection |
| M2 | **Fix test database isolation** - `test_db` session is shared across tests without rollback between test functions, risking test interdependence. | `tests/conftest.py:57-74` | Prevents flaky tests |
| M3 | **Replace bare `except Exception` with specific exceptions** - Multiple routers catch all exceptions generically, losing diagnostic information. | `app/routers/runs.py:100-110`, `app/routers/runs.py:162-167` | Better error diagnostics |
| M4 | **Deduplicate VDOT computation** - `PlanRequest.compute_vdot` and `FitnessPlanRequest.compute_vdot` duplicate the same VDOT parsing logic. Extract to shared utility. | `app/schemas/plan_schemas.py:247-288`, `app/schemas/plan_schemas.py:353-368` | DRY violation |

#### Medium Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| M5 | **Thin wrapper PlanService** - `PlanService` has 10 delegation methods to `PlanViewService` that add no value. Call directly or use composition cleanly. | `app/services/plans/plan_service.py:138-160` | Unnecessary indirection |
| M6 | **TrainingPlan model is a god object** - 24 columns including multiple JSON blobs (`plan_data`, `nutrition_plan_data`, `hr_zones_data`, `nutrition_phases_data`, `race_protocol_data`, `adaptation_alert`, `adaptation_history`, `pending_recommendation`). Consider normalizing into separate tables. | `app/models/training_plan.py:10-71` | Hard to query, migrate, evolve |
| M7 | **Startup migrations run on every boot** - Alembic migrations, VDOT backfill, effort-class backfill, and inactive account cleanup all run on every startup. Add latency and risk to every deployment. | `app/main.py:82-130` | Deployment risk, slow startup |
| M8 | **Fragile test mode detection** - Uses `"pytest" in __import__("sys").modules` to detect test mode. Use an environment variable or explicit flag instead. | `app/main.py:44` | Non-obvious, fragile |

#### Low Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| M9 | **No async database sessions** - App uses synchronous SQLAlchemy, blocking the FastAPI event loop. Consider async sessions for production concurrency. | `app/dependencies.py:52-62` | Performance bottleneck at scale |
| M10 | **Add integration tests for routers** - Test coverage is strong for core logic but routers and services have less coverage. | `tests/test_routers/`, `tests/test_services/` | Confidence in web layer |

---

## 2. Readability

### Strengths

- **Excellent docstrings in core modules** - `app/core/nutrition/nutrition_engine.py` documents rationale behind every nutrition formula constant with source references (ACSM guidelines)
- **Consistent naming conventions** - snake_case for functions/variables, PascalCase for classes throughout
- **Good use of type hints in schemas** - All Pydantic schemas have proper type annotations with `Field()` descriptions
- **Well-organized constants** - `app/constants.py` centralizes supported distances, distance names, and workout types
- **Clear exception hierarchy** - `app/exceptions.py` has clean hierarchy with `user_message` and `suggestion` attributes for UI display

### Areas for Improvement

#### High Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| R1 | **Standardize type hint syntax** - Mix of `Union[type, type]` / `Optional[type]` (old) and `type | type` (new) syntax across the codebase. Pick one style and apply consistently. | `app/schemas/race_prep_schemas.py:46-48` vs `app/schemas/run_schemas.py:4` | Consistency |
| R2 | **Move UI messages out of config** - `config.py` has 10 low/high mileage message strings embedded in the Settings class. Move to a separate constants or i18n module. | `app/config.py:86-125` | Config should be configuration, not content |
| R3 | **Explain magic numbers** - Several unexplained constants in generators (e.g., `0.20` ratio in performance plan generator). Add comments explaining the rationale. | `app/core/generators/performance_plan_generator.py:283`, `app/core/generators/beginner_plan_generator.py:150` | Understandability |

#### Medium Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| R4 | **Use structured logging** - Multiple routers use f-strings in `logger.warning/error/info` calls instead of `%s` or `{}` style structured logging. | `app/routers/runs.py:101,110,112,122,163,322,349` | Better log aggregation |
| R5 | **Duplicate import** - `favorite_recipe.py` imports `uuid` twice. | `app/models/favorite_recipe.py:4,8` | Cleanliness |
| R6 | **Simplify PlanRequest validators** - `model_validator` does weeks validation, mileage validation, AND VDOT computation. VDOT computation involves importing `VDOTCalculator` and doing time parsing, which is unexpected in a schema validator. | `app/schemas/plan_schemas.py:118-288` | Unexpected side effects in validators |

---

## 3. Extensibility

### Strengths

- **Strategy pattern via delegated modules** - Training calculations split into independent modules (`phase_calculator.py`, `mileage_progression.py`, `workout_builders.py`, etc.) making it easy to swap algorithms
- **KeyWorkoutLibrary** - `app/core/training/key_workout_library.py` provides a pluggable workout catalog
- **Configuration-driven constraints** - All training constraints configurable via environment variables; clear extension path for new race distances
- **Mixin-based PDF generation** - `PDFGenerator` uses multiple inheritance with `PDFBase`, `PlanPagesMixin`, `NutritionPagesMixin`, `SupplementaryPagesMixin` for clean separation
- **Encrypted type for sensitive data** - `app/models/encrypted_type.py` provides reusable `EncryptedString` SQLAlchemy type

### Areas for Improvement

#### High Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| E1 | **No plugin architecture for workout types** - Adding a new workout type requires changes in multiple places: `constants.py`, `workout_builders.py`, `workout_distribution.py`, schema validators, and templates. Create a registry or plugin system. | Multiple files | High change cost for new workout types |
| E2 | **No interface/protocol definitions** - No `Protocol` classes or abstract base classes defining contracts between modules. Add formal interfaces for generators, services, and builders. | Throughout | Harder to swap implementations |
| E3 | **Plan data stored as JSON blobs** - `TrainingPlan` stores `plan_data` and `nutrition_plan_data` as JSON columns. Makes it hard to query, migrate, or evolve the plan schema. Consider normalized tables or at least a JSON schema validation layer. | `app/models/training_plan.py:24-25` | Schema evolution difficulty |

#### Medium Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| E4 | **Nutrition engine hardcoded to one meal database** - `MealSelector` reads from a fixed `meals.json`. Add abstraction for alternative meal sources or dietary preference engines. | `app/core/nutrition/nutrition_engine.py:76` | Limited dietary customization |
| E5 | **Rate limiter is in-memory only** - Uses a `defaultdict` with no persistence. On multi-instance deployments (e.g., Fly.io), rate limits are per-instance, not global. Use Redis or similar for distributed rate limiting. | `app/rate_limit.py:10-37` | Ineffective rate limiting at scale |
| E6 | **No API versioning** - All routes are at base paths (`/api/runs`, `/api/auth/google`). Add `/api/v1/` prefixing for future backward-compatible evolution. | All routers | Breaking changes harder to manage |
| E7 | **Tight coupling between generators and builders** - `PerformancePlanGenerator` imports directly from `performance_workout_builders`. A new generator type would need its own builder module with no shared interface. Define a common builder protocol. | `app/core/generators/performance_plan_generator.py:27-35` | Hard to add new generator types |

---

## 4. Security

### Strengths

- **JWT tokens in HTTP-only cookies** - `httponly=True`, `samesite="lax"`, conditionally `secure=True`. Token NOT returned in response body. (`app/routers/auth.py:64-71`)
- **Google OAuth verified with public keys** - Proper audience/issuer validation with certificate caching (1-hour TTL). (`app/services/auth/auth_service.py:65-99`)
- **CSRF protection via Content-Type requirement** - Requires `application/json` or `multipart/form-data` on state-changing API requests. (`app/middleware.py:87-108`)
- **Security headers on all responses** - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`. (`app/middleware.py:14-23`)
- **Strava tokens encrypted at rest** - Uses `EncryptedString` (Fernet encryption) for Strava tokens. (`app/models/user.py:23-24`)
- **Production secret validation** - Validates `SECRET_KEY` is at least 32 characters and doesn't contain weak patterns. (`app/main.py:59-79`)
- **Rate limiting on auth endpoints** - 10 req/min on Google auth, 5 req/min on Strava callback. (`app/routers/auth.py:40`)
- **Request size limiting** - Rejects requests exceeding 1 MB default. (`app/middleware.py:38-46`)
- **Plan ownership validation** - Checks user/anonymous ID before allowing plan access. (`app/dependencies.py:192-218`)
- **Run logs scoped to user** - All run queries filter by `RunLog.user_id == current_user.id`, preventing IDOR. (`app/routers/runs.py:142`)
- **Account deletion cleans up Strava tokens** - Revokes Strava tokens before deleting user account. (`app/routers/auth.py:128-133`)

### Areas for Improvement

#### Critical

| # | Issue | Location | Risk |
|---|-------|----------|------|
| S1 | **Add Content-Security-Policy header** - Missing CSP header leaves the app vulnerable to XSS if any user-generated content is rendered (e.g., run notes). | `app/middleware.py:14-19` | XSS vulnerability |
| S2 | **Sanitize run notes input** - `notes` field (max 1000 chars) has no character-level sanitization. Users could store HTML/JS. Verify Jinja2 autoescaping is enabled and add input sanitization. | `app/schemas/run_schemas.py:18`, `app/models/run_log.py:30` | Stored XSS |
| S3 | **Separate encryption key from JWT secret** - `ENCRYPTION_KEY` falls back to `SECRET_KEY`. Anyone with the JWT signing key can also decrypt stored tokens. Require separate keys. | `app/models/encrypted_type.py:24` | Defense-in-depth violation |

#### High Priority

| # | Issue | Location | Risk |
|---|-------|----------|------|
| S4 | **Add proper CSRF tokens** - Content-Type check is effective against simple form submissions but not against sophisticated attacks. Add CSRF token for state-changing operations. | `app/middleware.py:87-108` | CSRF vulnerability |
| S5 | **Distributed rate limiting** - In-memory rate limiting means each server instance has its own counter. Attackers could distribute requests across instances to bypass limits. | `app/rate_limit.py:14` | Rate limit bypass |
| S6 | **Rate limit account deletion** - Account deletion endpoint has no rate limiting. An attacker with a stolen cookie could delete an account. | `app/routers/auth.py:119-138` | Account destruction |
| S7 | **Stricter SameSite for API endpoints** - `samesite="lax"` allows cookies on top-level navigations. For API-only endpoints, `samesite="strict"` would be more appropriate. | `app/routers/auth.py:69` | Cookie leakage |

#### Medium Priority

| # | Issue | Location | Risk |
|---|-------|----------|------|
| S8 | **Add audit logging for sensitive operations** - Account deletion, Strava disconnect, and plan deletion lack structured audit logs with IP addresses, user agents, and timestamps. | `app/routers/auth.py:127`, `app/routers/strava.py:185` | No forensic trail |
| S9 | **Debug endpoint information disclosure** - `/debug/config` exposes whether Google Client ID is configured and debug mode status. Provides reconnaissance data. | `app/main.py:211-218` | Information disclosure |
| S10 | **Strava OAuth state token contains user ID** - If intercepted, an attacker could link the state token to a specific user. Consider using an opaque random string mapped server-side. | `app/routers/strava.py:35-38` | User identification |

---

## Priority Summary

### Immediate Action (Critical)
- [S1] Add Content-Security-Policy header
- [S2] Sanitize run notes input / verify Jinja2 autoescaping
- [S3] Separate encryption key from JWT secret

### Short Term (High Priority)
- [M1] Remove pass-through delegation methods
- [M2] Fix test database isolation
- [M3] Replace bare `except Exception` with specific exceptions
- [M4] Deduplicate VDOT computation
- [S4] Add proper CSRF tokens
- [S5] Implement distributed rate limiting
- [S6] Rate limit account deletion
- [E1] Create workout type registry
- [E2] Define Protocol/interface contracts

### Medium Term
- [M5] Simplify PlanService composition
- [M6] Normalize TrainingPlan model
- [M7] Move startup migrations to explicit command
- [R1] Standardize type hint syntax
- [R2] Move UI messages out of config
- [S7] Stricter SameSite for API endpoints
- [E3] Add JSON schema validation for plan data
- [E6] Add API versioning

### Low Priority / Nice to Have
- [M9] Consider async database sessions
- [M10] Add integration tests for routers
- [R4] Use structured logging consistently
- [E4] Abstract nutrition meal sources
- [E5] Distributed rate limiting (if not addressed above)
- [E7] Common builder protocol for generators
- [S8] Audit logging
- [S9] Lock down debug endpoints
- [S10] Opaque Strava state tokens
