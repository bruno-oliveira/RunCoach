"""VDOT recalibration — update pace zones when fitness changes."""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.training.plan_calendar import compute_current_week
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog, TrainingPlan
from app.utils import to_date as _to_date

from ._helpers import parse_plan_data_lookups, today_date

logger = logging.getLogger(__name__)

_VDOT_RECALIBRATION_THRESHOLD = 1.0

# Session-hit-rate recalibration (audit E5) — Runna-style "Pace Insights".
# Pace deviation thresholds mirror the coaching pattern analyzer so the two
# surfaces agree: consistently faster than target ⇒ fitter than the plan
# VDOT, consistently slower ⇒ the target is too hot (or the runner is
# fatigued). Warmup/cooldown dilution biases the average slow, so the
# "slower" band is wider and its VDOT sensitivity gentler.
_PACE_HIT_MIN_SAMPLE = 4
_PACE_HIT_LOOKBACK_WEEKS = 6
_PACE_HIT_FAST_DEV = -0.05
_PACE_HIT_SLOW_DEV = 0.08
_PACE_HIT_FAST_SENSITIVITY = 20.0
_PACE_HIT_SLOW_SENSITIVITY = 12.0
_PACE_HIT_MAX_DELTA = 2.0
_PACE_HIT_QUALITY_TYPES = ("tempo", "interval", "threshold")


def _pace_hit_implied_vdot(
    plan_id: str,
    user_id: str,
    db: Session,
    plan_vdot: float,
) -> Optional[float]:
    """VDOT implied by how the runner hits prescribed quality-session paces.

    Beyond the after-races-only signal, this reads completed tempo/interval
    sessions and compares actual to planned pace. A consistent, multi-session
    deviation nudges VDOT — letting the plan recalibrate from training even
    when the runner hasn't raced (audit E5). Returns None when the sample is
    thin or the deviation sits inside the neutral band.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(weeks=_PACE_HIT_LOOKBACK_WEEKS)
    ).replace(tzinfo=None)

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.user_id == user_id,
            RunLog.planned_pace_min_km.isnot(None),
            RunLog.avg_pace_min_km.isnot(None),
            RunLog.date >= cutoff,
        )
        .all()
    )

    deviations = [
        (r.avg_pace_min_km - r.planned_pace_min_km) / r.planned_pace_min_km
        for r in runs
        if r.effective_workout_type in _PACE_HIT_QUALITY_TYPES
        and r.planned_pace_min_km
        and r.avg_pace_min_km
    ]

    if len(deviations) < _PACE_HIT_MIN_SAMPLE:
        return None

    median_dev = statistics.median(deviations)

    if median_dev <= _PACE_HIT_FAST_DEV:
        delta = min(_PACE_HIT_MAX_DELTA, -median_dev * _PACE_HIT_FAST_SENSITIVITY)
        return round(plan_vdot + delta, 1)
    if median_dev >= _PACE_HIT_SLOW_DEV:
        delta = min(_PACE_HIT_MAX_DELTA, median_dev * _PACE_HIT_SLOW_SENSITIVITY)
        return round(plan_vdot - delta, 1)
    return None


def recalibrate_zones_only(
    training_plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Rewrite future workout pace zones when the user's VDOT has shifted.

    Public helper callable from per-run hooks (run logging, activity sync) and
    from the full plan-adjust flow. Returns the recalibration result dict if
    pace zones were updated, or None if nothing changed.
    """
    from app.application.ports import RacePredictorService

    plan_vdot = training_plan.vdot
    if not plan_vdot:
        return None

    # Primary signal: best recent race-like efforts.
    recent_vdot = RacePredictorService.get_best_recent_vdot(
        user_id,
        weeks=12,
        db=db,
    )

    target_vdot: Optional[float] = None
    source = "recent_efforts"
    if recent_vdot and abs(recent_vdot - plan_vdot) >= _VDOT_RECALIBRATION_THRESHOLD:
        target_vdot = recent_vdot

    # Fallback: recalibrate from how the runner hits prescribed quality paces
    # when there's no race-effort move to act on (audit E5).
    if target_vdot is None:
        pace_implied = _pace_hit_implied_vdot(training_plan.id, user_id, db, plan_vdot)
        if (
            pace_implied is not None
            and abs(pace_implied - plan_vdot) >= _VDOT_RECALIBRATION_THRESHOLD
        ):
            target_vdot = pace_implied
            source = "training_paces"

    if target_vdot is None:
        return None

    current_vdot = target_vdot
    delta = current_vdot - plan_vdot

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
        "VDOT recalibration: plan=%s old=%.1f new=%.1f delta=%.1f source=%s pace_updates=%d weekly_updates=%d",
        training_plan.id,
        old_vdot,
        current_vdot,
        delta,
        source,
        pace_updates,
        weekly_updates,
    )

    return {
        "recalibrated": True,
        "old_vdot": round(old_vdot, 1),
        "new_vdot": round(current_vdot, 1),
        "delta": round(delta, 1),
        "direction": direction,
        "source": source,
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
