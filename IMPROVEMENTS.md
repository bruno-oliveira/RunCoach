# RunCoach — Improvement Opportunities

> Last reviewed: May 2026

This document catalogs improvement opportunities organized by priority and quality dimension. Each item includes a rationale, affected files, and suggested approach.

---

## Priority Matrix

| Priority | Impact | Effort | Area |
|----------|--------|--------|------|
| P0 | High | Low | Security |
| P1 | High | Medium | Maintainability |
| P2 | Medium | Medium | Extensibility |
| P3 | Low-Medium | Low | Modularity / Hygiene |

---

## P0 — Security

### 1. Add explicit CORS middleware

**Problem:** No `CORSMiddleware` is configured. The app relies on browser same-origin policy by default. While acceptable for a server-rendered app with cookie auth, this should be explicit and documented.

**Files:** `app/main.py:159-162`

**Suggested fix:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],  # from config
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 2. Add rate limiting to plan generation

**Problem:** `app/rate_limit.py` limits auth (10/min), Strava callback (5/min), and account deletion (3/hour), but plan generation has no rate limit. PDF generation is CPU-intensive and could be abused for resource exhaustion.

**Files:** `app/rate_limit.py`, `app/web/routers/plan_generation.py`

**Suggested fix:** Add a `plan_generation_limiter` with a cap like 5 requests per minute per IP. Apply it to the `/generate-plan` and `/download-pdf/*` endpoints.

### 3. Remove or harden debug endpoint

**Problem:** `/debug/config` (`app/main.py:226-233`) exposes whether Google Client ID is configured and debug mode status. While gated by `settings.enable_debug_endpoints`, this endpoint should never be reachable in production.

**Files:** `app/main.py:226-233`

**Suggested fix:** Either remove the endpoint entirely, or add an additional admin-authentication check beyond the settings flag. Consider removing it and using health check metrics instead.

### 4. Implement JWT refresh token mechanism

**Problem:** JWT tokens expire after 24 hours with no refresh path. Users must re-authenticate via Google OAuth.

**Files:** `app/contexts/auth/auth_service.py:27`, `app/dependencies.py:136-142`

**Suggested fix:** Add a refresh token endpoint that issues a new access token when the user presents a valid (non-expired) refresh token. Store refresh tokens server-side with revocation support.

### 5. Clean up anonymous user records

**Problem:** `app/web/middleware.py:71-103` creates UUID-based anonymous users stored in the `users` table. These accumulate without cleanup.

**Files:** `app/web/middleware.py:71-103`, `app/models/user.py`

**Suggested fix:** Add a periodic cleanup task (similar to `app/application/cleanup_service.py`) that removes anonymous users older than N days who have no associated plans or runs.

---

## P1 — Maintainability

### 6. Decompose `app/main.py` (God file)

**Problem:** 243 lines handling lifespan, secrets validation, startup migrations, static files, 11 router includes, template setup, and 3 page endpoints. The home endpoint (`app/main.py:189-213`) directly queries the database and imports `RunLog` — logic that belongs in a service.

**Files:** `app/main.py`

**Suggested fix:**
- Extract router registration into `app/web/routers/__init__.py`
- Extract the home endpoint into a dedicated router or service
- Extract startup/migration logic into `app/infrastructure/database/migrations.py`
- Target: `main.py` under 80 lines, acting purely as composition root

### 7. Split `app/dependencies.py`

**Problem:** 224 lines mixing service factories, auth resolution, ownership helpers, and re-exports of `engine`/`SessionLocal`. The `validate_plan_ownership` function (`app/dependencies.py:187-199`) directly instantiates `SQLAlchemyPlanRepository` instead of using DI.

**Files:** `app/dependencies.py`

**Suggested fix:** Split into focused modules:
- `app/dependencies/database.py` — engine, session, repo factories
- `app/dependencies/services.py` — service factories (PlanService, NutritionEngine, etc.)
- `app/dependencies/auth.py` — user resolution, ownership validation
- `app/dependencies/__init__.py` — re-exports for backward compatibility

### 8. Reduce `create_run_log` endpoint complexity

**Problem:** `app/web/routers/runs.py:36-146` (110 lines) does ownership validation, workout validation, run creation, quality scoring, VDOT enrichment, feedback generation, adaptation evaluation, and response building — violating single responsibility.

**Files:** `app/web/routers/runs.py:36-146`

**Suggested fix:** Extract into a `RunCreationService` in `app/contexts/runner/enrichment/` that orchestrates:
1. Create run record
2. Score quality
3. Enrich with VDOT
4. Generate feedback
5. Evaluate adaptation
The endpoint then becomes a thin HTTP adapter calling the service.

### 9. Split `app/schemas/plan_schemas.py`

**Problem:** 585 lines containing 4 schema classes, 2 helper functions, and a mileage config dict. `PlanRequest` alone has 7 `@model_validator` methods.

**Files:** `app/schemas/plan_schemas.py`

