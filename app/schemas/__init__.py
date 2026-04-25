"""Pydantic schemas — re-exported from domain-specific modules."""

from app.schemas.plan_schemas import (
    PlanRequest,
    PlanRequestBase,
    PerformancePlanRequest,
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

from app.config import settings
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = Field(default_factory=lambda: settings.app_version)


__all__ = [
    "AuthResponse",
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
