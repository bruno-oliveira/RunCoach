"""FastAPI dependencies: re-exports from focused submodules.

- ``app.dependencies.database`` — engine, session, repo factories
- ``app.dependencies.services`` — cached service factories
- ``app.dependencies.auth``     — user resolution + ownership helpers
"""

from app.dependencies.auth import (
    ANONYMOUS_USER_COOKIE,
    COOKIE_NAME,
    get_admin_user,
    get_current_user,
    get_optional_user,
    validate_plan_ownership,
    verify_plan_ownership,
)
from app.dependencies.database import (
    SessionLocal,
    engine,
    get_db,
    get_plan_repository,
    get_run_repository,
    get_user_repository,
)
from app.dependencies.services import (
    get_adaptation_service,
    get_auth_service,
    get_coach_narrator,
    get_favorites_service,
    get_intervals_service,
    get_nutrition_engine,
    get_pdf_generator,
    get_performance_plan_generator,
    get_performance_service,
    get_plan_generator,
    get_plan_service,
    get_plan_view_service,
    get_strava_service,
)

__all__ = [
    "ANONYMOUS_USER_COOKIE",
    "COOKIE_NAME",
    "SessionLocal",
    "engine",
    "get_adaptation_service",
    "get_auth_service",
    "get_coach_narrator",
    "get_admin_user",
    "get_current_user",
    "get_favorites_service",
    "get_intervals_service",
    "get_db",
    "get_nutrition_engine",
    "get_optional_user",
    "get_pdf_generator",
    "get_performance_plan_generator",
    "get_performance_service",
    "get_plan_generator",
    "get_plan_repository",
    "get_plan_service",
    "get_plan_view_service",
    "get_run_repository",
    "get_strava_service",
    "get_user_repository",
    "validate_plan_ownership",
    "verify_plan_ownership",
]
