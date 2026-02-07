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

# Run specific test file
python3 -m pytest tests/test_api.py -v
python3 -m pytest tests/test_nutrition_engine.py -v
python3 -m pytest tests/test_plan_generator.py -v

# Test PDF generation
python3 -c "from app.core.pdf_generator import PDFGenerator; from app.core.plan_generator import TrainingPlanGenerator; TrainingPlanGenerator().generate_plan(20, 10, 8)"
```

## Deployment

Deployed to Fly.io (region: sjc). Deploy with `fly deploy`.

Docker build: `docker build -t runcoach .`

## Architecture

### Project Structure

```
app/
├── __init__.py
├── main.py              # FastAPI application entry point
├── config.py            # Centralized configuration (pydantic-settings)
├── dependencies.py      # FastAPI dependency injection
├── schemas.py           # Pydantic request/response schemas
├── exceptions.py        # Custom exception hierarchy
├── auth_service.py      # Authentication service (Google OAuth, JWT)
├── meal_database.py     # Meal data management
├── nutrition_models.py  # Nutrition-related database models
├── core/                # Core business logic
│   ├── __init__.py
│   ├── plan_generator.py        # Training plan generation
│   ├── nutrition_engine.py      # Nutrition plan generation
│   ├── pdf_generator.py         # PDF export using ReportLab
│   └── adaptive_plan_generator.py  # Adaptive plans based on performance
├── models/              # SQLAlchemy database models
│   ├── __init__.py      # Model exports and relationship configuration
│   ├── base.py          # SQLAlchemy Base class
│   ├── user.py          # User model (Google OAuth)
│   ├── training_plan.py # Training plan model
│   ├── weekly_plan.py   # Weekly plan model
│   ├── daily_workout.py # Daily workout model
│   ├── plan_customization.py  # Plan customization model
│   └── run_log.py       # Run logging model for performance tracking
├── routers/
│   ├── __init__.py
│   ├── plans.py         # Plan generation endpoints
│   ├── nutrition.py     # Nutrition endpoints
│   ├── auth.py          # Authentication endpoints (Google OAuth)
│   └── runs.py          # Run logging and adaptive training endpoints
├── services/
│   ├── __init__.py
│   ├── plan_service.py      # Plan business logic
│   ├── nutrition_service.py # Nutrition business logic
│   └── adaptation_service.py # Plan adaptation based on performance
├── templates/           # Jinja2 HTML templates
│   ├── base.html        # Base template with common layout
│   ├── index.html       # Home page with input form
│   ├── plan.html        # Training plan display
│   ├── my_plans.html    # User's saved plans
│   ├── pdf_template.html # PDF generation template
│   └── components/      # Reusable template components
│       ├── nav.html     # Navigation component
│       ├── modal.html   # Modal dialog component
│       ├── workout_card.html  # Workout card component
│       └── macros.html  # Jinja2 macros
├── static/
│   ├── css/
│   │   ├── base.css       # Base styles
│   │   ├── index.css      # Home page styles
│   │   ├── plan.css       # Plan page styles
│   │   ├── my_plans.css   # My plans page styles
│   │   └── components.css # Component styles
│   └── js/
│       ├── api.js         # API client utilities
│       ├── auth.js        # Authentication handling
│       ├── plan.js        # Plan page interactions
│       └── modal.js       # Modal functionality
└── data/
    └── meals.json       # Meal database
