"""Readiness component scoring functions.

All _score_* helpers, weekly-volume bucketing, VDOT goal lookup,
scenario building, and formatting helpers used by ReadinessService.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, RunLog, WeeklyPlan
from app.services.race_predictor_service import RacePredictorService
from app.utils import parse_race_time_to_seconds, to_date as _to_date


# ------------------------------------------------------------------
# Weekly volume bucketing
# ------------------------------------------------------------------


def compute_weekly_volumes(
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


# ------------------------------------------------------------------
# Component scoring functions (each returns score 0-100 + detail str)
# ------------------------------------------------------------------


def score_volume(
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
    score = min(100, ratio * 100)

    pct = round(ratio * 100)
    detail = f"{round(total_actual, 1)} / {round(total_planned, 1)} km ({pct}% of planned)"
    return score, detail


def score_consistency(
    plan_runs: List[RunLog],
    plan_id: str,
    db: Session,
    current_week: int,
) -> tuple[float, str]:
    """Score run completion rate against planned workouts."""
    if current_week == 0:
        return 50.0, "Plan hasn't started yet"

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


def score_long_run(
    longest_actual: float,
    longest_planned: float,
    target_distance_str: str,
) -> tuple[float, str]:
    """Score long run readiness against the target race distance."""
    target = parse_float(target_distance_str)

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


def score_taper(current_week: int, total_weeks: int) -> tuple[float, str]:
    """Score taper positioning."""
    if total_weeks == 0:
        return 50.0, "No plan data"
    if current_week == 0:
        return 50.0, "Plan hasn't started yet"

    progress_pct = current_week / total_weeks

    if progress_pct >= 0.85:
        return 95.0, "Taper phase -- trust the training"
    elif progress_pct >= 0.70:
        return 85.0, "Peak training phase -- key workouts matter most now"
    elif progress_pct >= 0.40:
        return 70.0, "Build phase -- stay consistent"
    else:
        return 55.0, "Base phase -- building foundation"


def vdot_for_goal_time(goal_time_str: str, target_distance_km: float) -> Optional[float]:
    """Find the VDOT needed to achieve a goal time at a given distance."""
    goal_seconds = parse_race_time_to_seconds(goal_time_str)
    if not goal_seconds or target_distance_km <= 0:
        return None

    for test_vdot_10x in range(250, 850):
        test_vdot = test_vdot_10x / 10.0
        pred = VDOTCalculator.predict_time_for_distance(test_vdot, target_distance_km)
        if pred and pred <= goal_seconds:
            return test_vdot

    return None


def score_vdot(
    user_id: str,
    target_distance_str: str,
    db: Session,
    *,
    goal_time: Optional[str] = None,
) -> tuple[float, str, Dict, Dict]:
    """Score fitness based on VDOT relative to the runner's goal."""
    prediction_data = RacePredictorService.get_predictions_for_user(user_id, db)

    current_vdot = prediction_data.get("current_vdot")
    trend = prediction_data.get("vdot_trend", "stable")
    predictions = prediction_data.get("predictions", {})

    target_dist = parse_float(target_distance_str)

    needed_vdot = None
    if goal_time:
        needed_vdot = vdot_for_goal_time(goal_time, target_dist)

    vdot_info = {
        "current": current_vdot,
        "trend": trend,
        "run_count": prediction_data.get("run_count", 0),
        "best_effort": prediction_data.get("best_effort"),
        "needed_for_goal": needed_vdot,
    }

    if not current_vdot:
        return 50.0, "Not enough run data for VDOT", {}, vdot_info

    # Goal-relative scoring
    if needed_vdot is not None:
        vdot_gap = needed_vdot - current_vdot

        if vdot_gap <= 0:
            vdot_normalized = 100.0
        elif vdot_gap <= 1.0:
            vdot_normalized = 100.0 - (vdot_gap * 15.0)
        elif vdot_gap <= 3.0:
            vdot_normalized = 85.0 - ((vdot_gap - 1.0) * 10.0)
        elif vdot_gap <= 5.0:
            vdot_normalized = 65.0 - ((vdot_gap - 3.0) * 10.0)
        else:
            vdot_normalized = max(20.0, 45.0 - ((vdot_gap - 5.0) * 5.0))

        if trend == "improving":
            vdot_normalized = min(100, vdot_normalized + 5)
            trend_str = "improving"
        elif trend == "declining":
            vdot_normalized = max(0, vdot_normalized - 5)
            trend_str = "declining"
        else:
            trend_str = "stable"

        gap_dir = "above" if current_vdot >= needed_vdot else "below"
        gap_val = abs(current_vdot - needed_vdot)
        detail = f"VDOT {current_vdot} ({trend_str}) -- {gap_val:.1f} {gap_dir} goal VDOT {needed_vdot}"
    else:
        # Fallback: distance-relative assessment
        if target_dist > 0:
            predicted_time = VDOTCalculator.predict_time_for_distance(
                current_vdot, target_dist
            )
            if predicted_time:
                vdot_normalized = min(85.0, max(60.0, (current_vdot - 25) / 35 * 25 + 60))
            else:
                vdot_normalized = 50.0
        else:
            vdot_normalized = min(100, max(0, (current_vdot - 25) / 35 * 60 + 40))

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
    for name, pred in predictions.items():
        formatted_predictions[name] = {
            "time": pred.get("formatted", ""),
            "distance_km": pred.get("distance_km", 0),
            "seconds": pred.get("seconds", 0),
            "range": pred.get("range", {}),
            "is_target": abs(pred.get("distance_km", 0) - target_dist) < 1.0,
        }

    return vdot_normalized, detail, formatted_predictions, vdot_info


def build_scenarios(
    vdot_data: Dict, target_distance_str: str
) -> List[Dict[str, Any]]:
    """Build Dream/Solid/Tough/Survival race scenarios."""
    current_vdot = vdot_data.get("current")
    if not current_vdot:
        return []

    target_dist = parse_float(target_distance_str)
    if target_dist <= 0:
        return []

    base_time = VDOTCalculator.predict_time_for_distance(current_vdot, target_dist)
    if not base_time:
        return []

    scenario_defs = [
        ("Dream", current_vdot + 2.0, 15, "Everything clicks -- conservative start, strong finish"),
        ("Solid", current_vdot + 0.5, 50, "Smart race execution -- controlled effort throughout"),
        ("Tough", current_vdot - 1.0, 25, "Challenging conditions or pacing errors -- grit required"),
        ("Survival", current_vdot - 3.0, 10, "Worst case -- walk/run to the finish, still get it done"),
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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def parse_float(val) -> float:
    """Safely parse a string/float target distance."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def score_label(score: float) -> str:
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
