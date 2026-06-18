"""Backward-compatibility shim — schemas split into focused modules.

Prefer importing from the specific modules:
- ``app.schemas.plan_request``        — PlanRequest, PlanRequestBase, RaceInfoMixin
- ``app.schemas.performance_request`` — PerformancePlanRequest
- ``app.schemas.plan_config``         — helpers (compute_vdot_from_time, get_mileage_warning, parse_target_distance)
"""

from app.schemas.performance_request import PerformancePlanRequest
from app.schemas.plan_config import (
    _MILEAGE_CONFIG,
    compute_vdot_from_time,
    get_mileage_warning,
    parse_target_distance,
)
from app.schemas.plan_request import PlanRequest, PlanRequestBase, RaceInfoMixin

__all__ = [
    "PerformancePlanRequest",
    "PlanRequest",
    "PlanRequestBase",
    "RaceInfoMixin",
    "_MILEAGE_CONFIG",
    "compute_vdot_from_time",
    "get_mileage_warning",
    "parse_target_distance",
]
