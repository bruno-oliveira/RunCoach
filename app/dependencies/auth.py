"""Auth dependencies: user resolution + ownership validation."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.dependencies.database import get_db
from app.dependencies.services import get_auth_service
from app.infrastructure.config import settings
from app.models import TrainingPlan, User

COOKIE_NAME = "access_token"
ANONYMOUS_USER_COOKIE = "anonymous_user_id"

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

    # Special-purpose tokens (e.g. the short-lived OAuth ``state``) are
    # signed with the same key but must never be accepted as a session
    # credential. Session tokens carry no ``purpose`` claim.
    if payload.get("purpose") is not None:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    user = auth_service.get_current_user(db, user_id)
    if user is None:
        return None

    if user.last_activity:
        timeout_delta = timedelta(minutes=settings.session_timeout_minutes)
        last_activity = user.last_activity
        if last_activity.tzinfo is not None:
            last_activity = last_activity.replace(tzinfo=None)
        if (
            datetime.now(timezone.utc).replace(tzinfo=None) - last_activity
        ) > timeout_delta:
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


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the authenticated user to be the configured admin operator.

    Gated by ``settings.admin_email`` (case-insensitive). Returns 403 for any
    other user, and for everyone when no admin email is configured.
    """
    admin_email = (settings.admin_email or "").strip().lower()
    user_email = (current_user.email or "").strip().lower()
    if not admin_email or user_email != admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def verify_plan_ownership(
    plan: TrainingPlan,
    current_user: Optional[User],
    anonymous_user_id: Optional[str],
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
    plan_repo: Optional[SQLAlchemyPlanRepository] = None,
) -> TrainingPlan:
    """Validate that the authenticated user owns the given plan. 403 if not.

    Accepts an optional injected repository so FastAPI endpoints can supply
    a request-scoped repo via ``Depends(get_plan_repository)``.
    """
    repo = plan_repo or SQLAlchemyPlanRepository(db)
    plan = repo.get_for_user(plan_id, current_user.id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Training plan not found or access denied",
        )
    return plan


__all__ = [
    "COOKIE_NAME",
    "ANONYMOUS_USER_COOKIE",
    "get_current_user",
    "get_optional_user",
    "get_admin_user",
    "verify_plan_ownership",
    "validate_plan_ownership",
]
