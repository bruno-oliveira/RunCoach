"""Race readiness assessment service.

Synthesizes run log data, VDOT predictions, and plan adherence into
a single readiness report displayed on the plan view.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.contexts.runner.fitness.readiness_scoring import (
    build_scenarios,
    compute_weekly_volumes,
    parse_float,
    score_consistency,
    score_label,
    score_long_run,
    score_mountain_simulation,
    score_taper,
    score_vdot,
    score_volume,
)
from app.models import RunLog
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.plan.plan_date_utils import compute_current_week
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
    from app.contexts.runner.fitness.readiness_scoring import vdot_for_goal_time
    _vdot_for_goal_time = vdot_for_goal_time
except ImportError:
    pass


def _parse_plan_targets(plan_data: list) -> tuple:
    """Extract weekly km targets, peak long run, and peak week km from plan data."""
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
    return planned_weekly_km, planned_long_run_km, peak_week_km


def _build_component_dict(score: float, weight: int, detail: str) -> Dict[str, Any]:
    """Build a standardized component entry for the readiness report."""
    return {
        "score": round(score),
        "weight": weight,
        "label": score_label(score),
        "detail": detail,
    }


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

        current_week = compute_current_week(
            start_date, today, total_weeks=total_weeks, pre_start=0
        )
        weeks_remaining = max(0, total_weeks - current_week)
        race_date = start_date + timedelta(weeks=total_weeks)

        planned_weekly_km, planned_long_run_km, peak_week_km = _parse_plan_targets(
            plan.plan_data or []
        )

        runs = (
            db.query(RunLog)
            .filter(RunLog.user_id == user_id, RunLog.training_plan_id == plan.id)
            .order_by(RunLog.date.asc())
            .all()
        )

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

        actual_weekly_km = compute_weekly_volumes(all_runs_in_range, start_date, current_week)
        longest_run_km = max((r.distance_km for r in all_runs_in_range), default=0)

        volume_score, volume_detail = score_volume(actual_weekly_km, planned_weekly_km, current_week)
        consistency_score, consistency_detail = score_consistency(runs, plan.id, db, current_week)
        long_run_score, long_run_detail = score_long_run(longest_run_km, planned_long_run_km, plan.target_distance)
        taper_score, taper_detail = score_taper(current_week, total_weeks)
        vdot_score, vdot_detail, predictions, vdot_data = score_vdot(
            user_id, plan.target_distance, db, goal_time=plan.goal_time
        )
        mountain_simulation = score_mountain_simulation(
            plan.plan_data or [],
            runs,
            start_date,
            current_week,
            is_trail=getattr(plan, "is_trail", False),
            training_terrain=getattr(plan, "training_terrain", None),
            target_elevation_gain_m=getattr(plan, "target_elevation_gain_m", None),
            plan_id=plan.id,
        )

        overall = (
            volume_score * ReadinessService.WEIGHT_VOLUME
            + vdot_score * ReadinessService.WEIGHT_VDOT
            + long_run_score * ReadinessService.WEIGHT_LONG_RUN
            + consistency_score * ReadinessService.WEIGHT_CONSISTENCY
            + taper_score * ReadinessService.WEIGHT_TAPER
        ) / 100
        overall = round(min(100, max(0, overall)), 0)

        volume_comparison = [
            {
                "week": i + 1,
                "planned": round(planned_weekly_km[i], 1) if i < len(planned_weekly_km) else 0,
                "actual": round(actual_weekly_km[i], 1) if i < len(actual_weekly_km) else 0,
            }
            for i in range(min(current_week, len(planned_weekly_km)))
        ]

        target_dist = plan.target_distance_km
        if getattr(plan, "is_trail", False):
            elev = getattr(plan, "target_elevation_gain_m", None)
            if elev is not None:
                distance_label = f"{target_dist:g} km Trail · {int(elev)} m vert"
            else:
                distance_label = f"{target_dist:g} km Trail"
        else:
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
                "volume": _build_component_dict(volume_score, ReadinessService.WEIGHT_VOLUME, volume_detail),
                "fitness": _build_component_dict(vdot_score, ReadinessService.WEIGHT_VDOT, vdot_detail),
                "long_run": _build_component_dict(long_run_score, ReadinessService.WEIGHT_LONG_RUN, long_run_detail),
                "consistency": _build_component_dict(consistency_score, ReadinessService.WEIGHT_CONSISTENCY, consistency_detail),
                "taper": _build_component_dict(taper_score, ReadinessService.WEIGHT_TAPER, taper_detail),
            },
            "mountain_simulation": (
                {
                    "score": round(mountain_simulation["score"]),
                    "label": score_label(mountain_simulation["score"]),
                    "detail": mountain_simulation["detail"],
                    "planned": mountain_simulation["planned"],
                    "actual": mountain_simulation["actual"],
                    "completion_pct": mountain_simulation["completion_pct"],
                }
                if mountain_simulation
                else None
            ),
            "predictions": predictions,
            "vdot": vdot_data,
            "scenarios": build_scenarios(
                vdot_data,
                plan.target_distance,
                target_elevation_gain_m=(
                    getattr(plan, "target_elevation_gain_m", None)
                    if getattr(plan, "is_trail", False)
                    else None
                ),
                trail_runs_count=(
                    RacePredictorService.get_trail_runs_count(plan.user_id, db)
                    if getattr(plan, "is_trail", False)
                    else None
                ),
            ),
            "volume_comparison": volume_comparison,
            "longest_run_km": round(longest_run_km, 1),
            "peak_planned_long_run_km": round(planned_long_run_km, 1),
            "peak_week_km": round(peak_week_km, 1),
            "total_runs": len(all_runs_in_range),
            "total_km": round(sum(r.distance_km for r in all_runs_in_range), 1),
        }
