"""Race pacing strategy engine with elevation-adjusted time estimation."""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models.run_log import RunLog
from app.schemas.race_prep_schemas import FeasibilityInfo, RaceBlueprint, RaceSegment

logger = logging.getLogger(__name__)

UPHILL_PENALTY_SEC_PER_KM_PER_PCT = 12
DOWNHILL_BONUS_SEC_PER_KM_PER_PCT = 5
MAX_DOWNHILL_BONUS_SEC_PER_KM = 15
PACE_CLAMP_SEC_PER_KM = 30


class RacePacingService:
    """Calculate elevation-adjusted race predictions and generate pace blueprints."""

    @staticmethod
    def get_user_vdot(user_id: str, db: Session, days: int = 90) -> dict[str, Any]:
        """Calculate median VDOT from recent RunLogs.

        Uses the top-3 VDOTs from the last N days to get a robust estimate.

        Args:
            user_id: The user's ID.
            db: Database session.
            days: Lookback window in days.

        Returns:
            Dict with vdot, run_count, and confidence level.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)

        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= cutoff,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= 1.0,
            )
            .order_by(RunLog.date.desc())
            .all()
        )

        if not runs:
            return {
                "vdot": 0.0,
                "run_count": 0,
                "confidence": "low",
            }

        vdots = [run.vdot for run in runs if run.vdot is not None]

        if len(vdots) >= 3:
            top_vdots = sorted(vdots, reverse=True)[:3]
            median_vdot = statistics.median(top_vdots)
        else:
            median_vdot = statistics.median(vdots) if vdots else 0.0

        run_count = len(vdots)
        if run_count >= 10:
            confidence = "high"
        elif run_count >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "vdot": round(median_vdot, 1),
            "run_count": run_count,
            "confidence": confidence,
        }

    @staticmethod
    def predict_flat_time(vdot: float, distance_km: float) -> int:
        """Predict flat-ground race time in seconds from VDOT.

        Args:
            vdot: User's VDOT value.
            distance_km: Race distance.

        Returns:
            Predicted time in seconds.
        """
        predicted = VDOTCalculator.predict_time_for_distance(vdot, distance_km)
        return predicted if predicted else 0

    @staticmethod
    def predict_elevation_adjusted_time(
        vdot: float,
        distance_km: float,
        elevation_profile: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Calculate elevation-adjusted race time.

        Args:
            vdot: User's VDOT value.
            distance_km: Race distance.
            elevation_profile: List of segment dicts with grade_pct.

        Returns:
            Dict with flat_time, elevation_adjusted, and elevation_penalty.
        """
        flat_time = RacePacingService.predict_flat_time(vdot, distance_km)
        if flat_time == 0:
            return {
                "flat_time": 0,
                "elevation_adjusted": 0,
                "elevation_penalty": 0,
            }

        base_pace_sec_per_km = flat_time / distance_km

        total_penalty = 0.0
        total_bonus = 0.0

        for seg in elevation_profile:
            seg_distance = seg["end_km"] - seg["start_km"]
            grade = seg["grade_pct"]
            net_grade = seg.get("net_grade_pct", grade)

            if grade > 0:
                penalty = grade * UPHILL_PENALTY_SEC_PER_KM_PER_PCT * seg_distance
                total_penalty += penalty

            if net_grade < 0:
                bonus = abs(net_grade) * DOWNHILL_BONUS_SEC_PER_KM_PER_PCT * seg_distance
                bonus = min(bonus, MAX_DOWNHILL_BONUS_SEC_PER_KM * seg_distance)
                total_bonus += bonus

        elevation_penalty = int(total_penalty - total_bonus)
        elevation_adjusted = flat_time + max(0, elevation_penalty)

        return {
            "flat_time": flat_time,
            "elevation_adjusted": elevation_adjusted,
            "elevation_penalty": elevation_penalty,
        }

    @staticmethod
    def validate_feasibility(
        target_time: int,
        flat_time: int,
        elevation_adjusted: int,
    ) -> FeasibilityInfo:
        """Assess how realistic a target time is.

        Args:
            target_time: User's desired race time in seconds.
            flat_time: Flat-ground predicted time.
            elevation_adjusted: Elevation-adjusted predicted time.

        Returns:
            FeasibilityInfo with label, message, and color.
        """
        if flat_time == 0:
            return FeasibilityInfo(
                label="Unknown",
                message="Not enough data to assess feasibility.",
                color="gray",
            )

        if target_time <= flat_time * 0.90:
            return FeasibilityInfo(
                label="Aggressive",
                message="This goal is significantly faster than your current fitness suggests. Consider building more base mileage first.",
                color="red",
            )

        if target_time <= flat_time * 0.95:
            return FeasibilityInfo(
                label="Challenging",
                message="This is an ambitious but possible goal with focused training. Expect a tough race.",
                color="yellow",
            )

        if target_time <= elevation_adjusted * 1.05:
            return FeasibilityInfo(
                label="Realistic",
                message="This target aligns well with your current fitness and the course profile.",
                color="green",
            )

        return FeasibilityInfo(
            label="Conservative",
            message="You have room to push harder. This could be a comfortable race day.",
            color="blue",
        )

    @staticmethod
    def generate_pace_blueprint(
        elevation_profile: list[dict[str, Any]],
        target_time_seconds: int,
        user_vdot: float,
        distance_km: float,
    ) -> RaceBlueprint:
        """Generate a segment-by-segment pacing blueprint.

        Args:
            elevation_profile: List of segment dicts with grade_pct.
            target_time_seconds: Desired total race time.
            user_vdot: User's VDOT value.
            distance_km: Total race distance.

        Returns:
            RaceBlueprint with paced segments.
        """
        flat_time = RacePacingService.predict_flat_time(user_vdot, distance_km)
        elevation_data = RacePacingService.predict_elevation_adjusted_time(
            user_vdot, distance_km, elevation_profile
        )

        base_pace_sec_per_km = target_time_seconds / distance_km if distance_km > 0 else 0

        segments = []
        cumulative_time = 0

        for seg in elevation_profile:
            seg_distance = seg["end_km"] - seg["start_km"]
            grade = seg["grade_pct"]
            net_grade = seg.get("net_grade_pct", grade)

            adjusted_pace = base_pace_sec_per_km

            if grade > 0:
                adjusted_pace += grade * UPHILL_PENALTY_SEC_PER_KM_PER_PCT

            if net_grade < 0:
                bonus = abs(net_grade) * DOWNHILL_BONUS_SEC_PER_KM_PER_PCT
                bonus = min(bonus, MAX_DOWNHILL_BONUS_SEC_PER_KM)
                adjusted_pace -= bonus

            if base_pace_sec_per_km > 0:
                diff = adjusted_pace - base_pace_sec_per_km
                adjusted_pace = base_pace_sec_per_km + max(
                    -PACE_CLAMP_SEC_PER_KM, min(PACE_CLAMP_SEC_PER_KM, diff)
                )

            segment_time = int(adjusted_pace * seg_distance)
            cumulative_time += segment_time

            pace_min_km = adjusted_pace / 60.0
            pace_str = VDOTCalculator.format_pace(pace_min_km)

            segments.append(RaceSegment(
                segment_number=seg["segment_number"],
                start_km=seg["start_km"],
                end_km=seg["end_km"],
                elevation_m=seg["avg_elevation"],
                grade_pct=seg["grade_pct"],
                net_grade_pct=seg.get("net_grade_pct", 0.0),
                target_pace_min_km=round(pace_min_km, 2),
                target_pace_str=pace_str,
                target_time_seconds=segment_time,
                cumulative_time_seconds=cumulative_time,
            ))

        feasibility = RacePacingService.validate_feasibility(
            target_time_seconds, flat_time, elevation_data["elevation_adjusted"]
        )

        return RaceBlueprint(
            segments=segments,
            total_distance_km=round(distance_km, 2),
            target_time_seconds=target_time_seconds,
            target_time_str=VDOTCalculator.format_duration(target_time_seconds),
            estimated_time_seconds=elevation_data["elevation_adjusted"],
            user_vdot=user_vdot,
            feasibility=feasibility,
        )
