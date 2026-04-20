"""Heart rate zone service — orchestrates zone computation and persistence."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.models.training_plan import TrainingPlan
from app.models.user import User

logger = logging.getLogger(__name__)


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
        max_hr, source = HRZoneCalculator.get_user_max_hr(
            user.id, db, user_age=user.age
        )
        zones = HRZoneCalculator.calculate_zones(max_hr)

        plan.hr_zones_data = {
            "max_hr": max_hr,
            "source": source,
            "zones": zones,
        }
        plan.max_heart_rate = max_hr

        logger.info(
            f"HR zones computed for plan {plan.id}: max_hr={max_hr} ({source})"
        )
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