**Suggested fix:** Split into:
- `app/schemas/plan_request.py` — `PlanRequest` and its validators
- `app/schemas/fitness_request.py` — `FitnessPlanRequest`
- `app/schemas/performance_request.py` — `PerformancePlanRequest`
- `app/schemas/plan_config.py` — `_MILEAGE_CONFIG` helper and constants
- `app/schemas/__init__.py` — re-exports

### 10. Add test coverage reporting

**Problem:** `pyproject.toml` has pytest configuration but no `pytest-cov` or coverage thresholds. Cannot measure coverage gaps.

**Files:** `pyproject.toml`, `requirements.txt`

**Suggested fix:**
```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=80"
```
Add `pytest-cov` to `requirements.txt` and the `[test]` extra in `pyproject.toml`.

### 11. Add type hints to `PlanService` methods

**Problem:** `app/contexts/plan/plan_service.py:118-124` (`customize_plan`, `delete_plan`) have no type hints on parameters. Inconsistent with the rest of the codebase.

**Files:** `app/contexts/plan/plan_service.py`

**Suggested fix:** Add type annotations to all public method signatures. Consider enabling `mypy` or `pyright` in CI.

---

## P2 — Extensibility

### 12. Inject repository interfaces into services

**Problem:** `PlanService` (`app/contexts/plan/plan_service.py:65-66`) and `AuthService` (`app/contexts/auth/auth_service.py:115`) directly instantiate concrete repositories (`SQLAlchemyPlanRepository(db)`, `SQLAlchemyUserRepository(db)`) instead of accepting `IPlanRepository` / `IUserRepository` interfaces. This makes testing harder and prevents swapping implementations.

**Files:** `app/contexts/plan/plan_service.py:65-66`, `app/contexts/auth/auth_service.py:115`, `app/domain/repositories.py`

**Suggested fix:**
```python
class PlanService:
    def __init__(self, repo: IPlanRepository, ...):
        self._repo = repo
```
Wire up in `app/dependencies.py` using the existing protocol definitions.

### 13. Make `PlanRequest` validators extensible

**Problem:** Adding a new plan type (e.g., "couch-to-10K") requires modifying the `PlanRequest` class and its 7 validators. The `_MILEAGE_CONFIG` dict (`app/schemas/plan_schemas.py:46-54`) is built at module load time but validators reference it directly.

**Files:** `app/schemas/plan_schemas.py`

**Suggested fix:** Extract validation rules into a `PlanValidationRegistry` that can be extended without modifying existing code:
```python
class PlanValidationRegistry:
    _rules: dict[str, PlanValidationRule] = {}

    @classmethod
    def register(cls, plan_type: str, rule: PlanValidationRule): ...
```

### 14. Implement feature flags

**Problem:** `app/infrastructure/config.py:57` has a "Feature Flags" comment section but no actual flags defined. No runtime feature toggling exists.

**Files:** `app/infrastructure/config.py:57`

**Suggested fix:** Add a simple feature flag system:
```python
class Settings(BaseSettings):
    feature_flags: dict[str, bool] = {}

    def is_enabled(self, flag: str) -> bool:
        return self.feature_flags.get(flag, False)
```
Or integrate a lightweight library like `unleash` or `flagpole`. Start with environment-variable-driven flags.

### 15. Add an event bus for domain events

**Problem:** `app/domain/events.py` defines domain event dataclasses, but the adaptation system uses direct service calls rather than domain events. This creates tight coupling between plan creation and adaptation evaluation.

**Files:** `app/domain/events.py`, `app/contexts/plan/adaptation/`, `app/web/routers/runs.py`

**Suggested fix:** Introduce a simple in-process event bus:
```python
class EventBus:
    _handlers: dict[type, list[Callable]] = {}

    def subscribe(self, event_type: type, handler: Callable): ...
    def publish(self, event: DomainEvent): ...
```
Publish events like `RunLogged`, `PlanCreated`, `PlanAdapted` and let interested services subscribe.

### 16. Add `ge`/`le` constraints to `PerformancePlanRequest.target_distance`

**Problem:** `app/schemas/plan_schemas.py:502` has no `ge`/`le` constraints — only a `@field_validator` checks against `SUPPORTED_DISTANCES`.

**Files:** `app/schemas/plan_schemas.py:502`

**Suggested fix:** Add `Annotated[str, Field(...)]` with a pattern or enum constraint, or convert to an `Enum` type.

---

## P3 — Modularity & Hygiene

### 17. Remove schema-to-infrastructure dependency

**Problem:** `app/schemas/__init__.py:32` imports from `infrastructure/config.py` (`HealthResponse` uses `settings.app_version`). This creates a dependency from schemas to infrastructure, violating the layer dependency rule.

**Files:** `app/schemas/__init__.py:32`

**Suggested fix:** Move `HealthResponse` to `app/infrastructure/health.py` or make it a plain schema without referencing `settings`. The health endpoint can construct the response with runtime values.

### 18. Remove ORM model imports from web layer

