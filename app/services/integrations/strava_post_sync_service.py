"""Post-sync orchestration: auto-map runs to plans and trigger adjustments."""

import logging
from datetime import timedelta, timezone, datetime

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.models.user import User
from app.services.adaptation import AdaptationService
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)


def auto_map_and_adjust(
    user: User,
    db: Session,
    adaptation_service: AdaptationService,
) -> list[dict]:
    """Find active plans and auto-map runs + auto-adjust each one.

    Returns a list of per-plan result dicts suitable for the sync response.
    """
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
            continue

        try:
            map_result = adaptation_service.map_runs_to_plan(
                plan.id, user.id, db
            )
            recommendation = adaptation_service.evaluate_recommendation(
                plan.id, user.id, db
            )
            alert = adaptation_service.check_alerts(plan.id, user.id, db)
            results.append({
                "plan_id": plan.id,
                "runs_mapped": map_result.get("mapped", 0),
                "has_recommendation": recommendation is not None,
                "alert": alert,
            })
        except Exception as e:
            logger.warning(f"Auto-adjust failed for plan {plan.id}: {e}")

    return results


async def initial_sync(
    user_id: str,
    strava_service,
) -> None:
    """Run the initial Strava sync in a background task with its own DB session."""
    from app.config import settings
    from app.dependencies import SessionLocal
    from app.utils import TimestampAdapter

    sync_db = SessionLocal()
    try:
        sync_user = sync_db.query(User).filter(User.id == user_id).first()
        if not sync_user:
            return
        initial_after = TimestampAdapter.days_ago_utc_epoch(settings.strava_initial_sync_days)
        result = await strava_service.sync_activities(sync_user, sync_db, after_timestamp=initial_after)
        logger.info(
            f"Initial Strava sync for user {user_id}: "
            f"{result['synced']} synced, {result['total']} total"
        )
        if result.get("synced", 0) > 0:
            adaptation_service = AdaptationService()
            adjustment_results = auto_map_and_adjust(sync_user, sync_db, adaptation_service)
            if adjustment_results:
                logger.info(
                    f"Auto-adjusted {len(adjustment_results)} plan(s) for user {user_id}"
                )
    except Exception as e:
        logger.error(f"Initial Strava sync failed: {e}")
    finally:
        sync_db.close()
