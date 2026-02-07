"""FastAPI dependencies for dependency injection."""

from typing import Generator, Optional

from fastapi import Cookie, Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth_service import AuthService
from app.config import settings
from app.models import User
from app.core.nutrition_engine import NutritionEngine
from app.core.pdf_generator import PDFGenerator
from app.core.plan_generator import TrainingPlanGenerator

# Cookie name must match the one in auth router
COOKIE_NAME = "access_token"
ANONYMOUS_USER_COOKIE = "anonymous_user_id"

# Database setup
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
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


def get_auth_service() -> AuthService:
    """Get an AuthService instance."""
    return AuthService()


security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Get the current authenticated user from JWT token.
    Updates last_activity timestamp and checks for inactivity timeout.
    """
    token = None

    # First, try Authorization header
    if credentials:
        token = credentials.credentials

    # Fall back to cookie
    if not token:
        token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = auth_service.verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_service.get_current_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.last_activity:
        from datetime import timedelta
        from app.config import settings
        timeout_delta = timedelta(minutes=settings.session_timeout_minutes)
        if (datetime.utcnow() - user.last_activity) > timeout_delta:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity",
                headers={"WWW-Authenticate": "Bearer"},
            )

    auth_service.update_user_activity(db, user)

    return user


async def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[User]:
    """
    Get the current authenticated user if a valid token is provided.
    Returns None if no token or invalid token (for optional authentication).

    Checks for token in:
    1. Authorization header (Bearer token)
    2. HTTP cookie (for browser navigation)
    """
    token = None

    # First, try Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    # Fall back to cookie
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

    return auth_service.get_current_user(db, user_id)


# Type aliases for dependency injection
DatabaseSession = Session
PlanGenerator = TrainingPlanGenerator
NutritionGenerator = NutritionEngine
PdfGenerator = PDFGenerator
AuthService = AuthService
