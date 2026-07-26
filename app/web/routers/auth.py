"""Authentication router with Google OAuth support."""

import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.dependencies import (
    get_auth_service,
    get_current_user,
    get_db,
    get_strava_service,
)
from app.infrastructure.config import settings
from app.infrastructure.integrations.strava_service import StravaService
from app.models import User
from app.rate_limit import account_deletion_limiter, auth_limiter
from app.schemas import AuthResponse, GoogleAuthRequest, UserResponse
from app.schemas.auth_schemas import UserSettingsUpdate
from app.web.middleware import _cookie_secure

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Cookie settings
COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = 24 * 60 * 60  # 1 day in seconds


def _user_response(user: User) -> UserResponse:
    """Build the API view of a user. Single source of truth so every auth
    endpoint returns the same shape (and the same fields)."""
    return UserResponse(
        id=user.id,
        google_id=user.google_id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        created_at=user.created_at,
        plans_generated=user.plans_generated,
        strava_connected=bool(user.strava_athlete_id),
        intervals_connected=bool(user.intervals_athlete_id),
        age=user.age,
        max_hr=user.max_hr,
        resting_hr=user.resting_hr,
        threshold_hr=user.threshold_hr,
        nudge_email_enabled=bool(user.nudge_email_enabled),
    )


def _set_session_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    """Set the access-token cookie, and optionally a refresh-token cookie."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )
    if refresh_token is not None:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=settings.refresh_token_days * 24 * 60 * 60,
            httponly=True,
            samesite="lax",
            secure=_cookie_secure(),
            path="/api/auth",
        )


@auth_router.post("/google", response_model=AuthResponse)
async def google_auth(
    auth_request: GoogleAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Authenticate user using Google OAuth ID token.

    Sets an httponly cookie with the JWT. The token is NOT returned in the
    response body to prevent XSS exfiltration.
    """
    auth_limiter.check(request)
    logger.info("Attempting Google OAuth authentication")

    google_user_data = await auth_service.verify_google_token(auth_request.id_token)

    if not google_user_data:
        logger.error("Google token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    anonymous_user_id = request.cookies.get("anonymous_user_id")

    user = auth_service.get_or_create_user(db, google_user_data, anonymous_user_id)

    logger.info("User authenticated: %s", user.id)

    access_token = auth_service.create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(minutes=settings.access_token_minutes),
    )
    refresh_token, _ = auth_service.issue_refresh_token(db, user)

    _set_session_cookies(response, access_token, refresh_token)
    response.delete_cookie(key="anonymous_user_id", samesite="lax")

    return AuthResponse(user=_user_response(user))


@auth_router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's information.

    Requires a valid JWT token in Authorization header.
    """
    return _user_response(current_user)


@auth_router.patch("/me/settings", response_model=UserResponse)
def update_user_settings(
    payload: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update mutable user settings (age, HR anchors, coaching-email consent)."""
    if payload.age is not None:
        # 0 clears the override.
        current_user.age = payload.age or None
    if payload.max_hr is not None:
        # 0 clears the override and reverts to detection / the age formula.
        current_user.max_hr = payload.max_hr or None
    if payload.resting_hr is not None:
        # 0 clears the override.
        current_user.resting_hr = payload.resting_hr or None
    if payload.threshold_hr is not None:
        # 0 clears the override and reverts to the data-derived estimate.
        current_user.threshold_hr = payload.threshold_hr or None
    if payload.nudge_email_enabled is not None:
        # A boolean, so false is a choice rather than "unset" — assigned
        # directly instead of going through the ``or None`` clearing idiom.
        current_user.nudge_email_enabled = payload.nudge_email_enabled
    db.commit()
    db.refresh(current_user)
    return _user_response(current_user)


@auth_router.post("/refresh", response_model=UserResponse)
def refresh_session(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Exchange a refresh token for a new access token (and rotate the refresh token)."""
    auth_limiter.check(request)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    user = auth_service.consume_refresh_token(db, refresh_token)
    if user is None:
        # Treat any failure (unknown / expired / revoked) uniformly to avoid
        # leaking whether the token previously existed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    access_token = auth_service.create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(minutes=settings.access_token_minutes),
    )
    new_refresh, _ = auth_service.issue_refresh_token(db, user)
    _set_session_cookies(response, access_token, new_refresh)

    return _user_response(user)


@auth_router.post("/logout")
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Logout endpoint.
    Clears both authentication and anonymous tracking cookies, and revokes
    the refresh token server-side if one was presented.
    """
    if refresh_token:
        auth_service.revoke_refresh_token(db, refresh_token)
    response.delete_cookie(key=COOKIE_NAME, samesite="lax")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, samesite="lax", path="/api/auth")
    response.delete_cookie(key="anonymous_user_id", samesite="lax")
    return {"message": "Successfully logged out"}


@auth_router.delete("/account")
async def delete_account(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Delete the current user's account and all associated data."""
    account_deletion_limiter.check(request)
    logger.info("Account deletion requested for user %s", current_user.id)
    if current_user.strava_access_token:
        # Best-effort revoke: never block account deletion on Strava reachability,
        # but escalate failures to ERROR so an operator can manually deauthorize
        # the dangling token.
        revoke_ok = False
        try:
            token = await strava_service.ensure_valid_token(current_user, db)
            revoke_ok = await strava_service.revoke_token(token)
        except Exception:
            logger.error(
                "Strava token refresh raised during account deletion "
                "(user_id=%s, strava_athlete_id=%s) — manual deauthorize required",
                current_user.id,
                current_user.strava_athlete_id,
                exc_info=True,
            )
        if not revoke_ok:
            logger.error(
                "Strava token revocation failed during account deletion "
                "(user_id=%s, strava_athlete_id=%s) — manual deauthorize required",
                current_user.id,
                current_user.strava_athlete_id,
            )
    db.delete(current_user)
    db.commit()
    response.delete_cookie(key=COOKIE_NAME, samesite="lax")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, samesite="lax", path="/api/auth")
    response.delete_cookie(key="anonymous_user_id", samesite="lax")
    return {"message": "Account deleted"}
