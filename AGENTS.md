# RunCoach Development Guide

## Project Overview
RunCoach is a personalized running training plan generator with nutrition guidance, built with FastAPI. It supports multiple race distances (5K to marathon), Strava integration, adaptive training plans, and performance tracking.

## Quick Start
```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Start development server
python3 -m uvicorn app.main:app --reload --port 8000

# Run tests
python3 -m pytest
```

## Architecture

### Core Structure
```
app/
├── main.py              # FastAPI app factory with lifespan management
├── config.py            # Pydantic settings from environment variables
├── schemas.py           # Request/response validation models
├── dependencies.py      # FastAPI dependency injection
├── routers/             # API endpoints (13 routers)
├── services/            # Business logic (23 services)
├── models/              # SQLAlchemy ORM models (11 models)
├── core/                # Domain logic (training, nutrition, coaching)
├── templates/           # Jinja2 HTML templates
└── static/              # Frontend assets
```

### Key Features
- **Training Plans**: Generate plans for 5K, 10K, Half Marathon, Trail (30K), Marathon
- **VDOT System**: Jack Daniels' VDOT for pace zones and race predictions
- **Adaptive Plans**: Automatically adjusts based on logged performance (requires 3+ runs)
- **Strava Integration**: OAuth sync for activities with automatic workout type mapping
- **Nutrition Guidance**: Personalized based on body weight and training load
- **Performance Plans**: Advanced training for improving race times (6-16 weeks)
- **Readiness Scoring**: Daily readiness tracking for training optimization
- **Triathlon Support**: Multi-sport training plans

### Database Models
- `User` - Authentication and profile
- `TrainingPlan` - Generated training plans
- `WeeklyPlan` / `DailyWorkout` - Plan breakdown
- `RunLog` - Logged runs with metrics (heart rate, cadence, VDOT)
- `RunFeedback` - User feedback on workouts
- `PlanCustomization` - User plan adjustments
- `ReadinessLog` - Daily readiness scores
- `FavoriteRecipe` - Saved nutrition recipes

### Key Services
- `adaptation/AdaptationService` - Plan adaptation logic
- `strava_service.py` - Strava OAuth and activity sync
- `auth_service.py` - JWT authentication
- `plan_service.py` - Plan generation and management
- `readiness_scoring.py` - Readiness calculations
- `training_load_service.py` - Training load metrics

## Development Conventions

### Code Style
- Follow PEP 8, max line length 88
- Type hints on all functions
- snake_case for variables/functions, PascalCase for classes
- Docstrings for all public methods
- Relative imports for local modules

### Database
- Always close sessions: `finally: db.close()`
- Use context managers for resources
- Alembic for migrations (auto-run on startup)

### Validation
- Pydantic models in `schemas.py`
- Custom exceptions in `exceptions.py`
- Distance-specific validation rules in config

### Authentication
- Google OAuth for user authentication
- JWT tokens with configurable expiration
- Anonymous user tracking via cookies

## Testing
```bash
# Run all tests
python3 -m pytest

# Run specific test file
python3 -m pytest tests/test_specific.py

# Run with coverage
python3 -m pytest --cov=app
```

## Configuration
Environment variables (see `.env.example`):
- `SECRET_KEY` - JWT signing key (required for production)
- `GOOGLE_CLIENT_ID` - Google OAuth
- `STRAVA_CLIENT_ID/SECRET` - Strava integration
- `DATABASE_URL` - Database connection (default: SQLite)
- `DEBUG` - Enable debug mode and endpoints

## Deployment
- Docker support via `Dockerfile`
- Fly.io configuration in `fly.toml`
- Render configuration in `render.yaml`
- Auto-migrations on startup
- Health check endpoint at `/health`
