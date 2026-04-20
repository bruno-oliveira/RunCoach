"""Strava OAuth page endpoints.

Page/redirect endpoints have been moved here.
API endpoints remain in strava.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.config import settings
from app.dependencies import get_current_user, get_db, get_auth_service, get_strava_service, get_adaptation_service
from app.models import TrainingPlan
from app.models.user import User
from app.schemas import StravaSyncResponse
from app.services.strava_service import StravaService
from app.services.adaptation_service import AdaptationService
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strava-pages"])

# How far back to look on the very first sync (before any cursor exists).
# A full year ensures we cover any active training plan the user might have.
INITIAL_SYNC_DAYS = 365


def _auto_map_and_adjust(
    user: User,
    db: Session,
    adaptation_service: AdaptationService,
) -> list[dict]:
    """Find active plans and auto-map runs + auto-adjust each one.

    Returns a list of per-plan result dicts suitable for the sync response.
    """
    from app.utils import to_date as _to_date

    today = datetime.now(timezone.utc).date()

    active_plans = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == user.id,
            TrainingPlan.start_date.isnot(None),
        )
        .all()
    )

    results: list[dict] = []
    for plan in active_plans:
        start = _to_date(plan.start_date)
        if start is None:
            continue
        end_date = start + timedelta(weeks=plan.weeks_duration)
        if today > end_date:
            continue  # plan is completed

        try:
            map_result = adaptation_service.map_runs_to_plan(
                plan.id, user.id, db
            )
            adjust_result = adaptation_service.adjust_plan(
                plan.id, user.id, db
            )
            # Check for proactive adaptation alerts
            alert = adaptation_service.check_alerts(plan.id, user.id, db)
            results.append({
                "plan_id": plan.id,
                "runs_mapped": map_result.get("mapped", 0),
                "adjusted": adjust_result.get("adjusted", False),
                "multiplier": adjust_result.get("multiplier"),
                "reason": adjust_result.get("reason", ""),
                "alert": alert,
            })
        except Exception as e:
            logger.warning(f"Auto-adjust failed for plan {plan.id}: {e}")

    return results


@router.get("/api/strava/callback")
async def strava_callback(
    code: str = Query(...),
    state: str = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Handle Strava OAuth callback: exchange code, store tokens, trigger initial sync."""
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

    try:
        token_data = await strava_service.exchange_code_for_tokens(code)
    except Exception as e:
        logger.error(f"Strava token exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange code with Strava",
        )

    athlete = token_data.get("athlete", {})
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]
    db.commit()

    # Initial sync in background to avoid blocking the HTTP response
    async def _initial_sync(user_id: str):
        from app.dependencies import SessionLocal, get_adaptation_service
        sync_db = SessionLocal()
        try:
            sync_user = sync_db.query(User).filter(User.id == user_id).first()
            if not sync_user:
                return
            initial_after = TimestampAdapter.days_ago_utc_epoch(INITIAL_SYNC_DAYS)
            result = await strava_service.sync_activities(sync_user, sync_db, after_timestamp=initial_after)
            logger.info(
                f"Initial Strava sync for user {user_id}: "
                f"{result['synced']} synced, {result['total']} total"
            )
            if result.get("synced", 0) > 0:
                adaptation_service = AdaptationService()
                adjustment_results = _auto_map_and_adjust(sync_user, sync_db, adaptation_service)
                if adjustment_results:
                    logger.info(
                        f"Auto-adjusted {len(adjustment_results)} plan(s) for user {user_id}"
                    )
        except Exception as e:
            logger.error(f"Initial Strava sync failed: {e}")
        finally:
            sync_db.close()

    background_tasks.add_task(_initial_sync, user.id)

    return RedirectResponse(url="/my-plans", status_code=status.HTTP_302_FOUND)
