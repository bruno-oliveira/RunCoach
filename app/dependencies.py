"""FastAPI dependencies: DB session, services, auth.

Engine + session factory live in ``app.infrastructure.database``.
Stateless services are cached via ``@lru_cache`` so each request reuses
a single instance; services that hold a per-request DB session take it
through ``Depends(get_db)``.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.performance_plan_generator import PerformancePlanGenerator
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import PlanService
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.runner.fitness.performance_service import PerformanceService
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal, engine, get_db
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.integrations.strava_service import StravaService
from app.models import TrainingPlan, User

COOKIE_NAME = "access_token"
ANONYMOUS_USER_COOKIE = "anonymous_user_id"


# ---- Stateless service factories (one instance per process) ----

@lru_cache
def get_plan_generator() -> TrainingPlanGenerator:
    return TrainingPlanGenerator()


@lru_cache
def get_pdf_generator() -> PDFGenerator:
    return PDFGenerator()


@lru_cache
def get_performance_plan_generator() -> PerformancePlanGenerator:
    return PerformancePlanGenerator()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


@lru_cache
def get_plan_service() -> PlanService:
    return PlanService()


@lru_cache
def get_strava_service() -> StravaService:
    return StravaService()


@lru_cache
def get_adaptation_service() -> AdaptationService:
    return AdaptationService()


# ---- Factories that take per-request arguments ----

def get_nutrition_engine(random_seed: int | None = None) -> NutritionEngine:
    """NutritionEngine is reseedable per-request; do not cache."""
    return NutritionEngine(random_seed=random_seed)


def get_performance_service(db: Session = Depends(get_db)) -> PerformanceService:
    """PerformanceService holds a DB session, so it must be per-request."""
    return PerformanceService(db)


def get_plan_repository(db: Session = Depends(get_db)) -> SQLAlchemyPlanRepository:
    """Per-request plan repository bound to the current DB session."""
    return SQLAlchemyPlanRepository(db)


def get_run_repository(db: Session = Depends(get_db)) -> SQLAlchemyRunRepository:
    """Per-request run repository bound to the current DB session."""
    return SQLAlchemyRunRepository(db)


def get_user_repository(db: Session = Depends(get_db)) -> SQLAlchemyUserRepository:
    """Per-request user repository bound to the current DB session."""
    return SQLAlchemyUserRepository(db)


# ---- Auth ----

security = HTTPBearer(auto_error=False)


async def _resolve_user(
    request: Request,
    db: Session,
    auth_service: AuthService,
) -> Optional[User]:
    """Token extraction → user lookup, shared by both auth dependencies."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if not token:
        token = request.cookies.get(COOKIE_NAME)

    if not token:
        return None

    payload = auth_service.verify_token(token)
    if payload is None:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    user = auth_service.get_current_user(db, user_id)
    if user is None:
        return None

    # All datetimes in this app are stored as naive UTC (tzinfo=None).
    # Strip tzinfo defensively in case a future code path stores tz-aware.
    if user.last_activity:
        timeout_delta = timedelta(minutes=settings.session_timeout_minutes)
        last_activity = user.last_activity
        if last_activity.tzinfo is not None:
            last_activity = last_activity.replace(tzinfo=None)
        if (datetime.now(timezone.utc).replace(tzinfo=None) - last_activity) > timeout_delta:
            return None

    auth_service.update_user_activity(db, user)
    return user


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Get the current authenticated user; 401 if no valid session."""
    user = await _resolve_user(request, db, auth_service)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[User]:
    """Get the current authenticated user, or None if not authenticated."""
    return await _resolve_user(request, db, auth_service)


# ---- Ownership helpers ----

def verify_plan_ownership(
    plan: TrainingPlan, current_user: Optional[User], anonymous_user_id: Optional[str]
) -> bool:
    """Check if the current user or anonymous session owns the plan."""
    if current_user is not None:
        return plan.user_id == current_user.id
    if anonymous_user_id is not None:
        return plan.user_id == anonymous_user_id
    return False


def validate_plan_ownership(
    plan_id: str,
    db: Session,
    current_user: User,
) -> TrainingPlan:
    """Validate that the authenticated user owns the given plan. 403 if not."""
    plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, current_user.id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Training plan not found or access denied",
        )
    return plan


__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "get_plan_generator",
    "get_pdf_generator",
    "get_performance_plan_generator",
    "get_auth_service",
    "get_plan_service",
    "get_strava_service",
    "get_adaptation_service",
    "get_nutrition_engine",
    "get_performance_service",
    "get_plan_repository",
    "get_run_repository",
    "get_user_repository",
    "get_current_user",
    "get_optional_user",
    "verify_plan_ownership",
    "validate_plan_ownership",
    "COOKIE_NAME",
    "ANONYMOUS_USER_COOKIE",
]
