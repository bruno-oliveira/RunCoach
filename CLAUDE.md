# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RunCoach is a FastAPI web application that generates personalized running training plans with nutrition guidance. Users input their current weekly mileage, target race distance (5K, 10K, Half Marathon, Marathon, or Trail), and training duration to receive a customized multi-week plan. The application supports Google OAuth authentication and adaptive training plans based on user performance data.

## Development Commands

```bash
# Start development server with hot reload
python3 -m uvicorn app.main:app --reload --port 8000

# Install dependencies
python3 -m pip install -r requirements.txt

# Run tests
python3 -m pytest tests/ -v

# Run a specific test suite (tests are grouped under tests/test_<area>/)
python3 -m pytest tests/test_routers/ -v      # API endpoint tests
python3 -m pytest tests/test_services/ -v     # context-service tests
python3 -m pytest tests/test_core/ -v         # pure-logic tests

# Lint, format, and type-check (enforced in CI)
ruff check app/ tests/
ruff format --check app/ tests/
pyright

# Smoke-test plan generation
python3 -c "from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator; TrainingPlanGenerator().generate_plan(20, 10, 8)"

# Browser-verify a UI change (signed-in user + live plan, on a DISPOSABLE db copy)
python3 scripts/verify_ui.py        # copies runcoach.db, migrates it, prints a session cookie
python3 scripts/dev_verify.py       # serves :8011 against the copy
python3 scripts/verify_ui.py --check  # hash of the real db, to prove it never changed
```

### Never write to `runcoach.db`

`runcoach.db` holds real dev data, and there is **no seed file and no WAL backup
beside it** — an `UPDATE` without a preceding `SELECT` is unrecoverable. It has
already cost a developer their local Intervals connection.

Use `scripts/verify_ui.py` to get a signed-in user and a live plan on a throwaway
copy. If you must touch a real row, `SELECT` and record the current values first.

Two related traps worth knowing:

- **`last_activity`** — `_resolve_user` rejects a session whose user has a stale
  `last_activity`, so a hand-minted JWT 403s every page for no visible reason.
  `verify_ui.py` sets it.
- **`alembic.ini` leaves `sqlalchemy.url` empty on purpose** so the `alembic` CLI
  honours `DATABASE_URL`. Do not hardcode a value back into it: a literal there
  silently wins over the environment, so `DATABASE_URL=... alembic upgrade head`
  would migrate `./runcoach.db` instead of your scratch database.

## Deployment

Deployed to Fly.io (region: sjc). Deploy with `fly deploy`.

Docker build: `docker build -t runcoach .`

## Architecture

The codebase is organized into **domain-driven bounded contexts** with clean dependency direction (web → application → contexts → core / domain; infrastructure implements interfaces). See `ARCHITECTURAL_IMPROVEMENT.md` for the design rationale.

### Project Structure

