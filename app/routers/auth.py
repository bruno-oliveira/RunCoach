"""Authentication router with Google OAuth support."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth_service import AuthService
from app.config import settings
from app.dependencies import get_auth_service, get_db, get_current_user
from app.models import User
from app.schemas import GoogleAuthRequest, Token, UserResponse

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Cookie settings
COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 24 * 60 * 60  # 1 day in seconds


@auth_router.post("/google", response_model=Token)
async def google_auth(
    auth_request: GoogleAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user using Google OAuth ID token.
    Merges anonymous user data if anonymous_user_id cookie is present.
    """
    logger.info(f"Attempting Google OAuth authentication...")

    google_user_data = await auth_service.verify_google_token(auth_request.id_token)

    if not google_user_data:
        logger.error(f"Google token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"Google authentication successful for: {google_user_data.get('email')}")

    anonymous_user_id = request.cookies.get("anonymous_user_id")
    logger.info(f"Anonymous user ID from cookie: {anonymous_user_id}")

    user = auth_service.get_or_create_user(db, google_user_data, anonymous_user_id)

    logger.info(f"User created/retrieved: {user.id}, Name: {user.name}")

    access_token = auth_service.create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(days=1),
    )

    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
    )

    response.delete_cookie(key="anonymous_user_id", samesite="lax")

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            google_id=user.google_id,
            email=user.email,
            name=user.name,
            picture=user.picture,
            created_at=user.created_at,
            plans_generated=user.plans_generated,
        ),
    )


@auth_router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's information.

    Requires a valid JWT token in Authorization header.
    """
    return UserResponse(
        id=current_user.id,
        google_id=current_user.google_id,
        email=current_user.email,
        name=current_user.name,
        picture=current_user.picture,
        created_at=current_user.created_at,
        plans_generated=current_user.plans_generated,
    )


@auth_router.post("/logout")
async def logout(response: Response):
    """
    Logout endpoint.
    Clears both authentication and anonymous tracking cookies.
    """
    response.delete_cookie(key=COOKIE_NAME, samesite="lax")
    response.delete_cookie(key="anonymous_user_id", samesite="lax")
    return {"message": "Successfully logged out"}
