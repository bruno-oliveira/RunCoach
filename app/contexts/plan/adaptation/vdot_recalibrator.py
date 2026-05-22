"""VDOT recalibration — update pace zones when fitness changes."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.plan_date_utils import compute_current_week
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import TrainingPlan
from app.utils import to_date as _to_date

from ._helpers import parse_plan_data_lookups, today_date

logger = logging.getLogger(__name__)

_VDOT_RECALIBRATION_THRESHOLD = 1.0


def recalibrate_zones_only(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Rewrite future workout pace zones when the user's VDOT has shifted.

    Public helper callable from per-run hooks (run logging, Strava sync) and
    from the full plan-adjust flow. Returns the recalibration result dict if
    pace zones were updated, or None if nothing changed.
    """
    from app.contexts.runner.fitness.race_predictor_service import RacePredictorService

    plan_vdot = training_plan.vdot
    if not plan_vdot:
        return None

    current_vdot = RacePredictorService.get_best_recent_vdot(
        user_id,
        weeks=12,
        db=db,
    )
    if not current_vdot:
        return None

    delta = current_vdot - plan_vdot
    if abs(delta) < _VDOT_RECALIBRATION_THRESHOLD:
        return None

    new_zones = VDOTCalculator.get_pace_zones(current_vdot)
    if not new_zones:
        return None

    old_zones = VDOTCalculator.get_pace_zones(plan_vdot)

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    current_week = compute_current_week(start_date, today, clamp_min=1, pre_start=1)

    pace_updates = 0
    for (week_num, day_num), workout in pd_workout.items():
        if week_num < current_week:
            continue

        if workout.get("target_pace") and old_zones:
            zone = workout.get("zone", "")
            zone_map = {
                "zone_1": "E",
                "zone_2": "E",
                "zone_3": "T",
                "zone_4": "I",
                "zone_5": "I",
            }
            vdot_key = zone_map.get(zone)
            if vdot_key and vdot_key in new_zones:
                new_pace = new_zones[vdot_key].get("pace_min_km")
                if new_pace:
                    from app.utils import format_pace

                    workout["target_pace"] = new_pace
                    workout["target_pace_formatted"] = format_pace(new_pace)
                    pace_updates += 1

        for seg in workout.get("segments", []):
            zone = seg.get("zone", "")
            zone_map = {
                "zone_1": "E",
                "zone_2": "E",
                "zone_3": "T",
                "zone_4": "I",
                "zone_5": "I",
            }
            vdot_key = zone_map.get(zone)
            if vdot_key and vdot_key in new_zones:
                new_pace = new_zones[vdot_key].get("pace_min_km")
                if new_pace:
                    from app.utils import format_pace

                    seg["pace_raw"] = new_pace
                    seg["pace_formatted"] = format_pace(new_pace)

    if pace_updates == 0:
        return None

    training_plan.plan_data = plan_data
    old_vdot = training_plan.vdot
    training_plan.vdot = round(current_vdot, 1)

    weekly_updates = _sync_future_weekly_plans(
        training_plan, current_week, new_zones, db
    )

    db.flush()

    direction = "improved" if delta > 0 else "decreased"
    logger.info(
        "VDOT recalibration: plan=%s old=%.1f new=%.1f delta=%.1f pace_updates=%d weekly_updates=%d",
        training_plan.id,
        old_vdot,
        current_vdot,
        delta,
        pace_updates,
        weekly_updates,
    )

    return {
        "recalibrated": True,
        "old_vdot": round(old_vdot, 1),
        "new_vdot": round(current_vdot, 1),
        "delta": round(delta, 1),
        "direction": direction,
        "pace_updates": pace_updates,
        "weekly_plans_updated": weekly_updates,
    }


def check_vdot_recalibration(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Backwards-compatible alias for :func:`recalibrate_zones_only`."""
    return recalibrate_zones_only(training_plan, user_id, db)


def _sync_future_weekly_plans(
    training_plan: TrainingPlan,
    current_week: int,
    new_zones: Dict[str, Any],
    db: Session,
) -> int:
    """Stamp WeeklyPlan.pace_zones_updated_at on future weeks so the UI can badge them."""
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from app.models import WeeklyPlan

    weekly_plans = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == training_plan.id,
            WeeklyPlan.week_number >= current_week,
        )
        .all()
    )

    if not weekly_plans:
        return 0

    now = _dt.now(_tz.utc).replace(tzinfo=None)
    for wp in weekly_plans:
        wp.pace_zones_updated_at = now

    return len(weekly_plans)
