"""Post-sync orchestration: auto-map runs to plans and trigger adjustments."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.models import TrainingPlan
from app.models.user import User
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
            map_result = adaptation_service.map_runs_to_plan(plan.id, user.id, db)

            vdot_recalibration = None
            try:
                from app.contexts.plan.adaptation.vdot_recalibrator import (
                    recalibrate_zones_only,
                )

                vdot_recalibration = recalibrate_zones_only(plan, user.id, db)
            except Exception as e:
                logger.warning(
                    f"VDOT recalibration after sync failed for plan {plan.id}: {e}"
                )

            results.append(
                {
                    "plan_id": plan.id,
                    "runs_mapped": map_result.get("mapped", 0),
                    "vdot_recalibration": vdot_recalibration,
                }
            )
        except Exception as e:
            logger.warning(f"Auto-adjust failed for plan {plan.id}: {e}")

    return results
