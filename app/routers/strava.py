"""Strava OAuth and sync endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth_service import AuthService
from app.config import settings
from app.dependencies import get_current_user, get_db, get_auth_service, get_strava_service
from app.models.user import User
from app.schemas import StravaStatusResponse, StravaSyncResponse
from app.services.strava_service import StravaService

logger = logging.getLogger(__name__)

strava_router = APIRouter(prefix="/api/strava", tags=["strava"])


@strava_router.get("/connect")
async def strava_connect(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Return Strava OAuth authorization URL."""
    # Encode user_id into a signed JWT state parameter for CSRF protection
    state = auth_service.create_access_token(
        {"sub": current_user.id, "purpose": "strava_oauth"}
    )
    authorize_url = strava_service.get_authorization_url(state)
    return {"authorize_url": authorize_url}


@strava_router.get("/callback")
async def strava_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Handle Strava OAuth callback: exchange code, store tokens, trigger initial sync."""
    # Verify state JWT to get user_id
    payload = auth_service.verify_token(state)
    if not payload or payload.get("purpose") != "strava_oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Exchange code for tokens
    try:
        token_data = await strava_service.exchange_code_for_tokens(code)
    except Exception as e:
        logger.error(f"Strava token exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange code with Strava",
        )

    # Store tokens on user
    athlete = token_data.get("athlete", {})
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]
    db.commit()

    # Trigger initial full sync (all historical activities)
    try:
        result = await strava_service.sync_activities(user, db, days_back=None)
        logger.info(
            f"Initial Strava sync for user {user.id}: "
            f"{result['synced']} synced, {result['skipped']} skipped"
        )
    except Exception as e:
        logger.error(f"Initial Strava sync failed: {e}")

    # Redirect back to the app
    return RedirectResponse(url="/my-plans", status_code=status.HTTP_302_FOUND)


@strava_router.post("/sync", response_model=StravaSyncResponse)
async def strava_sync(
    days_back: Optional[int] = Query(default=None, ge=1, le=3650),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Manually trigger Strava activity sync.

    If days_back is not provided, syncs all historical activities.
    If days_back is provided, only syncs activities from the last N days (max 3650 = ~10 years).
    """
    if not current_user.strava_athlete_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava account not connected. Connect via /api/strava/connect first.",
        )

    try:
        result = await strava_service.sync_activities(
            current_user, db, days_back=days_back
        )
    except Exception as e:
        logger.error(f"Strava sync failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava sync failed: {str(e)}",
        )

    return StravaSyncResponse(**result)


@strava_router.get("/status", response_model=StravaStatusResponse)
async def strava_status(
    current_user: User = Depends(get_current_user),
):
    """Return Strava connection status for the current user."""
    connected = bool(current_user.strava_athlete_id)
    return StravaStatusResponse(
        connected=connected,
        athlete_id=current_user.strava_athlete_id if connected else None,
    )


@strava_router.post("/disconnect")
async def strava_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Disconnect Strava account. Keeps previously synced RunLogs."""
    strava_service.disconnect(current_user, db)
    return {"detail": "Strava account disconnected"}
