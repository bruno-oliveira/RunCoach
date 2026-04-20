"""Performance analysis — read-only metrics from logged runs."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, WeeklyPlan

EFFORT_THRESHOLDS = {
    "too_easy": 3,
    "easy": 5,
    "hard": 7,
    "too_hard": 9,
}

PACE_VARIANCE_THRESHOLD = 0.15  # 15% variance from expected
MIN_RUNS_FOR_ADAPTATION = 3


def analyze_performance(
    training_plan_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Analyze user's performance on a training plan.

    Returns metrics about adherence, effort levels, and pace.
    """
    runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == training_plan_id)
        .order_by(RunLog.date)
        .all()
    )

    if not runs:
        return {
            "total_runs": 0,
            "adherence_rate": 0.0,
            "avg_effort": None,
            "effort_trend": "insufficient_data",
            "pace_consistency": None,
            "pace_consistency_by_type": {},
            "recommendations": ["Log more runs to get personalized feedback"],
        }

    total_logged = len(runs)

    planned_workouts = (
        db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == training_plan_id,
            DailyWorkout.workout_type.notin_(["rest", "recovery"]),
        )
        .count()
    )

    adherence_rate = (
        min(100.0, total_logged / planned_workouts * 100)
        if planned_workouts > 0
        else 0
    )

    efforts = [r.perceived_effort for r in runs if r.perceived_effort is not None]
    avg_effort = sum(efforts) / len(efforts) if efforts else None
    effort_trend = _analyze_effort_trend(efforts)

    # Per-type pace consistency (improvement #8):
    # Join runs to workouts to get planned type, then compute CV per type
    paces_by_type = _get_paces_by_type(training_plan_id, db)
    pace_consistency_by_type = {}
    all_per_type_cvs = []
    for wtype, paces in paces_by_type.items():
        cv = _calculate_pace_consistency(paces)
        if cv is not None:
            pace_consistency_by_type[wtype] = cv
            all_per_type_cvs.append((cv, len(paces)))

    # Weighted average of per-type CVs for a single headline number
    if all_per_type_cvs:
        total_weight = sum(count for _, count in all_per_type_cvs)
        pace_consistency = round(
            sum(cv * count for cv, count in all_per_type_cvs) / total_weight, 2
        )
    else:
        # Fall back to raw CV across all runs
        all_paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km]
        pace_consistency = _calculate_pace_consistency(all_paces)

    recommendations = _generate_recommendations(
        avg_effort, effort_trend, adherence_rate, pace_consistency
    )

    return {
        "total_runs": total_logged,
        "planned_workouts": planned_workouts,
        "adherence_rate": round(adherence_rate, 1),
        "avg_effort": round(avg_effort, 1) if avg_effort else None,
        "effort_trend": effort_trend,
        "pace_consistency": pace_consistency,
        "pace_consistency_by_type": pace_consistency_by_type,
        "recommendations": recommendations,
    }


def _get_paces_by_type(
    training_plan_id: str, db: Session,
) -> Dict[str, List[float]]:
    """Get paces grouped by planned workout type."""
    rows = (
        db.query(RunLog.avg_pace_min_km, DailyWorkout.workout_type)
        .outerjoin(DailyWorkout, RunLog.daily_workout_id == DailyWorkout.id)
        .filter(
            RunLog.training_plan_id == training_plan_id,
            RunLog.avg_pace_min_km.isnot(None),
        )
        .all()
    )
    paces_by_type: Dict[str, List[float]] = defaultdict(list)
    for pace, wtype in rows:
        key = wtype or "unknown"
        paces_by_type[key].append(pace)
    return paces_by_type


def _analyze_effort_trend(efforts: List) -> str:
    """Analyze if effort is increasing, decreasing, or stable."""
    if len(efforts) < 4:
        return "insufficient_data"

    mid_point = len(efforts) // 2
    first_half_avg = sum(efforts[:mid_point]) / mid_point
    second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)

    diff = second_half_avg - first_half_avg

    if diff > 1.0:
        return "increasing"
    elif diff < -1.0:
        return "decreasing"
    else:
        return "stable"


def _calculate_pace_consistency(paces: List[float]) -> Optional[float]:
    """Calculate coefficient of variation for pace."""
    if len(paces) < 2:
        return None

    avg_pace = sum(paces) / len(paces)
    variance = sum((p - avg_pace) ** 2 for p in paces) / (len(paces) - 1)
    std_dev = variance ** 0.5

    cv = (std_dev / avg_pace) * 100 if avg_pace > 0 else 100
    return round(cv, 2)


def _generate_recommendations(
    avg_effort: Optional[float],
    effort_trend: str,
    adherence_rate: float,
    pace_consistency: Optional[float],
) -> List[str]:
    """Generate actionable recommendations based on performance."""
    recommendations = []

    if adherence_rate < 50:
        recommendations.append("Try to complete more planned workouts for better results")
    elif adherence_rate > 90:
        recommendations.append("Excellent adherence! Keep up the great work!")

    if avg_effort:
        if avg_effort <= EFFORT_THRESHOLDS["too_easy"]:
            recommendations.append(
                "Your runs feel too easy - consider increasing intensity or distance"
            )
        elif avg_effort >= EFFORT_THRESHOLDS["too_hard"]:
            recommendations.append(
                "You're pushing too hard - consider reducing intensity to avoid burnout"
            )
        elif EFFORT_THRESHOLDS["easy"] < avg_effort < EFFORT_THRESHOLDS["hard"]:
            recommendations.append("Your effort levels look optimal!")

    if effort_trend == "increasing":
        recommendations.append("Fatigue may be building - ensure adequate recovery")
    elif effort_trend == "decreasing":
        recommendations.append("You're adapting well to the training load!")

    if pace_consistency:
        if pace_consistency < 5:
            recommendations.append("Your pacing is very consistent - great control!")
        elif pace_consistency > 15:
            recommendations.append("Work on more consistent pacing across runs")

    return recommendations if recommendations else ["Keep logging runs for personalized insights"]
