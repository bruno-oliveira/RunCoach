"""VDOT recalibration — update pace zones when fitness changes."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import to_date as _to_date

from ._helpers import parse_plan_data_lookups, today_date

logger = logging.getLogger(__name__)

_VDOT_RECALIBRATION_THRESHOLD = 1.0


def check_vdot_recalibration(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    from app.services.race_predictor_service import RacePredictorService

    plan_vdot = training_plan.vdot
    if not plan_vdot:
        return None

    current_vdot = RacePredictorService.get_best_recent_vdot(
        user_id, weeks=12, db=db,
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
    days_elapsed = (today - start_date).days
    current_week = max(1, days_elapsed // 7 + 1)

    pace_updates = 0
    for (week_num, day_num), workout in pd_workout.items():
        if week_num < current_week:
            continue

        if workout.get("target_pace") and old_zones:
            zone = workout.get("zone", "")
            zone_map = {
                "zone_1": "E", "zone_2": "E", "zone_3": "T",
                "zone_4": "I", "zone_5": "I",
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
                "zone_1": "E", "zone_2": "E", "zone_3": "T",
                "zone_4": "I", "zone_5": "I",
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
    db.flush()

    direction = "improved" if delta > 0 else "decreased"
    logger.info(
        "VDOT recalibration: plan=%s old=%.1f new=%.1f delta=%.1f pace_updates=%d",
        training_plan.id, old_vdot, current_vdot, delta, pace_updates,
    )

    return {
        "recalibrated": True,
        "old_vdot": round(old_vdot, 1),
        "new_vdot": round(current_vdot, 1),
        "delta": round(delta, 1),
        "direction": direction,
        "pace_updates": pace_updates,
    }
