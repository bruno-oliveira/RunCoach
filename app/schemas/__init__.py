"""Pydantic schemas — re-exported from domain-specific modules."""

from app.schemas.plan_schemas import (
    PlanRequest,
    PlanRequestBase,
    PerformancePlanRequest,
    FitnessPlanRequest,
    RaceInfoMixin,
    get_mileage_warning,
    parse_target_distance,
)
from app.schemas.auth_schemas import (
    AuthResponse,
    GoogleAuthRequest,
    Token,
    UserBase,
    UserCreate,
    UserResponse,
)
from app.schemas.run_schemas import (
    RunLogBase,
    RunLogCreate,
    RunLogListResponse,
    RunLogResponse,
    RunLogUpdate,
)
from app.schemas.strava_schemas import (
    StravaStatusResponse,
    StravaSyncResponse,
)

# HealthResponse moved to app.infrastructure.health to avoid the
# schemas → infrastructure dependency. Re-exported for backward compat.
from app.infrastructure.health import HealthResponse


__all__ = [
    "AuthResponse",
    "FitnessPlanRequest",
    "GoogleAuthRequest",
    "HealthResponse",
    "PlanRequest",
    "PlanRequestBase",
    "PerformancePlanRequest",
    "RaceInfoMixin",
    "RunLogBase",
    "RunLogCreate",
    "RunLogListResponse",
    "RunLogResponse",
    "RunLogUpdate",
    "StravaStatusResponse",
    "StravaSyncResponse",
    "Token",
    "UserBase",
    "UserCreate",
    "UserResponse",
    "get_mileage_warning",
    "parse_target_distance",
]
