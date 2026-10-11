"""Pydantic schemas — re-exported from domain-specific modules."""

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
    IntervalsPushWeekRequest,
    IntervalsPushWeekResponse,
    IntervalsStatusResponse,
    IntervalsSyncResponse,
    WatchPlanRequest,
    WatchStatusResponse,
    WatchSyncToggleRequest,
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
from app.schemas.single_run_schemas import (
    SingleRunCreate,
    SingleRunListResponse,
    SingleRunResponse,
)

__all__ = [
    "AuthResponse",
    "GoogleAuthRequest",
    "IntervalsPushRequest",
    "IntervalsPushResponse",
    "IntervalsPushWeekRequest",
    "IntervalsPushWeekResponse",
    "IntervalsStatusResponse",
    "IntervalsSyncResponse",
    "WatchPlanRequest",
    "WatchStatusResponse",
    "WatchSyncToggleRequest",
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
    "SingleRunCreate",
    "SingleRunListResponse",
    "SingleRunResponse",
    "Token",
    "UserBase",
    "UserCreate",
    "UserResponse",
    "get_mileage_warning",
    "parse_target_distance",
]