tests/
├── __init__.py
├── conftest.py          # Pytest fixtures
├── test_api.py          # API endpoint tests
├── test_nutrition_engine.py # Nutrition engine tests
└── test_plan_generator.py   # Plan generator tests
```

### Core Components

- **`app/main.py`** - FastAPI application entry point. Sets up logging, creates database tables, mounts static files, and includes routers. Includes health check, home page, and debug endpoints.

- **`app/config.py`** - Centralized configuration using `pydantic-settings`. Loads from environment variables and `.env` file. Contains app settings, database URL, logging level, training plan constraints, and OAuth settings (`secret_key`, `google_client_id`).

- **`app/dependencies.py`** - FastAPI dependency injection. Provides database sessions, `TrainingPlanGenerator`, `NutritionEngine`, `PDFGenerator`, and `AuthService` instances. Includes `get_current_user` and `get_optional_user` dependencies for authentication (supports both Bearer tokens and HTTP-only cookies).

- **`app/schemas.py`** - Pydantic models for request/response validation. Includes `PlanRequest`, `GoogleAuthRequest`, `Token`, `UserResponse`, `RunLogCreate`, `RunLogResponse`, `AdaptivePlanRequest`, and various workout/nutrition schemas.

- **`app/auth_service.py`** - `AuthService` class for authentication. Handles Google OAuth token verification via Google's public keys, JWT creation/verification using `python-jose`, and user creation/retrieval.

- **`app/routers/plans.py`** - Plan generation and management endpoints: `/generate-plan`, `/customize-plan`, `/plan/{plan_id}`, `/download-pdf/{plan_id}`. Handles form submissions, validation errors, and plan customization.

- **`app/routers/nutrition.py`** - Nutrition endpoints: `/randomize-meals`, `/nutrition-plan/{plan_id}`. Supports re-randomizing meal suggestions.

- **`app/routers/auth.py`** - Authentication endpoints under `/api/auth`: `POST /google` (Google OAuth login), `GET /me` (current user info), `POST /logout`. Sets HTTP-only cookies for browser navigation.

- **`app/routers/runs.py`** - Run logging and adaptive training endpoints:
  - `/api/runs` - CRUD operations for run logs (distance, duration, heart rate, cadence, elevation, perceived effort)
  - `/api/adaptive/metrics` - Get user's fitness metrics based on run data
  - `/api/adaptive/suggestions` - Get personalized training suggestions
  - `/api/adaptive/performance-gaps` - Analyze gaps vs race requirements
  - `/api/adaptive/generate-plan` - Generate adaptive plans based on performance

- **`app/services/plan_service.py`** - `PlanService` class encapsulating plan creation and retrieval business logic.

- **`app/services/nutrition_service.py`** - `NutritionService` class for nutrition plan management.

- **`app/services/adaptation_service.py`** - `AdaptationService` class for analyzing run performance and adapting training plans. Analyzes effort trends, pace consistency, adherence rates, and can automatically adjust future weeks based on performance.

- **`app/core/plan_generator.py`** - `TrainingPlanGenerator` class that creates weekly training schedules. Implements the 10% rule for mileage progression, calculates peak mileage based on race distance, supports configurable runs per week (3-6), and generates varied daily workouts.

- **`app/core/nutrition_engine.py`** - `NutritionEngine` class that generates personalized meal blueprints. Calculates macronutrient needs based on training volume and body weight, uses scoring system to select optimal meals with variety.

- **`app/core/pdf_generator.py`** - `PDFGenerator` class using ReportLab to create downloadable PDF training plans.

- **`app/core/adaptive_plan_generator.py`** - `AdaptivePlanGenerator` class that generates training plans based on user's actual running data. Calculates fitness metrics from run logs (weekly mileage, pace, heart rate, improvement trends) and adjusts plans accordingly.

- **`app/models/__init__.py`** - Exports all models and configures SQLAlchemy relationships between them.

- **`app/models/user.py`** - `User` model with Google OAuth fields (`google_id`, `email`, `name`, `picture`) and `plans_generated` counter.

- **`app/models/run_log.py`** - `RunLog` model for tracking runs with fields for distance, duration, pace, heart rate, cadence, elevation, workout type, and perceived effort.

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

- `app/templates/base.html` - Base template with common layout and navigation
- `app/templates/index.html` - Input form with distance/weeks/mileage selection
- `app/templates/plan.html` - Training plan display with nutrition blueprint
- `app/templates/my_plans.html` - User's saved training plans
- `app/templates/pdf_template.html` - PDF generation template
- `app/templates/components/` - Reusable components (nav, modal, workout_card, macros)

## Testing

Tests use pytest with fixtures defined in `tests/conftest.py`:

- **`test_db`** - In-memory SQLite database session
- **`client`** - FastAPI TestClient with database override
- **`plan_generator`** - TrainingPlanGenerator instance
- **`nutrition_engine`** - NutritionEngine instance
- **`nutrition_engine_seeded`** - NutritionEngine with fixed seed (42) for reproducibility
- **Sample parameter fixtures** - `sample_5k_params`, `sample_marathon_params`, `sample_trail_params`

Test files:
- `test_api.py` - API endpoint tests
- `test_nutrition_engine.py` - Nutrition engine tests
- `test_plan_generator.py` - Plan generator tests

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

Training constraints are configured in `app/config.py`:
- Minimum/maximum weeks per distance
- Minimum mileage requirements per distance

## Code Style

- **Imports**: Standard library, third-party, then local (relative imports for app modules)
- **Types**: Type hints on all function signatures using `Union[type, type]` or `type | type` syntax
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Line length**: 88 characters max (configured in pyproject.toml via ruff)
- **Database**: Use dependency injection for sessions, close in `finally` blocks
- **Validation**: Use Pydantic models with `@field_validator` and `@model_validator` decorators
- **Logging**: Use `logging.getLogger(__name__)` pattern
- **Docstrings**: Google style with Args/Returns sections

## Key Patterns

- **Router-based architecture**: Endpoints organized in `app/routers/` with `APIRouter`
- **Core module separation**: Business logic in `app/core/` separate from web layer
- **Model separation**: Each SQLAlchemy model in its own file under `app/models/`
- **Dependency injection**: Services and database sessions via FastAPI `Depends()`
- **Service layer**: Business logic in `app/services/` separate from routes
- **Centralized config**: Settings loaded via pydantic-settings with environment variable support
- **Custom exceptions**: Domain exceptions with `user_message` and `suggestion` for UI display
- **Google OAuth authentication**: JWT tokens stored in HTTP-only cookies for browser navigation
- **Adaptive training**: Plans adjust based on logged run performance data
- **Training plan validation**: Pydantic validators raise custom exceptions caught by routes
- **Nutrition engine scoring**: Meals scored by protein/fiber contribution with randomness for variety
- **PDF generation**: ReportLab "story" list of flowables
- **JSON storage**: Plan and nutrition data stored as JSON strings in SQLite TEXT columns
- **Seeded randomization**: `NutritionEngine` accepts `random_seed` for reproducible results