"""Race readiness assessment service.

Synthesizes run log data, VDOT predictions, and plan adherence into
a single readiness report displayed on the plan view.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.services.race_predictor_service import RacePredictorService
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

        # ── Parse plan data for weekly targets ──
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

        # ── Fetch logged runs for this plan ──
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

        # ── Actual weekly volumes ──
        actual_weekly_km = _compute_weekly_volumes(all_runs_in_range, start_date, current_week)

        # ── Longest run ──
        longest_run_km = max((r.distance_km for r in all_runs_in_range), default=0)

        # ── Component scores ──
        volume_score, volume_detail = _score_volume(
            actual_weekly_km, planned_weekly_km, current_week
        )
        consistency_score, consistency_detail = _score_consistency(
            runs, plan.id, db, current_week
        )
        long_run_score, long_run_detail = _score_long_run(
            longest_run_km, planned_long_run_km, plan.target_distance
        )
        taper_score, taper_detail = _score_taper(current_week, total_weeks)

        # VDOT & predictions
        vdot_score, vdot_detail, predictions, vdot_data = _score_vdot(
            user_id, plan.target_distance, db
        )

        # ── Weighted total ──
        overall = (
            volume_score * ReadinessService.WEIGHT_VOLUME
            + vdot_score * ReadinessService.WEIGHT_VDOT
            + long_run_score * ReadinessService.WEIGHT_LONG_RUN
            + consistency_score * ReadinessService.WEIGHT_CONSISTENCY
            + taper_score * ReadinessService.WEIGHT_TAPER
        ) / 100  # scores are 0-100, weights sum to 100 → result is 0-100

        overall = round(min(100, max(0, overall)), 0)

        # ── Race scenarios ──
        scenarios = _build_scenarios(vdot_data, plan.target_distance)

        # ── Volume comparison data (for chart) ──
        volume_comparison = []
        for i in range(min(current_week, len(planned_weekly_km))):
            volume_comparison.append({
                "week": i + 1,
                "planned": round(planned_weekly_km[i], 1) if i < len(planned_weekly_km) else 0,
                "actual": round(actual_weekly_km[i], 1) if i < len(actual_weekly_km) else 0,
            })

        target_dist = _parse_float(plan.target_distance)
        distance_label = DISTANCE_LABELS.get(target_dist, f"{target_dist}km")

        return {
            "overall_score": int(overall),
            "overall_label": _score_label(overall),
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
                    "label": _score_label(volume_score),
                    "detail": volume_detail,
                },
                "fitness": {
                    "score": round(vdot_score),
                    "weight": ReadinessService.WEIGHT_VDOT,
                    "label": _score_label(vdot_score),
                    "detail": vdot_detail,
                },
                "long_run": {
                    "score": round(long_run_score),
                    "weight": ReadinessService.WEIGHT_LONG_RUN,
                    "label": _score_label(long_run_score),
                    "detail": long_run_detail,
                },
                "consistency": {
                    "score": round(consistency_score),
                    "weight": ReadinessService.WEIGHT_CONSISTENCY,
                    "label": _score_label(consistency_score),
                    "detail": consistency_detail,
                },
                "taper": {
                    "score": round(taper_score),
                    "weight": ReadinessService.WEIGHT_TAPER,
                    "label": _score_label(taper_score),
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


# ──────────────────────────────────────────────────────────────────
# Component scoring functions (each returns score 0-100 + detail str)
# ──────────────────────────────────────────────────────────────────


def _compute_weekly_volumes(
    runs: List[RunLog], start_date: date, num_weeks: int
) -> List[float]:
    """Bucket runs into weekly volumes aligned to the plan start."""
    volumes = [0.0] * num_weeks
    for run in runs:
        run_date = _to_date(run.date)
        if run_date is None:
            continue
        delta = (run_date - start_date).days
        if delta < 0:
            continue
        week_idx = delta // 7
        if week_idx < num_weeks:
            volumes[week_idx] += run.distance_km
    return volumes


def _score_volume(
    actual: List[float], planned: List[float], current_week: int
) -> tuple[float, str]:
    """Score volume adherence for completed weeks."""
    if current_week == 0 or not planned:
        return 50.0, "Plan hasn't started yet"

    weeks_to_check = min(current_week, len(planned), len(actual))
    if weeks_to_check == 0:
        return 50.0, "No completed weeks yet"

    total_planned = sum(planned[:weeks_to_check])
    total_actual = sum(actual[:weeks_to_check])

    if total_planned == 0:
        return 80.0, "No planned volume"

    ratio = total_actual / total_planned
    # 100% adherence = 100 score, scale down from there
    # >110% still caps at 100 (over-training is separate concern)
    score = min(100, ratio * 100)

    pct = round(ratio * 100)
    detail = f"{round(total_actual, 1)} / {round(total_planned, 1)} km ({pct}% of planned)"
    return score, detail


def _score_consistency(
    plan_runs: List[RunLog],
    plan_id: str,
    db: Session,
    current_week: int,
) -> tuple[float, str]:
    """Score run completion rate against planned workouts."""
    if current_week == 0:
        return 50.0, "Plan hasn't started yet"

    # Count planned non-rest workouts for completed weeks
    planned_count = (
        db.query(func.count(DailyWorkout.id))
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number <= current_week,
            DailyWorkout.workout_type.notin_(["rest", "recovery"]),
        )
        .scalar()
    ) or 0

    completed_count = len([
        r for r in plan_runs if r.daily_workout_id is not None
    ])

    if planned_count == 0:
        return 80.0, "No planned workouts found"

    ratio = min(1.0, completed_count / planned_count)
    score = ratio * 100

    detail = f"{completed_count} / {planned_count} workouts completed ({round(ratio * 100)}%)"
    return score, detail


def _score_long_run(
    longest_actual: float,
    longest_planned: float,
    target_distance_str: str,
) -> tuple[float, str]:
    """Score long run readiness against the target race distance."""
    target = _parse_float(target_distance_str)

    # Use the race distance as the benchmark (you don't need to run
    # the full distance in training, ~70-80% is typical)
    benchmark = target * 0.75
    if benchmark <= 0:
        benchmark = longest_planned or 15.0

    if longest_actual >= benchmark:
        score = 100.0
    elif benchmark > 0:
        score = (longest_actual / benchmark) * 100
    else:
        score = 50.0

    score = min(100, score)
    detail = f"Longest: {round(longest_actual, 1)} km (target ~{round(benchmark, 1)} km)"
    return score, detail


def _score_taper(current_week: int, total_weeks: int) -> tuple[float, str]:
    """Score taper positioning — are we where we should be?"""
    if total_weeks == 0:
        return 50.0, "No plan data"
    if current_week == 0:
        return 50.0, "Plan hasn't started yet"

    progress_pct = current_week / total_weeks

    if progress_pct >= 0.85:
        # Taper phase — should be resting
        return 95.0, "Taper phase — trust the training"
    elif progress_pct >= 0.70:
        # Peak/transition
        return 85.0, "Peak training phase — key workouts matter most now"
    elif progress_pct >= 0.40:
        # Build phase
        return 70.0, "Build phase — stay consistent"
    else:
        # Early base
        return 55.0, "Base phase — building foundation"


def _score_vdot(
    user_id: str,
    target_distance_str: str,
    db: Session,
) -> tuple[float, str, Dict, Dict]:
    """Score fitness based on VDOT trend and predictions."""
    prediction_data = RacePredictorService.get_predictions_for_user(user_id, db)

    current_vdot = prediction_data.get("current_vdot")
    trend = prediction_data.get("vdot_trend", "stable")
    predictions = prediction_data.get("predictions", {})

    vdot_info = {
        "current": current_vdot,
        "trend": trend,
        "run_count": prediction_data.get("run_count", 0),
        "best_effort": prediction_data.get("best_effort"),
    }

    if not current_vdot:
        return 50.0, "Not enough run data for VDOT", {}, vdot_info

    # Base score from VDOT itself (25=very beginner → 85=world class)
    # Map to a 40-100 range for recreational runners
    vdot_normalized = min(100, max(0, (current_vdot - 25) / 35 * 60 + 40))

    # Trend bonus/penalty
    if trend == "improving":
        vdot_normalized = min(100, vdot_normalized + 10)
        trend_str = "improving"
    elif trend == "declining":
        vdot_normalized = max(0, vdot_normalized - 10)
        trend_str = "declining"
    else:
        trend_str = "stable"

    detail = f"VDOT {current_vdot} ({trend_str})"

    # Format predictions for display
    formatted_predictions = {}
    target_dist = _parse_float(target_distance_str)
    for name, pred in predictions.items():
        formatted_predictions[name] = {
            "time": pred.get("formatted", ""),
            "distance_km": pred.get("distance_km", 0),
            "seconds": pred.get("seconds", 0),
            "range": pred.get("range", {}),
            "is_target": abs(pred.get("distance_km", 0) - target_dist) < 1.0,
        }

    return vdot_normalized, detail, formatted_predictions, vdot_info


def _build_scenarios(
    vdot_data: Dict, target_distance_str: str
) -> List[Dict[str, Any]]:
    """Build Dream/Solid/Tough/Survival race scenarios."""
    current_vdot = vdot_data.get("current")
    if not current_vdot:
        return []

    target_dist = _parse_float(target_distance_str)
    if target_dist <= 0:
        return []

    base_time = VDOTCalculator.predict_time_for_distance(current_vdot, target_dist)
    if not base_time:
        return []

    # Dream: VDOT+2, Solid: VDOT+0.5, Tough: VDOT-1, Survival: VDOT-3
    scenario_defs = [
        ("Dream", current_vdot + 2.0, 15, "Everything clicks — conservative start, strong finish"),
        ("Solid", current_vdot + 0.5, 50, "Smart race execution — controlled effort throughout"),
        ("Tough", current_vdot - 1.0, 25, "Challenging conditions or pacing errors — grit required"),
        ("Survival", current_vdot - 3.0, 10, "Worst case — walk/run to the finish, still get it done"),
    ]

    scenarios = []
    for name, vdot_adj, probability, description in scenario_defs:
        clamped = max(25.0, min(85.0, vdot_adj))
        time_secs = VDOTCalculator.predict_time_for_distance(clamped, target_dist)
        if time_secs:
            pace_secs_per_km = time_secs / target_dist
            pace_min = int(pace_secs_per_km // 60)
            pace_sec = int(pace_secs_per_km % 60)
            scenarios.append({
                "name": name,
                "time": VDOTCalculator.format_duration(time_secs),
                "pace": f"{pace_min}:{pace_sec:02d}/km",
                "probability": probability,
                "description": description,
            })

    return scenarios


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _parse_float(val) -> float:
    """Safely parse a string/float target distance."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _score_label(score: float) -> str:
    """Return a human-readable label for a 0-100 score."""
    if score >= 85:
        return "Strong"
    elif score >= 65:
        return "Good"
    elif score >= 45:
        return "Moderate"
    elif score >= 25:
        return "Developing"
    return "Needs work"