```
app/
├── __init__.py
├── main.py              # FastAPI application entry point + factory
├── dependencies.py      # Per-context DI: lazy service factories + repo factories
├── exceptions.py        # Custom exception hierarchy
├── constants.py         # Cross-cutting constants (distances etc.)
├── utils.py
├── rate_limit.py
├── template_helpers.py  # Jinja2 templates + static-URL helpers
├── domain/              # Pure domain layer (no I/O, no ORM)
│   ├── coaching.py      # Coaching domain value objects
│   └── repositories.py  # Repository protocols (IPlanRepository, IRunRepository, IUserRepository)
├── core/                # Pure calculation libraries (no I/O)
│   ├── training/        # VDOT, phases, mileage, workout building
│   ├── coaching/        # Coaching feedback, notes, pattern analysis
│   └── race/            # Race protocols
├── contexts/            # Bounded contexts (application + per-context services)
│   ├── plan/            # Plan generation, adaptation, view, repositories
│   │   ├── plan_service.py, plan_view_service.py, plan_lifecycle_service.py
│   │   ├── repositories.py            # SQLAlchemyPlanRepository
│   │   ├── plan_type_registry.py
│   │   ├── generators/                # Plan generators (road, beginner, fitness, performance)
│   │   └── adaptation/                # Adaptation engine (signals, evaluators, adjusters)
│   ├── runner/          # Runner profile, fitness, run enrichment
│   │   ├── repositories.py            # SQLAlchemyRunRepository
│   │   ├── profile/                   # RunnerProfile dataclass + builder
│   │   ├── fitness/                   # FitnessService, performance, predictions, HR zones
│   │   └── enrichment/                # Run enrichment + week pulse
│   ├── nutrition/       # NutritionEngine, meal database
│   └── auth/            # AuthService, repositories.py (SQLAlchemyUserRepository)
├── infrastructure/      # I/O + 3rd-party adapters
│   ├── config.py        # pydantic-settings (was app/config.py)
│   ├── database/        # SQLAlchemy engine, SessionLocal, get_db (engine.py)
│   ├── export/          # PDF generation (ReportLab)
│   └── integrations/    # Strava, GPX, FIT
├── application/         # Cross-context orchestration
│   └── cleanup_service.py  # Inactive-account retention task
├── web/                 # Web layer
│   ├── routers/         # FastAPI routers (auth, plans, runs, analytics, strava, etc.)
│   ├── middleware.py    # CSRF, security headers, anonymous-user cookie, size limits
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS + JS
├── models/              # SQLAlchemy ORM models (kept centralized for relationship config)
│   ├── base.py, user.py, training_plan.py, weekly_plan.py, daily_workout.py,
│   ├── plan_customization.py, run_log.py, run_feedback.py, readiness_log.py,
│   ├── favorite_recipe.py, encrypted_type.py
├── schemas/             # Pydantic request/response models
├── migrations/          # Startup data backfills (vdot, effort classes)
└── data/
    └── meals.json       # Meal database

tests/
├── conftest.py
├── test_core/           # Pure-logic tests
├── test_services/       # Context-service tests
├── test_routers/        # API endpoint tests
└── test_security/       # CSRF, headers, ownership
```

### Dependency rule

- `web/routers/` → `application/`, `contexts/`, `schemas/`
- `application/` → `contexts/`, `core/`, `domain/`
- `contexts/<X>/` → `core/`, `domain/`, sibling context only via `application/` or events
- `core/` imports nothing from `contexts/`, `infrastructure/`, or SQLAlchemy
- `infrastructure/` implements protocols defined in `domain/`

### Core Components

- **`app/main.py`** - FastAPI application entry point (`create_app` factory). Sets up logging, runs startup Alembic migrations, mounts static files, registers middleware, routers, and the global exception handler. Includes the `/health` check.

- **`app/infrastructure/config.py`** - Centralized configuration using `pydantic-settings`. Loads from environment variables and `.env` file. Contains app settings, database URL, logging level, training plan constraints, and OAuth settings (`secret_key`, `google_client_id`).

- **`app/dependencies/`** - FastAPI dependency injection package, split into `database` / `services` / `auth`. Provides database sessions, cached service factories (`TrainingPlanGenerator`, `NutritionEngine`, `PDFGenerator`, `AuthService`, `FavoritesService`, …), repository factories, and `get_current_user` / `get_optional_user` (Bearer tokens or HTTP-only cookies).

- **`app/schemas/`** - Pydantic request/response models package. Includes `PlanRequest`, `GoogleAuthRequest`, `Token`, `UserResponse`, `RunLogCreate`, `RunLogResponse`, `AdaptivePlanRequest`, and various workout/nutrition schemas.

- **`app/contexts/auth/auth_service.py`** - `AuthService` class for authentication. Handles Google OAuth token verification, JWT creation/verification (`PyJWT`), and user creation/retrieval (via `SQLAlchemyUserRepository`).

- **`app/web/routers/plans.py`** (and the focused split modules `plan_generation.py`, `plan_view.py`, `plan_list.py`, `plan_sharing.py`, `plan_adjustments.py`) - Plan endpoints: generate, view, customize, share, download.

- **`app/web/routers/nutrition.py`** - Nutrition endpoints: `/randomize-meals`, `/nutrition-plan/{plan_id}`.

- **`app/web/routers/auth.py`** - Authentication endpoints under `/api/auth`: `POST /google`, `GET /me`, `POST /logout`. Sets HTTP-only cookies for browser navigation.

- **`app/web/routers/runs.py`** - Run logging CRUD (`/api/runs`) plus adaptive endpoints (`/api/adaptive/*`).