**Problem:** `app/main.py:198` home endpoint imports `RunLog` model directly. The web layer should not import ORM models.

**Files:** `app/main.py:198`

**Suggested fix:** Create a `DashboardService` or `StatsService` in `app/contexts/runner/` that returns a dataclass or dict. The endpoint calls the service.

### 19. Reduce direct repository imports in routers

**Problem:** `app/web/routers/runs.py:21-29` imports `SQLAlchemyPlanRepository`, `SQLAlchemyRunRepository`, `FeedbackService`, `RacePredictorService`, and enrichment functions directly, bypassing service-layer abstractions.

**Files:** `app/web/routers/runs.py:21-29`

**Suggested fix:** Create a `RunService` facade in `app/contexts/runner/` that encapsulates all run-related operations. The router imports only this service.

### 20. Consolidate small adaptation modules

**Problem:** `app/contexts/plan/adaptation/` has 20 modules, some very small (`_helpers.py`, `skipped_detector.py`). These could potentially be merged for easier navigation.

**Files:** `app/contexts/plan/adaptation/`

**Suggested fix:** Merge modules with fewer than 30 lines into related siblings. For example, `_helpers.py` utilities can move into the modules that use them. `skipped_detector.py` can merge into `adherence_evaluator.py`.

### 21. Standardize logging format

**Problem:** `app/contexts/plan/plan_service.py:80` uses f-string in logger, while `app/main.py:135` uses `%` formatting. Inconsistent logging style.

**Files:** `app/contexts/plan/plan_service.py:80`, `app/main.py:135`

**Suggested fix:** Standardize on lazy `%`-style formatting for all logging calls (avoids string interpolation when log level is disabled):
```python
logger.info("Plan %s created for user %s", plan_id, user_id)
```
Or configure a logging formatter that handles structured logging.

### 22. Add secret rotation support

**Problem:** Once `SECRET_KEY` and `ENCRYPTION_KEY` are set, they cannot be rotated without invalidating all existing JWTs and encrypted Strava tokens.

**Files:** `app/infrastructure/config.py`, `app/contexts/auth/auth_service.py:27`, `app/models/encrypted_type.py`

**Suggested fix:** Support key versioning:
- Store the key version in the JWT payload
- Maintain a `SECRET_KEY_V2` alongside `SECRET_KEY`
- On verification, try both keys
- On creation, always use the latest key
- Same pattern for `ENCRYPTION_KEY` with Fernet key rotation

---

## Appendix: Current Architecture Strengths

These are areas where the codebase is already well-designed and should be preserved:

- **Domain-Driven Design with bounded contexts** (`app/contexts/`) — clear separation of plan, runner, nutrition, and auth concerns
- **Repository Protocol pattern** (`app/domain/repositories.py`) — `Protocol` classes with `TYPE_CHECKING` guard keep the domain layer pure
- **Core layer purity** (`app/core/`) — no I/O, no ORM imports, pure calculation libraries
- **Comprehensive input validation** — Pydantic schemas with 7+ validators on `PlanRequest`, field-level constraints on all numeric/string fields
- **Strong authentication** — Google OAuth with JWK caching, HTTP-only cookies, session timeout, activity throttling
- **Security middleware** — CSP headers, CSRF via Content-Type check, request size limits, HSTS, Permissions-Policy
- **Encrypted sensitive fields** — Fernet encryption for Strava tokens via `EncryptedString` type
- **Adaptation engine modularity** — 20 focused modules behind a thin facade, easily extensible
- **Test coverage breadth** — 55 test files across core, services, routers, and security
- **Alembic migrations** — real migration testing in test fixtures, not just `create_all()`
- **Production secret validation** — `SECRET_KEY` strength check, separate `ENCRYPTION_KEY` requirement, key reuse prevention
- **Docker security** — pinned base image with SHA256 digest, non-root user, restricted permissions on pdf_cache

---

## Quick Wins (under 30 minutes each)

1. Add `pytest-cov` to `requirements.txt` and configure coverage thresholds (#10)
2. Add `ge`/`le` constraints to `PerformancePlanRequest.target_distance` (#16)
3. Standardize logging format across the codebase (#21)
4. Add CORS middleware with explicit allowed origins (#1)
5. Add rate limiting to plan generation endpoint (#2)
6. Split `app/schemas/plan_schemas.py` into focused modules (#9)
7. Add type hints to `PlanService` methods (#11)

---

## Recommended Order of Implementation

1. **Security first:** #1 (CORS), #2 (rate limiting), #3 (debug endpoint)
2. **Maintainability:** #6 (decompose main.py), #7 (split dependencies.py), #8 (simplify runs router)
3. **Extensibility:** #12 (inject interfaces), #14 (feature flags), #15 (event bus)
4. **Hygiene:** #17 (schema-infra dependency), #18 (ORM in web layer), #19 (router abstractions)
5. **Long-term:** #4 (refresh tokens), #22 (secret rotation), #5 (anonymous user cleanup)
