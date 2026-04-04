"""FastAPI dependencies for dependency injection."""

from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.services.auth_service import AuthService
from app.config import settings
from app.models import TrainingPlan, User
from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.export.pdf_generator import PDFGenerator
from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.generators.performance_plan_generator import PerformancePlanGenerator
from app.services.plan_service import PlanService
from app.services.strava_service import StravaService

# Cookie name must match the one in auth router
COOKIE_NAME = "access_token"
ANONYMOUS_USER_COOKIE = "anonymous_user_id"

# Database setup
_is_sqlite = "sqlite" in settings.database_url

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=NullPool if _is_sqlite else None,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")    # readers don't block writers
        cursor.execute("PRAGMA synchronous=NORMAL")  # safe + faster than FULL (default)
        cursor.execute("PRAGMA foreign_keys=ON")     # enforce FK constraints
        cursor.execute("PRAGMA busy_timeout=5000")   # wait up to 5s on a locked DB
        cursor.execute("PRAGMA cache_size=-32000")   # 32MB page cache
        cursor.execute("PRAGMA temp_store=MEMORY")   # temp tables in RAM
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.

    Yields a database session that is automatically closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_plan_generator() -> TrainingPlanGenerator:
    """Get a TrainingPlanGenerator instance."""
    return TrainingPlanGenerator()


def get_nutrition_engine(random_seed: int | None = None) -> NutritionEngine:
    """Get a NutritionEngine instance with optional random seed."""
    return NutritionEngine(random_seed=random_seed)


def get_pdf_generator() -> PDFGenerator:
    """Get a PDFGenerator instance."""
    return PDFGenerator()


def get_performance_plan_generator() -> PerformancePlanGenerator:
    """Get a PerformancePlanGenerator instance."""
    return PerformancePlanGenerator()


def get_auth_service() -> AuthService:
    """Get an AuthService instance."""
    return AuthService()


def get_plan_service() -> PlanService:
    """Get a PlanService instance."""
    return PlanService()


def get_strava_service() -> StravaService:
    """Get a StravaService instance."""
    return StravaService()


security = HTTPBearer(auto_error=False)


async def _resolve_user(
    request: Request,
    db: Session,
    auth_service: AuthService,
) -> Optional[User]:
    """Shared token-extraction → user-lookup logic used by both auth dependencies."""
    # Extract token from Authorization header or cookie
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

    # Inactivity timeout check
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
    """Get the current authenticated user from JWT token.

    Raises 401 when no valid session is found.
    """
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
    """Get the current authenticated user if a valid token is provided.

    Returns None if no token or invalid token (for optional authentication).
    """
    return await _resolve_user(request, db, auth_service)


def verify_plan_ownership(
    plan: TrainingPlan, current_user: Optional[User], anonymous_user_id: Optional[str]
) -> bool:
    """Check if the current user or anonymous session owns the plan."""
    if current_user is not None:
        return plan.user_id == current_user.id
    if anonymous_user_id is not None:
        return plan.user_id == anonymous_user_id
    return False