- **`app/contexts/plan/plan_service.py`** - `PlanService` encapsulating plan lifecycle (creation, customization, deletion). Delegates queries to `SQLAlchemyPlanRepository`.

- **`app/contexts/plan/adaptation/`** - `AdaptationService` facade plus focused modules (signal computation, evaluators, adjusters). Analyzes effort trends, pace consistency, adherence; can auto-adjust future weeks.

- **`app/contexts/plan/generators/plan_generator.py`** - `TrainingPlanGenerator`: weekly training schedule orchestrator. Delegates to `core/training/*` for phases, mileage, workout building.

- **`app/contexts/nutrition/nutrition_engine.py`** - `NutritionEngine` for meal blueprints (scoring-based meal selection with seeded variety).

- **`app/infrastructure/export/pdf_generator.py`** - `PDFGenerator` (ReportLab) producing the downloadable plan PDF. Accepts `PlanExportDTO` so it isn't coupled to the ORM.

- **`app/contexts/plan/generators/performance_plan_generator.py`** - `PerformancePlanGenerator` for VDOT-based plans from a user's actual run data.

- **`app/contexts/plan/repositories.py`** - `SQLAlchemyPlanRepository` (implements `IPlanRepository`).
- **`app/contexts/runner/repositories.py`** - `SQLAlchemyRunRepository` (implements `IRunRepository`).
- **`app/contexts/auth/repositories.py`** - `SQLAlchemyUserRepository` (implements `IUserRepository`).

- **`app/infrastructure/database/engine.py`** - SQLAlchemy engine, `SessionLocal`, `get_db` generator dependency. SQLite PRAGMAs (WAL, foreign keys, busy timeout) live here.

- **`app/models/__init__.py`** - Exports all models and configures SQLAlchemy relationships between them.

- **`app/models/user.py`** - `User` model with Google OAuth fields (`google_id`, `email`, `name`, `picture`) and `plans_generated` counter.

- **`app/models/run_log.py`** - `RunLog` model for tracking runs with fields for distance, duration, pace, heart rate, cadence, elevation, workout type, and perceived effort. The user-entered/Strava `workout_type` is kept separate from `inferred_workout_type` (+ `inferred_type_confidence`), which is filled in from pace/HR/distance/splits by `app/contexts/runner/fitness/workout_type_classifier.py`. Read via the `effective_workout_type` property — it prefers the explicit label when present and falls back to inference for untagged Strava runs. Backfilled on startup by `app/migrations/startup.py` (`backfill_inferred_workout_types`).

- **`app/exceptions.py`** - Custom exception hierarchy with user-friendly messages: `RunCoachException` (base), `ValidationException`, `UnrealisticGoalException`, `InsufficientTimeException`, `InadequateBaseException`, `PlanGenerationException`, `DatabaseException`.

### Data Flow

1. User authenticates via Google OAuth -> `/api/auth/google` endpoint
2. User submits form on index.html -> `/generate-plan` endpoint
3. `PlanRequest` Pydantic model validates input (checks min weeks for distance, base mileage requirements)
4. `TrainingPlanGenerator.generate_plan()` creates weekly workout schedule
5. `NutritionEngine.generate_weekly_meal_plan()` creates nutrition blueprint
6. Data saved to SQLite via SQLAlchemy, rendered to plan.html template
7. Optional PDF download via `/download-pdf/{plan_id}`
8. User logs runs via `/api/runs` endpoints
9. `AdaptivePlanGenerator` analyzes performance and generates personalized recommendations

### Templates

Located under `app/web/templates/`:
- `base.html`, `index.html`, `plan.html`, `my_plans.html`, `plan_shared.html`, `analytics.html`, `recipes.html`, etc.
- `components/` - Reusable components (nav, modal, workout_card, change_plan_modal, week_card, etc.)

## Testing

Tests use pytest with fixtures defined in `tests/conftest.py`:

- **`test_db`** - In-memory SQLite database session
- **`client`** - FastAPI TestClient with database override
- **`plan_generator`** - TrainingPlanGenerator instance
- **`nutrition_engine`** - NutritionEngine instance
- **`nutrition_engine_seeded`** - NutritionEngine with fixed seed (42) for reproducibility
- **Sample parameter fixtures** - `sample_5k_params`, `sample_marathon_params`, `sample_trail_params`

