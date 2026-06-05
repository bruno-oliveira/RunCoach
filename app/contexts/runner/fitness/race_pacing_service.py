"""Race pacing strategy engine with elevation-adjusted time estimation."""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.training import race_predictor
from app.core.training.vdot_calculator import VDOTCalculator
from app.models.run_log import RunLog
from app.schemas.race_prep_schemas import FeasibilityInfo, RaceBlueprint, RaceSegment

logger = logging.getLogger(__name__)

DOWNHILL_BONUS_SEC_PER_KM_PER_PCT = 5
MAX_DOWNHILL_BONUS_SEC_PER_KM = 15
PACE_CLAMP_SEC_PER_KM = 30


def _is_trail_course(distance_km: float, total_elevation_gain_m: float) -> bool:
    """Course averages enough climbing to be classified as trail (>=20 m/km)."""
    if distance_km <= 0:
        return False
    return (
        total_elevation_gain_m / distance_km
        >= race_predictor.TRAIL_ELEVATION_M_PER_KM_THRESHOLD
    )


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
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(
            tzinfo=None
        )

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
    def predict_flat_time(
        vdot: float,
        distance_km: float,
        endurance_factor: Optional[float] = None,
    ) -> int:
        """Predict flat-ground race time in seconds from VDOT.

        Args:
            vdot: User's VDOT value.
            distance_km: Race distance.
            endurance_factor: Optional personalized endurance multiplier
                (>= 1.0) so the race-day pacing plan matches the same
                endurance-adjusted prediction shown on the predictions card
                (audit E3).

        Returns:
            Predicted time in seconds.
        """
        predicted = VDOTCalculator.predict_time_for_distance(
            vdot, distance_km, endurance_factor=endurance_factor
        )
        return predicted if predicted else 0

    @staticmethod
    def predict_elevation_adjusted_time(
        vdot: float,
        distance_km: float,
        elevation_profile: list[dict[str, Any]],
        trail_runs_count: Optional[int] = None,
        endurance_factor: Optional[float] = None,
    ) -> dict[str, int]:
        """Calculate a realistic race time from segment-level elevation data.

        Combines a piecewise grade penalty (12 → 16 → 24 → 35 sec/km/% as the
        grade gets steeper), a downhill bonus capped at 15 sec/km, an
        ultra-endurance decay for events beyond 3 hours, a personalized
        endurance multiplier, and a trail-inexperience multiplier for runners
        with few logged trail runs.
        """
        flat_time = RacePacingService.predict_flat_time(
            vdot, distance_km, endurance_factor=endurance_factor
        )
        if flat_time == 0:
            return {
                "flat_time": 0,
                "elevation_adjusted": 0,
                "elevation_penalty": 0,
            }

        total_penalty = 0.0
        total_bonus = 0.0
        total_elevation_gain = 0.0

        for seg in elevation_profile:
            seg_distance = seg["end_km"] - seg["start_km"]
            grade = seg["grade_pct"]
            net_grade = seg.get("net_grade_pct", grade)
            total_elevation_gain += seg.get("elevation_gain", 0.0)

            if grade > 0:
                rate = race_predictor.grade_penalty_rate(grade)
                total_penalty += grade * rate * seg_distance

            if net_grade < 0:
                bonus = (
                    abs(net_grade) * DOWNHILL_BONUS_SEC_PER_KM_PER_PCT * seg_distance
                )
                bonus = min(bonus, MAX_DOWNHILL_BONUS_SEC_PER_KM * seg_distance)
                total_bonus += bonus

        slope_penalty = total_penalty - total_bonus
        adjusted = flat_time + max(0.0, slope_penalty)

        adjusted *= race_predictor.ultra_endurance_decay(adjusted)

        if _is_trail_course(distance_km, total_elevation_gain):
            adjusted *= race_predictor.trail_inexperience_factor(trail_runs_count)

        elevation_adjusted = int(round(adjusted))
        return {
            "flat_time": flat_time,
            "elevation_adjusted": elevation_adjusted,
            "elevation_penalty": int(round(slope_penalty)),
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
        trail_runs_count: Optional[int] = None,
        endurance_factor: Optional[float] = None,
    ) -> RaceBlueprint:
        """Generate a segment-by-segment pacing blueprint.

        Per-segment pace = base_pace + piecewise grade penalty - downhill bonus,
        clamped to ±30 sec/km, then scaled so cumulative segment time equals
        the target. The scaling absorbs any rounding drift and ensures that
        when ``target_time_seconds`` itself includes the trail-inexperience
        multiplier (as is the case for trail courses), each segment's pace
        carries that slowdown too.
        """
        flat_time = RacePacingService.predict_flat_time(
            user_vdot, distance_km, endurance_factor=endurance_factor
        )
        elevation_data = RacePacingService.predict_elevation_adjusted_time(
            user_vdot,
            distance_km,
            elevation_profile,
            trail_runs_count=trail_runs_count,
            endurance_factor=endurance_factor,
        )

        base_pace_sec_per_km = (
            target_time_seconds / distance_km if distance_km > 0 else 0
        )

        raw_paces: list[float] = []
        seg_distances: list[float] = []
        for seg in elevation_profile:
            seg_distance = seg["end_km"] - seg["start_km"]
            grade = seg["grade_pct"]
            net_grade = seg.get("net_grade_pct", grade)

            pace = base_pace_sec_per_km
            if grade > 0:
                pace += grade * race_predictor.grade_penalty_rate(grade)
            if net_grade < 0:
                bonus = abs(net_grade) * DOWNHILL_BONUS_SEC_PER_KM_PER_PCT
                bonus = min(bonus, MAX_DOWNHILL_BONUS_SEC_PER_KM)
                pace -= bonus

            if base_pace_sec_per_km > 0:
                diff = pace - base_pace_sec_per_km
                pace = base_pace_sec_per_km + max(
                    -PACE_CLAMP_SEC_PER_KM, min(PACE_CLAMP_SEC_PER_KM, diff)
                )

            raw_paces.append(pace)
            seg_distances.append(seg_distance)

        raw_total_time = sum(p * d for p, d in zip(raw_paces, seg_distances))
        scale = target_time_seconds / raw_total_time if raw_total_time > 0 else 1.0

        segments = []
        cumulative_time = 0
        for seg, raw_pace, seg_distance in zip(
            elevation_profile, raw_paces, seg_distances
        ):
            adjusted_pace = raw_pace * scale
            segment_time = int(round(adjusted_pace * seg_distance))
            cumulative_time += segment_time

            pace_min_km = adjusted_pace / 60.0
            pace_str = VDOTCalculator.format_pace(pace_min_km)

            segments.append(
                RaceSegment(
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
                )
            )

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
