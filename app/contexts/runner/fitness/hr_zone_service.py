"""Heart rate zone service — orchestrates zone computation and persistence."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.training.hr_zone_calculator import (
    DEFAULT_MAX_HR,
    HR_ZONES_VERSION,
    MAX_HR_SPIKE_TOLERANCE_BPM,
    MAX_RELIABLE_MAX_HR,
    MIN_RELIABLE_MAX_HR,
    HRZoneCalculator,
)
from app.models.training_plan import TrainingPlan
from app.models.user import User

logger = logging.getLogger(__name__)


def detect_max_hr_from_runs(user_id: str, db: Session) -> Optional[int]:
    """Estimate max HR from run data, robust to single-sensor spikes.

    Optical wrist sensors routinely glitch 15-30 BPM high (cadence lock,
    loose strap), and the old "take the single highest reading ever" picked
    those spikes up permanently, inflating every zone for every future plan.

    Strategy: take the top recorded per-run max values inside the plausible
    human band; accept the highest only if the second-highest run
    corroborates it (within MAX_HR_SPIKE_TOLERANCE_BPM), otherwise fall back
    to the corroborated second reading. A single qualifying run is still
    accepted - one data point beats an age formula.
    """
    from app.models import RunLog

    rows = (
        db.query(RunLog.max_heart_rate)
        .filter(
            RunLog.user_id == user_id,
            RunLog.max_heart_rate.isnot(None),
            RunLog.max_heart_rate >= MIN_RELIABLE_MAX_HR,
            RunLog.max_heart_rate <= MAX_RELIABLE_MAX_HR,
        )
        .order_by(RunLog.max_heart_rate.desc())
        .limit(5)
        .all()
    )
    readings = [r[0] for r in rows]
    if not readings:
        return None
    if len(readings) == 1:
        return readings[0]
    top, second = readings[0], readings[1]
    if top - second > MAX_HR_SPIKE_TOLERANCE_BPM:
        return second
    return top


def get_user_max_hr(
    user_id: str,
    db: Session,
    user_age: Optional[int] = None,
) -> tuple[int, str]:
    """Determine max HR from run data, age, or a safe default.

    Returns:
        (max_hr, source) where source is "detected", "estimated", or "default".
    """
    detected = detect_max_hr_from_runs(user_id, db)
    if detected:
        return detected, "detected"

    if user_age and user_age > 0:
        return HRZoneCalculator.estimate_max_hr_age_based(user_age), "estimated"

    return DEFAULT_MAX_HR, "default"


class HRZoneService:
    """Compute, persist, and inject HR zones into training plans."""

    @staticmethod
    def compute_and_store_zones(
        plan: TrainingPlan,
        user: User,
        db: Session,
    ) -> list[dict]:
        """Calculate HR zones for a user and store them on the plan.

        Args:
            plan: TrainingPlan to annotate.
            user: The plan owner (for age fallback).
            db:   SQLAlchemy session.

        Returns:
            List of zone dicts with BPM ranges.
        """
        max_hr, source = get_user_max_hr(user.id, db, user_age=user.age)
        zones = HRZoneCalculator.calculate_zones(max_hr)

        plan.hr_zones_data = {
            "max_hr": max_hr,
            "source": source,
            "zones": zones,
            "version": HR_ZONES_VERSION,
        }
        plan.max_heart_rate = max_hr

        logger.info(f"HR zones computed for plan {plan.id}: max_hr={max_hr} ({source})")
        return zones

    @staticmethod
    def inject_hr_zones_into_plan_data(
        plan_data: list[dict],
        zones: list[dict],
    ) -> list[dict]:
        """Annotate each workout dict with its target HR zone info.

        Mutates plan_data in place and returns it for convenience.
        """
        for week in plan_data:
            for workout in week.get("daily_workouts", []):
                wtype = workout.get("type", "easy")
                target_zone = HRZoneCalculator.get_workout_zone(wtype)
                workout["hr_zone_target"] = target_zone
                workout["hr_zone_label"] = HRZoneCalculator.zone_label(
                    target_zone, zones
                )
        return plan_data

    @staticmethod
    def get_zones_for_plan(plan: TrainingPlan) -> Optional[dict]:
        """Deserialise stored HR zones from a plan.

        Returns:
            Dict with max_hr, source, and zones list — or None.
        """
        if not plan.hr_zones_data:
            return None
        return plan.hr_zones_data

    @staticmethod
    def zones_are_stale(plan: TrainingPlan) -> bool:
        """True when the plan carries zones from an older zone model."""
        data = plan.hr_zones_data
        if not data:
            return False  # nothing stored; the "missing" path handles this
        return data.get("version", 1) < HR_ZONES_VERSION