Test layout (grouped by layer):
- `tests/test_core/` - pure-logic tests (plan generation, nutrition, training math)
- `tests/test_services/` - context-service tests (adaptation, fitness, favorites, …)
- `tests/test_routers/` - API endpoint tests
- `tests/test_security/` - CSRF, security headers, ownership

## Configuration

Configuration via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | RunCoach | Application name |
| `APP_VERSION` | 1.0.0 | Application version |
| `DEBUG` | False | Debug mode |
| `DATABASE_URL` | sqlite:///./runcoach.db | Database connection string |
| `LOG_LEVEL` | INFO | Logging level |
| `SECRET_KEY` | (required) | JWT signing key |
| `GOOGLE_CLIENT_ID` | (required) | Google OAuth client ID |
| `SMTP_HOST` | (empty) | Outbound-nudge mail host. **Empty means send nothing** — the null mailer logs and reports failure rather than pretending |
| `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | 587 / empty | SMTP credentials. Port 465 switches to implicit TLS; otherwise STARTTLS unless `SMTP_STARTTLS=false` |
| `CRON_SECRET` | (empty) | Shared secret for `POST /api/notifications/run`. Empty makes the endpoint 404 |
| `PUBLIC_BASE_URL` | http://localhost:8000 | Absolute origin for links inside emails. Must be set in production |
| `NUDGE_MIN_INTERVAL_DAYS` | 4 | Floor between two nudge emails to the same runner |

Outbound coaching nudges are off in every direction until configured — see
`docs/outbound-nudges-setup.md` for the guards, the schedule, and how to check
who *would* be mailed before anything goes out.

Training constraints are configured in `app/infrastructure/config.py` (settings) and `app/core/training/training_config.py` (`DISTANCE_CONSTRAINTS` registry):
- Minimum/maximum weeks per distance
- Minimum mileage requirements per distance

## Code Style

- **Imports**: Standard library, third-party, then local. Use absolute imports for app modules (`from app.contexts... import ...`) — the dominant convention across the codebase
- **Types**: Type hints on all function signatures using `Union[type, type]` or `type | type` syntax
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Line length**: 88 characters max (configured in pyproject.toml via ruff)
- **Database**: Use dependency injection for sessions, close in `finally` blocks
- **Validation**: Use Pydantic models with `@field_validator` and `@model_validator` decorators
- **Logging**: Use `logging.getLogger(__name__)` pattern
- **Docstrings**: Google style with Args/Returns sections

## Key Patterns

- **Router-based architecture**: Endpoints organized in `app/web/routers/` with `APIRouter`
- **Core module separation**: Pure calculation logic in `app/core/` (no I/O, no ORM), separate from the web layer
- **Model separation**: Each SQLAlchemy model in its own file under `app/models/`
- **Dependency injection**: Services and database sessions via FastAPI `Depends()`
- **Bounded contexts**: Business logic lives in per-context services under `app/contexts/` (plan, runner, nutrition, auth)
- **Persistence boundary (CQRS-lite)**: Writes go through repositories; read-heavy paths use query modules; routers carry no raw `db.query` (see `ARCHITECTURE_PERSISTENCE.md`)
- **Centralized config**: Settings loaded via pydantic-settings with environment variable support
- **Custom exceptions**: Domain exceptions with `user_message`/`suggestion`, mapped to HTTP by a global handler registered in `create_app`
- **Google OAuth authentication**: JWT tokens stored in HTTP-only cookies for browser navigation
- **Adaptive training**: Plans adjust based on logged run performance data
- **Training plan validation**: Pydantic validators raise custom exceptions caught by routes
- **Nutrition engine scoring**: Meals scored by protein/fiber contribution with randomness for variety
- **PDF generation**: ReportLab "story" list of flowables
- **Normalized relational schema**: Plans are stored as related tables (`training_plans` → `weekly_plans` → `daily_workouts`), Alembic-managed. A denormalized `plan_data` JSON snapshot is also kept for rendering; `favorite_recipes.recipe_data` uses a proper `JSON` column
- **Seeded randomization**: `NutritionEngine` accepts `random_seed` for reproducible results