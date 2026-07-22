"""Pydantic schemas — re-exported from domain-specific modules."""

# HealthResponse moved to app.infrastructure.health to avoid the
# schemas → infrastructure dependency. Re-exported for backward compat.
from app.infrastructure.health import HealthResponse
from app.schemas.auth_schemas import (
    AuthResponse,
    GoogleAuthRequest,
    Token,
    UserBase,
    UserCreate,
    UserResponse,
)
from app.schemas.intervals_schemas import (
    IntervalsPushRequest,
    IntervalsPushResponse,
    IntervalsStatusResponse,
    IntervalsSyncResponse,
)
from app.schemas.plan_schemas import (
    PerformancePlanRequest,
    PlanRequest,
    PlanRequestBase,
    RaceInfoMixin,
    get_mileage_warning,
    parse_target_distance,
)
from app.schemas.readiness_schemas import (
    ReadinessCheckInCreate,
    ReadinessCheckInResponse,
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

__all__ = [
    "AuthResponse",
    "GoogleAuthRequest",
    "HealthResponse",
    "IntervalsPushRequest",
    "IntervalsPushResponse",
    "IntervalsStatusResponse",
    "IntervalsSyncResponse",
    "PlanRequest",
    "PlanRequestBase",
    "PerformancePlanRequest",
    "RaceInfoMixin",
    "ReadinessCheckInCreate",
    "ReadinessCheckInResponse",
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
