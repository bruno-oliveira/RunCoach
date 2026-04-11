"""Race readiness assessment service.

Synthesizes run log data, VDOT predictions, and plan adherence into
a single readiness report displayed on the plan view.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.services.readiness_scoring import (
    build_scenarios,
    compute_weekly_volumes,
    parse_float,
    score_consistency,
    score_label,
    score_long_run,
    score_taper,
    score_vdot,
    score_volume,
)
from app.models import RunLog
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

# Distance labels for display
DISTANCE_LABELS = {
    5.0: "5K",
    10.0: "10K",
    21.1: "Half Marathon",
    21.0975: "Half Marathon",
    30.0: "Trail (30K)",
    42.2: "Marathon",
    42.195: "Marathon",
}

# Backward-compatible aliases for the private module-level functions
# that were previously defined in this file.
_compute_weekly_volumes = compute_weekly_volumes
_score_volume = score_volume
_score_consistency = score_consistency
_score_long_run = score_long_run
_score_taper = score_taper
_score_vdot = score_vdot
_build_scenarios = build_scenarios
_parse_float = parse_float
_score_label = score_label
_vdot_for_goal_time = None  # re-exported below

try:
    from app.services.readiness_scoring import vdot_for_goal_time
    _vdot_for_goal_time = vdot_for_goal_time
except ImportError:
    pass


class ReadinessService:
    """Computes race readiness from plan + run log data."""

    # Component weights (must sum to 100)
    WEIGHT_VOLUME = 25
    WEIGHT_VDOT = 25
    WEIGHT_LONG_RUN = 20
    WEIGHT_CONSISTENCY = 15
    WEIGHT_TAPER = 15

    @staticmethod
    def compute_readiness(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Build a full readiness report for a training plan.

        Returns None if there's insufficient data (no start date, no runs).
        """
        start_date = _to_date(plan.start_date)
        if not start_date:
            return None

        today = date.today()
        total_weeks = plan.weeks_duration or 0
        if total_weeks == 0:
            return None

        # Current week (1-indexed, clamped)
        delta_days = (today - start_date).days
        if delta_days < 0:
            current_week = 0
        else:
            current_week = min((delta_days // 7) + 1, total_weeks)

        weeks_remaining = max(0, total_weeks - current_week)

        # Race day estimate (end of last week)
        race_date = start_date + timedelta(weeks=total_weeks)

        # Parse plan data for weekly targets
        plan_data = json.loads(plan.plan_data) if plan.plan_data else []
        planned_weekly_km = []
        planned_long_run_km = 0.0
        peak_week_km = 0.0
        for week in plan_data:
            wk_km = week.get("total_km", 0)
            planned_weekly_km.append(wk_km)
            if wk_km > peak_week_km:
                peak_week_km = wk_km
            for workout in week.get("daily_workouts", []):
                if workout.get("type") == "long":
                    dist = workout.get("distance", 0)
                    if dist > planned_long_run_km:
                        planned_long_run_km = dist

        # Fetch logged runs for this plan
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.training_plan_id == plan.id,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        # Also consider runs not mapped to plan but in date range
        all_runs_in_range = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= datetime.combine(start_date, datetime.min.time()),
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        if not all_runs_in_range:
            return None

        # Actual weekly volumes
        actual_weekly_km = compute_weekly_volumes(all_runs_in_range, start_date, current_week)

        # Longest run
        longest_run_km = max((r.distance_km for r in all_runs_in_range), default=0)

        # Component scores
        volume_score, volume_detail = score_volume(
            actual_weekly_km, planned_weekly_km, current_week
        )
        consistency_score, consistency_detail = score_consistency(
            runs, plan.id, db, current_week
        )
        long_run_score, long_run_detail = score_long_run(
            longest_run_km, planned_long_run_km, plan.target_distance
        )
        taper_score, taper_detail = score_taper(current_week, total_weeks)

        # VDOT & predictions
        vdot_score, vdot_detail, predictions, vdot_data = score_vdot(
            user_id, plan.target_distance, db, goal_time=plan.goal_time
        )

        # Weighted total
        overall = (
            volume_score * ReadinessService.WEIGHT_VOLUME
            + vdot_score * ReadinessService.WEIGHT_VDOT
            + long_run_score * ReadinessService.WEIGHT_LONG_RUN
            + consistency_score * ReadinessService.WEIGHT_CONSISTENCY
            + taper_score * ReadinessService.WEIGHT_TAPER
        ) / 100

        overall = round(min(100, max(0, overall)), 0)

        # Race scenarios
        scenarios = build_scenarios(vdot_data, plan.target_distance)

        # Volume comparison data (for chart)
        volume_comparison = []
        for i in range(min(current_week, len(planned_weekly_km))):
            volume_comparison.append({
                "week": i + 1,
                "planned": round(planned_weekly_km[i], 1) if i < len(planned_weekly_km) else 0,
                "actual": round(actual_weekly_km[i], 1) if i < len(actual_weekly_km) else 0,
            })

        target_dist = plan.target_distance_km
        distance_label = DISTANCE_LABELS.get(target_dist, f"{target_dist}km")

        return {
            "overall_score": int(overall),
            "overall_label": score_label(overall),
            "distance_label": distance_label,
            "target_distance_km": target_dist,
            "current_week": current_week,
            "total_weeks": total_weeks,
            "weeks_remaining": weeks_remaining,
            "race_date": race_date.isoformat(),
            "race_date_display": race_date.strftime("%b %-d, %Y"),
            "days_to_race": (race_date - today).days,
            "components": {
                "volume": {
                    "score": round(volume_score),
                    "weight": ReadinessService.WEIGHT_VOLUME,
                    "label": score_label(volume_score),
                    "detail": volume_detail,
                },
                "fitness": {
                    "score": round(vdot_score),
                    "weight": ReadinessService.WEIGHT_VDOT,
                    "label": score_label(vdot_score),
                    "detail": vdot_detail,
                },
                "long_run": {
                    "score": round(long_run_score),
                    "weight": ReadinessService.WEIGHT_LONG_RUN,
                    "label": score_label(long_run_score),
                    "detail": long_run_detail,
                },
                "consistency": {
                    "score": round(consistency_score),
                    "weight": ReadinessService.WEIGHT_CONSISTENCY,
                    "label": score_label(consistency_score),
                    "detail": consistency_detail,
                },
                "taper": {
                    "score": round(taper_score),
                    "weight": ReadinessService.WEIGHT_TAPER,
                    "label": score_label(taper_score),
                    "detail": taper_detail,
                },
            },
            "predictions": predictions,
            "vdot": vdot_data,
            "scenarios": scenarios,
            "volume_comparison": volume_comparison,
            "longest_run_km": round(longest_run_km, 1),
            "peak_planned_long_run_km": round(planned_long_run_km, 1),
            "peak_week_km": round(peak_week_km, 1),
            "total_runs": len(all_runs_in_range),
            "total_km": round(sum(r.distance_km for r in all_runs_in_range), 1),
        }
