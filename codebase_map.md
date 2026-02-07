# RunCoach Codebase Map

> **Comprehensive reference guide for implementing features in the RunCoach application**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [API Reference](#3-api-reference)
4. [Database Schema](#4-database-schema)
5. [Core Algorithms](#5-core-algorithms)
6. [Service Layer](#6-service-layer)
7. [Authentication & Session Management](#7-authentication--session-management)
8. [Code Patterns & Conventions](#8-code-patterns--conventions)
9. [Development Workflow](#9-development-workflow)
10. [Important Tricky Implementations](#10-important-tricky-implementations)

---

## 1. Project Overview

### Purpose
RunCoach is a **personalized running training platform** built with FastAPI that provides:

- Tailored training plans for multiple race distances (5K, 10K, Half Marathon, Trail Running 30K, Marathon)
- Performance-based plan adaptation using logged run data
- Nutrition guidance with meal suggestions and hydration recommendations
- Strength training integration with an exercise database
- Recipe management and favorites
- Google OAuth authentication with anonymous user support
- PDF export for offline plan access

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| **Web Framework** | FastAPI | 0.104.1 | Modern async web framework with auto-documentation |
| **Server** | Uvicorn | 0.24.0 | ASGI server |
| **Database ORM** | SQLAlchemy | 2.0.23 | Database operations with async support |
| **Database** | SQLite | - | Primary database (configurable) |
| **Templating** | Jinja2 | 3.1.2 | HTML rendering |
| **Authentication** | python-jose | 3.3.0 | JWT token handling |
| **OAuth** | authlib | 1.2.1 | Google OAuth integration |
| **PDF Generation** | ReportLab | 4.0.7 | PDF document export |
| **Validation** | Pydantic | 2.5.0 | Data validation and settings |
| **Testing** | pytest | 7.4.3 | Test framework |
| **HTTP Client** | httpx | 0.25.2 | Async HTTP for tests |
| **Caching** | cachetools | 5.3.2 | TTL caching |

### Architecture Patterns

```
┌─────────────────────────────────────────────────────────────┐
│                        Presentation Layer                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   HTML     │  │   JSON     │  │  Static    │           │
│  │ Templates  │  │   API      │  │   Files    │           │
│  └────────────┘  └────────────┘  └────────────┘           │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                         Routers (API Layer)                  │
│  ┌────────┐ ┌──────┐ ┌────┐ ┌──────────┐ ┌────────┐      │
│  │  auth  │ │plans │ │runs│ │nutrition│ │strength│      │
│  └────────┘ └──────┘ └────┘ └──────────┘ └────────┘      │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                        Services Layer                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │ Adaptation   │ │    Plan      │ │     Nutrition         ││
│  │   Service    │ │   Service    │ │     Service           ││
│  └──────────────┘ └──────────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                         Core Engine Layer                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │    Plan      │ │  Nutrition   │ │          PDF          ││
│  │  Generator   │ │   Engine     │ │      Generator       ││
│  └──────────────┘ └──────────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                        Data Models                            │
│  ┌──────┐ ┌────────┐ ┌──────┐ ┌────────┐ ┌──────────────┐  │
│  │ User │ │  Plan  │ │ Log  │ │ Recipe │ │    Models    │  │
│  └──────┘ └────────┘ └──────┘ └────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key Architectural Principles:**
- **Separation of Concerns**: Presentation → Business Logic → Data
- **Dependency Injection**: Services injected via FastAPI dependencies
- **Stateless Services**: Business logic classes are stateless
- **Type Safety**: Pydantic validation throughout

---

## 2. Directory Structure

```
/Users/boliveira/Documents/RunCoach/
│
├── app/                              # Main application package
│   ├── __init__.py                   # Package initialization
│   ├── main.py                       # FastAPI app entry point, routes, middleware
│   ├── config.py                     # Settings management, env variables, logging
│   ├── dependencies.py               # Dependency injection (DB, auth, services)
│   ├── auth_service.py               # Google OAuth authentication service
│   ├── meal_database.py              # Meal database management
│   ├── schemas.py                    # Pydantic models for validation
│   ├── exceptions.py                 # Custom exception definitions
│   ├── nutrition_models.py          # Nutrition-related models
│   │
│   ├── core/                         # Core business logic engines
│   │   ├── plan_generator.py         # Training plan generation algorithm
│   │   ├── adaptive_plan_generator.py # Adaptive plans based on run logs
│   │   ├── nutrition_engine.py       # Meal and nutrition planning
│   │   └── pdf_generator.py          # PDF document generation
│   │
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── base.py                   # Declarative base
│   │   ├── user.py                   # User authentication model
│   │   ├── training_plan.py          # Training plan storage
│   │   ├── weekly_plan.py            # Weekly plan details
│   │   ├── daily_workout.py          # Individual workout storage
│   │   ├── run_log.py                # Run logging model
│   │   ├── plan_customization.py     # Plan customization tracking
│   │   ├── strength_exercise.py     # Exercise database
│   │   ├── daily_strength_workout.py # Generated workouts
│   │   ├── user_favorite_workout.py  # User's favorite workouts
│   │   └── favorite_recipe.py        # User's favorite recipes
│   │
│   ├── routers/                      # API route handlers
│   │   ├── auth.py                   # Authentication endpoints
│   │   ├── plans.py                  # Plan generation/management
│   │   ├── runs.py                   # Run logging & performance tracking
│   │   ├── nutrition.py             # Nutrition plan endpoints
│   │   ├── recipes.py                # Recipe search & favorites
│   │   └── strength.py               # Strength training endpoints
│   │
│   ├── services/                     # Business logic services
│   │   ├── adaptation_service.py     # Performance-based plan adaptation
│   │   ├── nutrition_service.py      # Nutrition-related services
│   │   ├── plan_service.py           # Plan management operations
│   │   ├── merge_service.py          # Anonymous user data merging
│   │   └── strength_workout_generator.py # Workout generator
│   │
│   ├── data/                         # Static data files
│   │   ├── meals.json                # All meal database
│   │   ├── meals_breakfast.json     # Breakfast options
│   │   ├── meals_lunch.json          # Lunch options
│   │   ├── meals_post_workout.json   # Post-workout meals
│   │   ├── meals_dinner.json         # Dinner options
│   │   └── meals_snack.json          # Snack options
│   │
│   ├── static/                       # Static assets
│   │   ├── css/                      # Stylesheets
│   │   │   ├── base.css              # Base styles
│   │   │   ├── components.css        # Component styles
│   │   │   └── plan.css              # Plan page styles
│   │   └── js/                       # JavaScript
│   │       ├── api.js                # API client
│   │       ├── auth.js               # Auth handling
│   │       ├── modal.js              # Modal dialogs
│   │       └── plan.js               # Plan interactivity
│   │
│   └── templates/                    # Jinja2 HTML templates
│       ├── base.html                # Base template (extensible)
│       ├── index.html               # Home page
│       ├── plan.html                # Plan view page
│       ├── my_plans.html            # User plans list
│       ├── recipes.html             # Recipe search
│       ├── recipe_detail.html       # Recipe detail
│       ├── strength_training.html   # Strength training page
│       ├── workout_detail.html      # Workout detail shareable
│       └── components/              # Reusable components
│           ├── nav.html              # Navigation
│           ├── modal.html            # Modal dialogs
│           ├── macros.html           # Template macros
│           └── workout_card.html     # Workout card component
│
├── tests/                            # Test suite
│   ├── conftest.py                  # Pytest configuration
│   ├── test_api.py                  # API endpoint tests
│   ├── test_plan_generator.py       # Plan generation tests
│   ├── test_plan_generator_v2.py    # Plan generation v2 tests
│   └── test_nutrition_engine.py     # Nutrition engine tests
│
├── runcoach.db                      # SQLite database
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata & tool config
├── Dockerfile                       # Docker configuration
├── fly.toml                         # Fly.io deployment config
├── .env.example                     # Environment variables template
└── AGENTS.md                        # Agent guidelines

```

---

## 3. API Reference

### Authentication Routes (`/api/auth`)

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| POST | `/api/auth/google` | Google OAuth sign-in | No |
| GET | `/api/auth/me` | Get current user info | Yes |
| POST | `/api/auth/logout` | Logout and clear cookies | Yes |

### Plan Routes (`/plans/`, `/api/plan/`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| POST | `/generate-plan` | Generate new training plan | Optional | HTML/JSON |
| GET | `/plan/{plan_id}` | View existing plan details | Optional | HTML |
| GET | `/my-plans` | List user's plans | Yes | HTML |
| POST | `/customize-plan` | Customize a plan's workouts | Optional | JSON |
| GET | `/api/plan/{plan_id}/performance` | Get performance analysis | Yes | JSON |
| POST | `/api/plan/{plan_id}/adapt` | Adapt future weeks based on performance | Yes | JSON |
| POST | `/api/plan/{plan_id}/save` | Save/claim plan to account | Yes | JSON |
| GET | `/download-pdf/{plan_id}` | Download plan as PDF | No | PDF |

### Run Logging Routes (`/api/runs`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| POST | `/api/runs` | Create new run log | Yes | JSON |
| GET | `/api/runs` | List paginated run logs with filters | Yes | JSON |
| GET | `/api/runs/{run_id}` | Get specific run log | Yes | JSON |
| PUT | `/api/runs/{run_id}` | Update run log | Yes | JSON |
| DELETE | `/api/runs/{run_id}` | Delete run log | Yes | JSON |

### Adaptive Routes (`/api/adaptive`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| GET | `/api/adaptive/metrics` | Get current fitness metrics | Yes | JSON |
| GET | `/api/adaptive/suggestions` | Get training suggestions | Yes | JSON |
| GET | `/api/adaptive/performance-gaps` | Analyze gaps vs. race requirements | Yes | JSON |
| POST | `/api/adaptive/generate-plan` | Generate adaptive plan based on run history | Yes | JSON |

### Nutrition Routes (`/nutrition/`, `/api/recipes`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| POST | `/randomize-meals` | Generate new meal options for a plan | No | HTML |
| GET | `/nutrition-plan/{plan_id}` | View nutrition plan details | Optional | HTML |
| GET | `/api/recipes` | Search recipes with filters | No | JSON |
| GET | `/api/recipes/favorites` | Get user's favorite recipes | Yes | JSON |
| POST | `/api/recipes/favorite` | Add recipe to favorites | Yes | JSON |
| DELETE | `/api/recipes/favorite/{id}` | Remove favorite recipe | Yes | JSON |

### Strength Training Routes (`/api/strength`, `/strength-training`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| GET | `/api/strength/exercises` | List exercises with filters | No | JSON |
| GET | `/api/strength/exercises/{id}` | Get specific exercise | No | JSON |
| GET | `/api/strength/workout/today` | Get today's workout | No | JSON |
| GET | `/api/strength/workout/{date}` | Get workout by date | No | JSON |
| GET | `/api/strength/workout/week` | Get week's workouts | No | JSON |
| GET | `/api/strength/favorites` | Get user's favorite workouts | Yes | JSON |
| POST | `/api/strength/favorites` | Add workout to favorites | Yes | JSON |
| DELETE | `/api/strength/favorites/{id}` | Remove favorite | Yes | JSON |
| GET | `/strength-training` | Strength training page | No | HTML |
| GET | `/strength-training/{workout_id}` | Workout detail page (shareable) | No | HTML |

### Recipe Routes (`/recipes`)

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| GET | `/recipes` | Recipe search/browse page | No | HTML |
| GET | `/recipes/{recipe_name}` | Recipe detail page (shareable) | No | HTML |

### Health & Debug Routes

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| GET | `/health` | Health check endpoint | No |
| GET | `/debug/config` | Debug configuration check | No |
| GET | `/debug/test-auth` | Test authentication service | No |

### Root Routes

| Method | Endpoint | Purpose | Auth Required | Response |
|--------|----------|---------|---------------|----------|
| GET | `/` | Home page (with optional auth) | No | HTML |

---

## 4. Database Schema

### User Model (`/app/models/user.py`)

```python
class User(Base):
    id: str  # UUID v4, Primary Key
    google_id: str  # Unique, Indexed
    email: str  # Unique, Indexed
    name: str
    picture: str  # Avatar URL
    created_at: datetime
    last_activity: datetime
    plans_generated: int  # Counter for stats
```

**Indexes:**
- `idx_user_google_id` on `google_id`
- `idx_user_email` on `email`

---

### TrainingPlan Model (`/app/models/training_plan.py`)

```python
class TrainingPlan(Base):
    id: str  # UUID v4, Primary Key
    user_id: str  # Foreign Key → users.id, Indexed
    current_weekly_km: float  # User's current mileage
    target_distance: str  # e.g., "21.1", "30.0", "42.2"
    weeks_duration: int
    max_runs_per_week: int
    created_at: datetime
    plan_data: Text  # JSON string of plan structure
    nutrition_plan_data: Text  # JSON string of nutrition plan
```

**Indexes:**
- `idx_training_plan_user_id` on `user_id`

---

### WeeklyPlan Model (`/app/models/weekly_plan.py`)

```python
class WeeklyPlan(Base):
    id: str  # UUID v4, Primary Key
    training_plan_id: str  # Foreign Key → training_plans.id
    week_number: int
    total_km: float
    workout_distribution: Text  # JSON string of distribution
```

---

### DailyWorkout Model (`/app/models/daily_workout.py`)

```python
class DailyWorkout(Base):
    id: str  # UUID v4, Primary Key
    weekly_plan_id: str  # Foreign Key → weekly_plans.id
    day_of_week: int  # 1-7 (1=Monday, 7=Sunday)
    workout_type: str  # easy, tempo, interval, long, hill, rest, recovery
    distance_km: float
    intensity: str  # low, medium, high
    notes: Text
```

---

### RunLog Model (`/app/models/run_log.py`)

```python
class RunLog(Base):
    id: str  # UUID v4, Primary Key
    user_id: str  # Foreign Key → users.id, Indexed
    training_plan_id: str  # Foreign Key → training_plans.id
    daily_workout_id: str  # Foreign Key → daily_workouts.id
    date: datetime  # Indexed
    distance_km: float
    duration_minutes: float
    avg_pace_min_km: float
    avg_heart_rate: int
    max_heart_rate: int
    avg_cadence: int
    elevation_gain_m: int
    notes: Text
    workout_type: str
    perceived_effort: int  # 1-10 RPE scale
    created_at: datetime
```

**Indexes:**
- `idx_run_log_user_id` on `user_id`
- `idx_run_log_date` on `date`
- `idx_run_log_user_date` on `user_id` + `date` (composite)

---

### PlanCustomization Model (`/app/models/plan_customization.py`)

```python
class PlanCustomization(Base):
    id: str  # UUID v4, Primary Key
    training_plan_id: str  # Foreign Key → training_plans.id
    week_number: int
    adjustment_type: str
    adjustment_value: str
    created_at: datetime
```

---

### StrengthExercise Model (`/app/models/strength_exercise.py`)

```python
class StrengthExercise(Base):
    id: str  # UUID v4, Primary Key
    name: str
    exercise_id: str
    force: str  # push, pull, static
    level: str  # beginner, intermediate, expert
    mechanic: str  # compound, isolation
    equipment: str
    primary_muscles: Text  # JSON array
    secondary_muscles: Text  # JSON array
    instructions: Text  # JSON array
    category: str
    gif_url: str
    images: Text  # JSON array
    is_running_related: bool
    is_bodyweight: bool
    is_dumbbell: bool
```

---

### DailyStrengthWorkout Model (`/app/models/daily_strength_workout.py`)

```python
class DailyStrengthWorkout(Base):
    id: str  # UUID v4, Primary Key
    date: str  # YYYY-MM-DD
    title: str
    description: Text
    warmup_exercises: Text  # JSON array
    main_exercises: Text  # JSON array
    cooldown_exercises: Text  # JSON array
    warmup_duration: int  # minutes
    main_duration: int  # minutes
    cooldown_duration: int  # minutes
    total_duration: int  # minutes
    primary_focus: str  # upper body, lower body, core, full body
    secondary_focus: str
    difficulty: str  # beginner, intermediate, expert
```

---

### UserFavoriteWorkout Model (`/app/models/user_favorite_workout.py`)

```python
class UserFavoriteWorkout(Base):
    id: str  # UUID v4, Primary Key
    user_id: str  # Foreign Key → users.id
    workout_id: str  # Foreign Key → daily_strength_workouts.id
    notes: Text
    created_at: datetime
```

---

### FavoriteRecipe Model (`/app/models/favorite_recipe.py`)

```python
class FavoriteRecipe(Base):
    id: str  # UUID v4, Primary Key
    user_id: str  # Foreign Key → users.id
    recipe_name: str
    meal_type: str
    recipe_data: Text  # JSON
    created_at: datetime
```

---

## 5. Core Algorithms

### Training Plan Generation Algorithm

**Location:** `/app/core/plan_generator.py`

#### Phase Calculation

Training plans are divided into phases with dynamic ratios based on total weeks:

```python
def _calculate_phases(weeks: int) -> Dict[str, int]:
    base_min, build_min, peak_min, taper_min = 3, 3, 1, 2

    if weeks <= 10:
        base = round(weeks * 0.4)        # 40% base
        build = round(weeks * 0.3)       # 30% build
        peak = 1
        taper = weeks - base - build - peak
    elif weeks <= 14:
        base = round(weeks * 0.45)       # 45% base
        build = round(weeks * 0.3)       # 30% build
        peak = 1
        taper = weeks - base - build - peak
    elif weeks <= 18:
        base = round(weeks * 0.5)        # 50% base
        build = round(weeks * 0.25)      # 25% build
        peak = round(weeks * 0.1)        # 10% peak
        taper = weeks - base - build - peak
    else:
        base = round(weeks * 0.5)        # 50% base
        build = round(weeks * 0.25)      # 25% build
        peak = round(weeks * 0.1)        # 10% peak
        taper = weeks - base - build - peak

    return {"base": base, "build": build, "peak": peak, "taper": taper}
```

**Phase Principles:**
- Progressive loading: Base → Build → Peak → Taper
- Minimum phase durations enforced (3, 3, 1, 2 weeks)
- Phase ratios adjust based on total weeks available

---

#### Weekly Mileage Progression

```python
# Example calculation for a 12-week 10K plan:
current_km = 20.0
target_distance = 10.0
weeks = 12

phases = {"base": 4, "build": 4, "peak": 1, "taper": 2}
peak_km = 35.0  # Calculated based on race distance

# Base phase: Build from current to 70% of peak
base_end_target = peak_km * 0.70  # 24.5km

for week in range(phases['base']):
    if self._is_recovery_week(week_number, 'base'):
        week_km = current_week_km * 0.75  # Recovery reduction
    else:
        weeks_passed = count_non_recovery_weeks(week)
        weeks_remaining = total_non_recovery - weeks_passed
        needed_increase = base_end_target - current_week_km
        weekly_increase = needed_increase / weeks_remaining
        week_km = current_week_km + weekly_increase
```

**Key Rules:**
- **Recovery weeks:** Every 4th week, reduce mileage by 25%
- **Linear progression:** Calculate needed increase, divide by remaining non-recovery weeks
- **Phase targets:**
  - Base → 70% of peak mileage
  - Build → 100% of peak mileage

---

#### Long Run Distance Calculation

```python
def _calculate_long_run_distance(
    total_km: float,
    target_distance: float,
    weeks: int,
    week_number: int,
    phase: str,
    is_recovery_week: bool
) -> float:
    # Long run ratio increases with race distance
    long_run_ratio = self._calculate_long_run_ratio(phase, week_number, phases, target_distance, is_recovery_week, weeks)

    # Apply ratio to total weekly distance
    long_run_base = total_km * long_run_ratio

    # Cap based on race distance
    long_run_cap = {
        5.0: 8.0,
        10.0: 15.0,
        21.1: 20.0,
        30.0: 24.0,
        42.2: 32.0
    }.get(target_distance, target_distance * 0.77)

    # Minimum for race day readiness
    min_long_run = target_distance * 0.25

    return round(max(min_long_run, min(long_run_base, long_run_cap)), 1)
```

**Long Run Ratios by Race Distance:**
- **5K:** ~30% of weekly mileage
- **10K:** ~35-40% of weekly mileage
- **10 Mile/Half Marathon:** ~35-40% of weekly mileage
- **Marathon:** ~35% of weekly mileage

**Capping:**
- Prevents over-acumulation of long run distance
- Ensures long run is never > 80% of weekly mileage

---

#### Workout Distribution Algorithm

```python
def _get_workout_distribution(total_km, max_runs, phase, is_recovery_week, week_number, phases, target_distance):
    long_runs = 1  # Always one long run per week

    # Quality workouts vary by phase
    if phase == 'base' or is_recovery_week:
        quality_workouts = 0
    elif phase == 'build':
        quality_workouts = 2 if max_runs >= 5 else 1
    elif phase == 'peak':
        quality_workouts = 2 if max_runs >= 5 else 1
    else:  # taper
        quality_workouts = 0

    # Trail running special case - alternate hill and interval
    if target_distance == 30.0 and quality_workouts > 0:
        if week_number % 4 in [1, 2]:
            quality_workouts = {'hill': quality_workouts}
        else:
            quality_workouts = {'interval': quality_workouts}

    # Calculate remaining
    running_days = max_runs - 1 - quality_workouts
    easy_runs = max(0, running_days)
    rest_days = 7 - (max_runs + 1)  # Recovery day is separate
```

**Distribution Rules:**
- Long run: 1 per week (always Saturday)
- Recovery day: 1 per week (always Tuesday, day 2)
- Quality workouts: 0-2 per week (base/taper = 0, build/peak = 1-2)
- Easy runs: Fill remaining days
- Rest days: Fill any remaining slots

**Workout Types:**
- `recovery`: Stretching/cross-training, 0 distance
- `long`: Long run, primary workout of week
- `easy`: Easy recovery pace runs
- `tempo`: Sustained threshold effort
- `interval`: High-intensity repeats with recovery
- `hill`: Hill repeats (trail running focus)
- `rest`: Complete rest

---

#### Weekly Mileage Constraints

```python
MIN_WEEKLY_DISTANCE = {
    5.0: 15.0,
    10.0: 25.0,
    21.1: 30.0,
    30.0: 40.0,
    42.2: 48.0,
}

MAX_WEEKLY_DISTANCE = {
    5.0: 40.0,
    10.0: 64.0,
    21.1: 72.0,
    30.0: 80.0,
    42.2: 96.0,
}

MIN_WEEKS_BY_DISTANCE = {
    5.0: 6,
    10.0: 8,
    21.1: 10,
    30.0: 12,
    42.2: 16,
}
```

---

### Adaptive Plan Adaptation Algorithm

**Location:** `/app/services/adaptation_service.py`

#### Performance Analysis

```python
def analyze_performance(training_plan_id: str, db: session) -> Dict:
    # Get all logged runs for plan
    runs = db.query(RunLog).filter(RunLog.training_plan_id == training_plan_id).all()

    # Calculate adherence rate
    total_logged = len(runs)
    planned_workouts = db.query(DailyWorkout).filter(
        DailyWorkout.workout_type != "rest"
    ).count()
    adherence_rate = (total_logged / planned_workouts * 100) if planned_workouts > 0 else 0

    # Effort trend analysis
    efforts = [r.perceived_effort for r in runs if r.perceived_effort is not None]
    avg_effort = sum(efforts) / len(efforts) if efforts else None

    # Compare first half vs second half
    mid_point = len(efforts) // 2
    first_half_avg = sum(efforts[:mid_point]) / mid_point
    second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
    diff = second_half_avg - first_half_avg

    if diff > 1.0:
        effort_trend = "increasing"  # Fatigue building
    elif diff < -1.0:
        effort_trend = "decreasing"  # Adapting well
    else:
        effort_trend = "stable"

    # Pace consistency (coefficient of variation)
    paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km]
    if len(paces) >= 2:
        avg_pace = sum(paces) / len(paces)
        variance = sum((p - avg_pace) ** 2 for p in paces) / len(paces)
        std_dev = variance ** 0.5
        cv = (std_dev / avg_pace) * 100 if avg_pace > 0 else 100
    else:
        cv = None
```

**Key Metrics:**
- **Adherence Rate:** (Logged workouts / Planned workouts) × 100
- **Effort Trend:** First half vs second half average (1-10 scale)
- **Pace Consistency:** Coefficient of variation (lower = more consistent)

---

#### Adaptation Decision Logic

```python
def should_adapt_plan(training_plan_id: str, db: Session) -> Tuple[bool, str]:
    MIN_RUNS_FOR_ADAPTATION = 3  # Minimum runs required

    analysis = self.analyze_performance(training_plan_id, db)

    if analysis["total_runs"] < MIN_RUNS_FOR_ADAPTATION:
        return False, "Not enough data yet"

    avg_effort = analysis.get("avg_effort")
    effort_trend = analysis.get("effort_trend")
    adherence = analysis.get("adherence_rate", 0)

    # Adaptation triggers
    if avg_effort >= 9:  # Too hard
        return True, "Effort consistently too high - reducing load"
    elif avg_effort <= 3:  # Too easy
        return True, "Effort consistently too low - increasing challenge"
    elif effort_trend == "increasing" and avg_effort > 7:  # Fatigue building
        return True, "Fatigue building - adding recovery"
    elif adherence < 60:  # Too aggressive
        return True, "Low adherence - plan may be too aggressive"

    return False, "No adaptation needed - plan is appropriate"
```

**Adaptation Thresholds:**
| Condition | Threshold | Action |
|----------|-----------|--------|
| Too hard | Effort ≥ 9 | Reduce distances by 10% |
| Too easy | Effort ≤ 3 | Increase distances by 10% |
| Fatigue building | Trend increasing AND avg > 7 | Reduce distances by 5% |
| Too aggressive | Adherence < 60% | Reduce distances by 5% |
| Minimum data | 3+ runs required | Must have logs |

---

#### Plan Adaptation Execution

```python
def adapt_future_weeks(training_plan_id: str, db: Session, current_week: int) -> Dict:
    # Get analysis
    analysis = self.analyze_performance(training_plan_id, db)
    avg_effort = analysis.get("avg_effort")

    # Determine adjustment factor
    if avg_effort >= 9:
        distance_multiplier = 0.9  # Reduce by 10%
    elif avg_effort <= 3:
        distance_multiplier = 1.1  # Increase by 10%
    else:
        distance_multiplier = 0.95  # Conservative reduction

    # Get future weeks only (current week + 1 onwards)
    future_weeks = db.query(WeeklyPlan).filter(
        WeeklyPlan.training_plan_id == training_plan_id,
        WeeklyPlan.week_number > current_week
    ).all()

    changes = []
    for week in future_weeks:
        workouts = db.query(DailyWorkout).filter(
            DailyWorkout.weekly_plan_id == week.id
        ).all()

        for workout in workouts:
            if workout.workout_type != "rest" and workout.distance_km > 0:
                old_distance = workout.distance_km
                new_distance = round(old_distance * distance_multiplier, 1)

                workout.distance_km = new_distance
                workout.notes = f"Adapted: {workout.notes or ''} (adjusted from {old_distance}km based on performance)"

        # Update weekly total
        new_total = sum(w.distance_km for w in workouts if w.distance_km)
        week.total_km = new_total

    db.commit()
    return {"adapted": True, "changes": changes}
```

**Adaptation Rules:**
- Only modifies **future weeks** (past/current untouched)
- Applies uniform multiplier to all non-rest workouts
- Records changes with historical notes
- Recalculates weekly totals

---

### Fitness Scoring Algorithm

**Location:** `/app/core/adaptive_plan_generator.py`

```python
def _calculate_fitness_score(weekly_km: float, pace: float, improvement: float, run_count: int) -> int:
    score = 0

    # Volume component (40 points max)
    volume_score = min(40, (weekly_km / 50) * 40)  # 50km/week = full points
    score += volume_score

    # Pace component (30 points max)
    if pace:
        pace_score = max(0, 30 - (pace - 4.0) * 10)  # 4:00 min/km = 30 points
        score += pace_score

    # Improvement component (20 points max)
    improvement_score = min(20, max(0, improvement * 2))  # 10% improvement = 20 points
    score += improvement_score

    # Consistency component (10 points max)
    consistency_score = min(10, (run_count / 20) * 10)  # 20 runs = full points
    score += consistency_score

    return int(min(100, max(0, score)))
```

**Scoring Components (0-100 scale):**

| Component | Weight | Full Points Criteria |
|-----------|--------|---------------------|
| Volume | 40 pts | 50km/week |
| Pace | 30 pts | 4:00 min/km |
| Improvement | 20 pts | 10% improvement |
| Consistency | 10 pts | 20 runs |

---

### Nutrition Calculation Algorithm

**Location:** `/app/core/nutrition_engine.py`

```python
def calculate_daily_calories(weight_kg: float, weekly_km: float, target_distance: float) -> int:
    # BMR using Mifflin-St Jeor (simplified)
    bmr = weight_kg * 22

    # Activity multiplier based on weekly mileage
    if weekly_km < 20:
        activity_multiplier = 1.375
    elif weekly_km < 40:
        activity_multiplier = 1.55
    elif weekly_km < 60:
        activity_multiplier = 1.725
    else:
        activity_multiplier = 1.9

    # Calorie needs (kcal/day)
    daily_calories = bmr * activity_multiplier

    # Training day adjustment
    training_day_adjustment = weekly_km * 1.5  # ~150 calories per km

    return round(daily_calories + training_day_adjustment)

def calculate_macros(daily_calories: int, weight_kg: float, target_distance: float) -> Dict[str, float]:
    # Protein (1.8g per kg)
    protein_grams = weight_kg * 1.8
    protein_calories = protein_grams * 4

    # Fiber (25-30g for most runners)
    fiber_grams = 28.0

    # Carbs and fats distribution
    remaining = daily_calories - protein_calories
    carb_calories = remaining * 0.55  # 55% of remaining
    fat_calories = remaining * 0.45    # 45% of remaining

    carb_grams = carb_calories / 4
    fat_grams = fat_calories / 9

    return {
        "calories": daily_calories,
        "protein_g": protein_grams,
        "carbs_g": carb_grams,
        "fat_g": fat_grams,
        "fiber_g": fiber_grams
    }
```

**Nutrition Guidelines:**
- **Mileage tiers** (<20km, 20-40km, 40-60km, >60km) determine activity multiplier
- **Training days** add ~150 calories per km run
- **Protein**: 1.8g per kg body weight
- **Fiber**: Target 28g daily
- **Carb/Fat**: 55%/45% distribution after protein allocation

---

## 6. Service Layer

### AdaptationService (`/app/services/adaptation_service.py`)

**Purpose:** Analyze run performance and adapt training plans dynamically

**Key Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `analyze_performance(plan_id, db)` | Calculate adherence, effort, pace consistency | Dict with metrics |
| `should_adapt_plan(plan_id, db)` | Determine if adaptation is needed | Tuple[bool, str] |
| `adapt_future_weeks(plan_id, db, current_week)` | Adjust future weeks' distances | Dict with changes |
| `detect_skipped_workouts(plan_id, db)` | Count missed workouts | Dict with counts |

**Adaptation Logic Summary:**
1. Requires 3+ logged runs before adapting
2. Checks effort thresholds (≤3, ≥9, trend >1)
3. Checks adherence threshold (<60%)
4. Applies multipliers (0.9x, 0.95x, 1.1x)
5. Only modifies future weeks

---

### NutritionService (`/app/services/nutrition_service.py`)

**Purpose:** Nutrition planning and meal guidance

**Key Methods:**
- Meal matching and randomization
- Dietary restriction filtering
- Calorie adjustment for weight goals

---

### PlanService (`/app/services/plan_service.py`)

**Purpose:** Training plan management operations

**Key Methods:**
- CRUD operations for training plans
- Plan customization handling
- Data validation and consistency checks

---

### MergeService (`/app/services/merge_service.py`)

**Purpose:** Merge anonymous user data when authenticating

**Merge Algorithm Steps:**

```python
@staticmethod
def merge_anonymous_user(anonymous_user_id: str, authenticated_user_id: str, db: Session) -> Dict:
    # 1. Validation checks
    if not anonymous_user_id or anonymous_user_id == authenticated_user_id:
        return {"training_plans": 0, "run_logs": 0}

    anonymous_user = db.query(User).filter(User.id == anonymous_user_id).first()
    if not anonymous_user or anonymous_user.google_id:
        return {"training_plans": 0, "run_logs": 0}

    # 2. Migrate training plans
    plans = db.query(TrainingPlan).filter(
        TrainingPlan.user_id == anonymous_user_id
    ).all()
    for plan in plans:
        plan.user_id = authenticated_user_id

    # 3. Migrate run logs
    logs = db.query(RunLog).filter(
        RunLog.user_id == anonymous_user_id
    ).all()
    for log in logs:
        log.user_id = authenticated_user_id

    # 4. Create merge record
    # 5. Delete anonymous user
    db.delete(anonymous_user)
    db.commit()

    return {"training_plans": len(plans), "run_logs": len(logs)}
```

---

### StrengthWorkoutGenerator (`/app/services/strength_workout_generator.py`)

**Purpose:** Generate daily strength training workouts for runners

**Workout Components:**
- **Warmup:** Dynamic stretching (5-10 minutes)
- **Main Exercises:** Primary focus exercises
- **Cooldown:** Static stretching (5 minutes)

**Workout Focuses:**
- **Lower Body:** Quadriceps, hamstrings, glutes, calves
- **Upper Body:** Abs, obliques, chest, back
- **Core:** Abs, obliques, lower back
- **Full Body:** Comprehensive routine

**Generation Logic:**
1. Select focus based on rotation schedule
2. Choose 4-6 exercises for focus area
3. Balance muscle groups (push/pull, agonist/antagonist)
4. Target 20-30 minutes total duration

---

## 7. Authentication & Session Management

### Google OAuth Flow

**Location:** `/app/auth_service.py`

**Architecture:**
- **OAuth Type:** Google OAuth 2.0 with ID tokens
- **Token Type:** JWT for app sessions
- **Algorithms:** RS256 (Google), HS256 (app)

**Token Verification:**

```python
async def verify_google_token(id_token: str) -> Optional[dict]:
    # 1. Fetch Google's public keys (1-hour cache)
    # 2. Validate issuer: "https://accounts.google.com"
    # 3. Validate audience against settings.google_client_id
    # 4. Verify signature with RS256
    # 5. Return user data
```

**Key Validations:**
- **Issuer:** Must be Google
- **Audience:** Matches app's client ID
- **Signature:** Verified with public keys
- **Expiration:** Token not expired

---

### Token Creation

```python
def create_access_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=1))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=HS256)
```

**Token Payload:**
```python
{
    "sub": user_id,      # Subject (user ID)
    "email": email,     # User email
    "exp": timestamp,   # Expiration
}
```

---

### Cookie Management

**Cookie Configuration:**

| Cookie | Purpose | Settings |
|--------|---------|----------|
| `access_token` | Authenticated session JWT | `httponly=True`, `samesite="lax"`, `max_age=24h`, `secure=!debug` |
| `anonymous_user_id` | Anonymous user tracking | `httponly=True`, `samesite="lax"`, `max_age=30d`, `secure=!debug` |

**Cookie Security Settings:**
- **httponly=True:** Prevents XSS token theft
- **samesite="lax":** CSRF protection with usability
- **secure=!settings.debug:** HTTPS in production, HTTP in dev
- **max_age:** Explicit expiration time

---

### Dependency Injection

**Location:** `/app/dependencies.py`

**Required Authentication:**

```python
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    # Token source priority:
    # 1. Authorization: Bearer <token> header
    # 2. access_token cookie

    # Verify JWT, query user, check timeout
    # Raises 401 if invalid/expired
```

**Optional Authentication:**

```python
async def get_optional_user(
    request: Request,
    db: Session,
    auth_service: AuthService
) -> Optional[User]:
    # Returns None instead of raising exceptions
    # Allows anonymous access to non-critical endpoints
```

---

### Inactivity Timeout

**Configuration:** `/app/config.py`

```python
session_timeout_minutes: int = 30  # Default
```

**Checking in `get_current_user()`:**

```python
if user.last_activity:
    timeout_delta = timedelta(minutes=settings.session_timeout_minutes)
    if (datetime.utcnow() - user.last_activity) > timeout_delta:
        raise HTTPException(401, "Session expired due to inactivity")
```

---

### Anonymous User Flow

**1. Anonymous Plan Generation:**
```python
# User generates plan without logging in

# Create anonymous user
anonymous_user = User(email=f"anon_{uuid}@temp.io", ...)

# Set anonymous_user_id cookie
response.set_cookie(
    key="anonymous_user_id",
    value=anonymous_user.id,
    max_age=30 * 24 * 60 * 60,  # 30 days
)
```

**2. User Authenticates:**
```python
# Read anonymous cookie
anonymous_user_id = request.cookies.get("anonymous_user_id")

# Verify Google token, get user
user = auth_service.get_or_create_user(db, google_user_data, anonymous_user_id)

# Merge data if anonymous
if anonymous_user_id and anonymous_user_id != user.id:
    MergeService.merge_anonymous_user(db, anonymous_user_id, user.id)

# Set auth cookie, delete anonymous cookie
response.set_cookie(key="access_token", ...)
response.delete_cookie(key="anonymous_user_id", ...)
```

**3. Logout:**
```python
response.delete_cookie(key="access_token", ...)
response.delete_cookie(key="anonymous_user_id", ...)
```

---

## 8. Code Patterns & Conventions

### Naming Conventions

```python
# Variables/functions: snake_case
weekly_progression = []
user_id = "..."
calculate_phases()

# Classes: PascalCase
class TrainingPlanGenerator:
    class User:
        pass

# Constants: UPPER_CASE
MIN_RUNS_FOR_ADAPTATION = 3
COOKIE_NAME = "access_token"
```

---

### Type Hints

```python
# Always include type hints
def create_plan(
    self,
    current_km: float,
    target_distance: float,
    weeks: int,
) -> tuple[TrainingPlan, list[dict[str, Any]]]:
    pass

# Use modern union syntax (Python 3.10+)
user: User | None  # Instead of Optional[User]
plan_generator: TrainingPlanGenerator | None = None

# Complex types
def get_runs(self, user_id: str) -> list[RunLog]:
    pass
```

---

### Database Operation Patterns

**Retrieval:**

```python
# Single result (can be None)
def get_plan(self, plan_id: str) -> TrainingPlan | None:
    return self.db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id
    ).first()

# Multiple results
def get_user_plans(self, user_id: str) -> list[TrainingPlan]:
    return self.db.query(TrainingPlan).filter(
        TrainingPlan.user_id == user_id
    ).all()
```

**Creation/Update:**

```python
def update_plan_data(self, plan_id: str, plan_data: list[dict]) -> TrainingPlan | None:
    training_plan = self.get_plan(plan_id)
    if not training_plan:
        return None

    training_plan.plan_data = json.dumps(plan_data)
    self.db.commit()
    return training_plan
```

**Bulk Operations:**

```python
# Insert multiple related records efficiently
def save_weekly_plans(self, weekly_plans: list[dict], daily_workouts: list[dict]):
    self.db.bulk_insert_mappings(WeeklyPlan, weekly_plans)
    self.db.bulk_insert_mappings(DailyWorkout, daily_workouts)
    self.db.commit()
```

**Error Handling:**

```python
try:
    result = some_operation()
    db.commit()
    logger.info(f"Operation successful")
    return result
except Exception as e:
    db.rollback()
    logger.error(f"Operation failed: {e}")
    raise
```

**Session Closing:**

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # Always close!
```

---

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.info(f"Plan created: {plan_id}")
logger.warning(f"Adherence low: {adherence_rate}%")
logger.error(f"Failed to update user: {e}")
```

---

### Caching Pattern

```python
from cachetools import TTLCache

user_plans_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes

def get_user_plans(user_id: str, db: Session) -> list[TrainingPlan]:
    cache_key = f"plans_{user_id}"

    if cache_key in user_plans_cache:
        plans = user_plans_cache[cache_key]
        logger.info(f"Using cached plans for user {user_id}")
    else:
        plans = db.query(TrainingPlan).filter(
            TrainingPlan.user_id == user_id
        ).all()
        user_plans_cache[cache_key] = plans
        logger.info(f"Cached plans for user {user_id}")

    return plans

# Invalidate on modification
def invalidate_user_cache(user_id: str):
    user_plans_cache.pop(f"plans_{user_id}", None)
```

---

### Router Patterns

**Router Definition:**

```python
router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.post("")
async def create_run_log(
    run_log: RunLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Return JSON
```

**HTML Response:**

```python
@router.get("/plan/{plan_id}", response_class=HTMLResponse)
async def view_plan(
    plan_id: str,
    request: Request,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    return templates.TemplateResponse("plan.html", {
        "request": request,
        "plan": plan,
        "user": current_user
    })
```

**JSON Response:**

```python
@router.get("/api/plan/{plan_id}/performance")
async def get_plan_performance(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    adaptation_service: AdaptationService = Depends(get_adaptation_service),
    db: Session = Depends(get_db),
):
    analysis = adaptation_service.analyze_performance(plan_id, db)
    return analysis  # Auto-serialized as JSON
```

---

### Validation with Pydantic

```python
class RunLogCreate(BaseModel):
    date: datetime
    distance_km: float = Field(gt=0, description="Distance must be positive")
    duration_minutes: float = Field(gt=0, description="Duration must be positive")
    avg_pace_min_km: float | None = None
    perceived_effort: int = Field(ge=1, le=10, description="Effort 1-10")
    workout_type: str
    notes: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-15T07:00:00",
                "distance_km": 5.0,
                "duration_minutes": 30.0,
                "avg_pace_min_km": 6.0,
                "perceived_effort": 5,
                "workout_type": "easy"
            }
        }
```

---

### Error Handling

```python
# Custom exceptions in /app/exceptions.py
class ValidationException(Exception):
    pass

class PlanGenerationException(Exception):
    pass

class InsufficientTimeException(Exception):
    def __init__(self, message: str, suggestion: str):
        self.message = message
        self.suggestion = suggestion

# Usage
if weeks < min_weeks:
    raise InsufficientTimeException(
        f"Training for {target_display} requires at least {min_weeks} weeks",
        f"Consider extending your training to {min_weeks} weeks."
    )
```

---

## 9. Development Workflow

### Startup Commands

**Development Server:**
```bash
python3 -m uvicorn app.main:app --reload --port 8000
```

**Install Dependencies:**
```bash
python3 -m pip install -r requirements.txt
```

**Run Tests:**
```bash
pytest
pytest -v  # Verbose output
pytest tests/test_plan_generator.py -v  # Specific test file
```

**Type Checking:**
```bash
# Check pyproject.toml for linting commands
ruff check .
# or
python3 -m ruff check .
```

**Test PDF Generation:**
```bash
python3 -c "from app.core.pdf_generator import PDFGenerator; from app.core.plan_generator import TrainingPlanGenerator; TrainingPlanGenerator().generate_plan(20, 10, 8)"
```

**Database Migrations:**
```bash
python3 migrate_add_workout_links.py
```

---

### Testing Approach

**Test Structure:**
```python
# tests/conftest.py - Shared fixtures
@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def plan_generator():
    return TrainingPlanGenerator()
```

**Example Test:**
```python
def test_plan_generation_distance(db):
    generator = TrainingPlanGenerator()
    plan, _ = generator.generate_plan(
        current_km=20.0,
        target_distance=10.0,
        weeks=8,
        max_runs_per_week=4
    )

    # Verify total weeks
    assert len(plan) == 8

    # Verify progressive mileage
    first_week_total = sum(w['distance_km'] for w in plan[0]['workouts'])
    last_week_total = sum(w['distance_km'] for w in plan[-1]['workouts'])
    assert last_week_total > first_week_total
```

---

### Configuration

**Environment Variables (`.env`):**
```bash
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///runcoach.db
GOOGLE_CLIENT_ID=your-google-client-id
DEBUG=true
```

**Settings Location:** `/app/config.py`

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///runcoach.db"
    google_client_id: str = ""
    secret_key: str = "dev-secret-key"
    debug: bool = True
    session_timeout_minutes: int = 30

    class Config:
        env_file = ".env"
```

---

## 10. Important Tricky Implementations

### 1. Backward Compatibility in Plan Generator

**Location:** `/app/core/plan_generator.py:~375`

```python
# Ensures new plan_gen logic doesn't break existing tests
is_backward_compatible_call = (
    phase == 'build' and
    not is_recovery_week and
    week_number == 1 and
    phases is None and
    target_distance == 10.0
)

if is_backward_compatible_call:
    return self._get_workout_distribution_simple(total_km, max_runs, week_number)
```

**Why:** Allows feature additions without breaking existing test suite.

---

### 2. Double Distance Calculation Fix

**Location:** `/app/core/plan_generator.py:~665`

```python
# Quality workouts must not exceed 85% of long run
max_quality_distance = long_run_distance * 0.85

for key in quality_distances:
    if quality_distances[key] > max_quality_distance:
        quality_distances[key] = round(max_quality_distance, 1)

quality_total = sum(quality_distances.values())
easy_total = remaining_km - quality_total

# Handle case where easy runs would be too long
max_easy_distance = long_run_distance * 0.95
actual_easy_total = min(easy_total, total_max_easy)

# Redistribute lost distance to quality workouts
if actual_easy_total < easy_total and quality_total > 0:
    lost_distance = easy_total - actual_easy_total
    scaling_factor = (quality_total + lost_distance) / quality_total

    for key in quality_distances:
        quality_distances[key] = round(quality_distances[key] * scaling_factor, 1)

    # FINAL SAFETY CHECK: Ensure no quality workout exceeds long run
    for key in quality_distances:
        if quality_distances[key] > max_quality_distance:
            quality_distances[key] = round(max_quality_distance, 1)
```

**Why:** Complex redistribution when easy runs are capped. Must ensure training principle (long run is longest) isn't violated.

---

### 3. Recovery Week State Handling

**Location:** `/app/core/plan_generator.py:~480`

```python
for week in range(phases['base']):
    week_number = week + 1
    if self._is_recovery_week(week_number, 'base'):
        week_km = current_week_km * 0.75  # Recovery reduction
        current_week_km = week_km  # Reset to recovery level
    else:
        # Calculate how much distance we need to cover
        weeks_passed = sum(1 for i in range(week) if not self._is_recovery_week(i + 1, 'base'))
        total_non_recovery = sum(1 for i in range(phases['base']) if not self._is_recovery_week(i + 1, 'base'))
        weeks_remaining = total_non_recovery - weeks_passed
```

**Why:** Recovery weeks reset mileage, so progress calculation must exclude recovery weeks to avoid wrong totals.

---

### 4. Anonymous User Merging Validation

**Location:** `/app/services/merge_service.py`

```python
# Prevent merging already-linked or invalid accounts
if not anonymous_user_id or anonymous_user_id == authenticated_user_id:
    return {"training_plans": 0, "run_logs": 0}

anonymous_user = db.query(User).filter(User.id == anonymous_user_id).first()
if not anonymous_user or anonymous_user.google_id:
    return {"training_plans": 0, "run_logs": 0}
```

**Why:** Prevents security issues where someone could merge an already-linked account or non-existent user.

---

### 5. Workout Scheduling Convention

**Location:** `/app/core/plan_generator.py:~750`

```python
def _schedule_workout_types(distribution, phase, week_number, is_recovery_week):
    workout_types = [None] * 7

    # Recovery always on Day 2 (Tuesday)
    workout_types[1] = 'recovery'

    # Long run always on Day 6 (Saturday)
    workout_types[5] = 'long'

    # Quality workouts prefer middle of week (Days 3-4)
    quality_slots = [2, 3, 4]
    for day_idx in quality_slots:
        if distribution['hill'] > 0:
            workout_types[day_idx] = 'hill'
        elif distribution['interval'] > 0:
            workout_types[day_idx] = 'interval'
        elif distribution['tempo'] > 0:
            workout_types[day_idx] = 'tempo'
```

**Why:** Ensures consistent schedule across all plans for user familiarity.

**Day Mapping:**
- Day 1 = Monday
- Day 2 = Tuesday (Recovery)
- Day 3 = Wednesday
- Day 4 = Thursday
- Day 5 = Friday
- Day 6 = Saturday (Long Run)
- Day 7 = Sunday

---

### 6. Plan Validation Rules

**Location:** `/app/core/plan_generator.py:~815`

```python
def _validate_week_plan(workouts, total_km, phase):
    # No easy run > 105% of long run
    long_run_dist = max([w.get('distance', 0) for w in workouts if w['type'] == 'long'], default=0)
    for workout in workouts:
        if workout['type'] == 'easy':
            if workout.get('distance', 0) > long_run_dist * 1.05:
                return False, f"Easy run > 105% of long run"

    # Total distance tolerance ±5%
    actual_total = sum(w.get('distance', 0) for w in workouts)
    if abs(actual_total - total_km) > total_km * 0.05:
        return False, f"Total distance mismatch"

    # Recovery days must have 0 distance
    for workout in workouts:
        if workout['type'] == 'recovery' and workout.get('distance', 0) != 0:
            return False, f"Recovery day has non-zero distance"

    return True, "Valid"
```

**Why:** Prevents invalid training plans that violate training principles.

---

## Quick Reference - Key Values

### Adaptation Thresholds
- **Minimum runs for adaptation:** 3
- **Effort too hard:** ≥ 9
- **Effort too easy:** ≤ 3
- **Fatigue building:** Trend increasing AND avg > 7
- **Adherence too low:** < 60%

### Distance Constraints
- **Recovery week reduction:** 25% (×0.75)
- **Too hard adjustment:** ×0.9 (10% reduction)
- **Too easy adjustment:** ×1.1 (10% increase)
- **Conservative adjustment:** ×0.95 (5% reduction)

### Training Rules
- **Recovery every:** 4th week
- **Long run max vs weekly:** 80% (except 5K: 35%)
- **Quality workout max:** 85% of long run
- **Easy run max:** 95% of long run

### Session Settings
- **JWT expiration:** 1 day
- **Session timeout:** 30 minutes
- **Anonymous cookie max age:** 30 days
- **Cache TTL:** 5 minutes (plans)

---

**File Locations Summary**

| Feature | File |
|---------|------|
| Plan Generation | `/app/core/plan_generator.py` |
| Plan Adaptation | `/app/services/adaptation_service.py` |
| Nutrition Engine | `/app/core/nutrition_engine.py` |
| Auth Service | `/app/auth_service.py` |
| Data Merging | `/app/services/merge_service.py` |
| Database Models | `/app/models/*.py` |
| API Routes | `/app/routers/*.py` |
| Dependencies | `/app/dependencies.py` |
| Configuration | `/app/config.py` |

---

**Last Updated:** 2024-02-07
**RunCoach Codebase Map** - For internal development reference only