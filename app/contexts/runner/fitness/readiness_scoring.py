"""Readiness component scoring functions.

All _score_* helpers, weekly-volume bucketing, VDOT goal lookup,
scenario building, and formatting helpers used by ReadinessService.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, RunLog, WeeklyPlan
from app.utils import parse_race_time_to_seconds
from app.utils import to_date as _to_date

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
    detail = (
        f"{round(total_actual, 1)} / {round(total_planned, 1)} km ({pct}% of planned)"
    )
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

    completed_count = len([r for r in plan_runs if r.daily_workout_id is not None])

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
    detail = (
        f"Longest: {round(longest_actual, 1)} km (target ~{round(benchmark, 1)} km)"
    )
    return score, detail


def _freshness_from_tsb(tsb: float, in_taper: bool) -> float:
    """Map TSB (form) to a 0-100 freshness score, contextualized by phase.

    Near the race (taper) you want TSB rising toward positive — lingering
    fatigue means the taper isn't working, so it scores low. Mid-plan,
    moderate negative TSB is *productive* fatigue and only deep overreaching
    is penalized.
    """
    if in_taper:
        if tsb >= 10:
            return 100.0
        if tsb >= 5:
            return 90.0
        if tsb >= 0:
            return 75.0
        if tsb >= -10:
            return 55.0
        if tsb >= -20:
            return 35.0
        return 20.0
    # Build / peak: negative TSB expected.
    if tsb >= 5:
        return 85.0
    if tsb >= -10:
        return 80.0
    if tsb >= -25:
        return 70.0
    if tsb >= -35:
        return 50.0
    return 35.0


def score_taper(
    current_week: int,
    total_weeks: int,
    tsb: Optional[float] = None,
    tsb_form: Optional[str] = None,
) -> tuple[float, str]:
    """Score taper positioning, reconciled with actual TSB freshness.

    The calendar position sets the base expectation; when a trustworthy TSB
    is available it blends in (60/40) so an overreached runner two weeks out
    no longer reads a flat "Strong" purely from the calendar (audit G7).
    """
    if total_weeks == 0:
        return 50.0, "No plan data"
    if current_week == 0:
        return 50.0, "Plan hasn't started yet"

    progress_pct = current_week / total_weeks

    if progress_pct >= 0.85:
        base, detail = 95.0, "Taper phase -- trust the training"
    elif progress_pct >= 0.70:
        base, detail = 85.0, "Peak training phase -- key workouts matter most now"
    elif progress_pct >= 0.40:
        base, detail = 70.0, "Build phase -- stay consistent"
    else:
        base, detail = 55.0, "Base phase -- building foundation"

    if tsb is None:
        return base, detail

    freshness = _freshness_from_tsb(tsb, in_taper=progress_pct >= 0.85)
    final = round(base * 0.6 + freshness * 0.4, 1)
    detail += f" · Form TSB {tsb:+.0f}"
    if tsb_form:
        detail += f" ({tsb_form})"
    return final, detail


def vdot_for_goal_time(
    goal_time_str: str, target_distance_km: float
) -> Optional[float]:
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
                vdot_normalized = min(
                    85.0, max(60.0, (current_vdot - 25) / 35 * 25 + 60)
                )
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


# Mountain-simulation proxy factors: turn flat-terrain runs into uphill /
# downhill / transition proxies. Base by workout type, then boosted for hard
# efforts and runs with real vertical.
_SIM_BASE_FACTORS = {
    "interval": (0.60, 0.45, 2),
    "tempo": (0.60, 0.45, 2),
    "hill": (0.60, 0.45, 2),
    "long": (0.30, 0.40, 1),
}
_SIM_DEFAULT_FACTORS = (0.12, 0.15, 0)
_SIM_HARD_EFFORT_THRESHOLD = 7
_SIM_HARD_EFFORT_BOOST = (0.08, 0.05, 1)  # (uphill, downhill, transitions)
_SIM_VERT_M_PER_KM_THRESHOLD = 20
_SIM_VERT_BOOST = (0.10, 0.10, 0)  # uphill + downhill only


def _empty_simulation_result(detail: str) -> Dict[str, Any]:
    """Neutral (50) mountain-simulation result with zeroed metrics."""
    zero = {
        "uphill_effort_min": 0,
        "downhill_eccentric_min": 0,
        "hike_run_transition_reps": 0,
    }
    return {
        "score": 50.0,
        "detail": detail,
        "planned": dict(zero),
        "actual": dict(zero),
        "completion_pct": {"uphill": 0, "downhill": 0, "transitions": 0},
    }


def _simulation_factors(
    wtype: str, effort: int, m_per_km: float
) -> Tuple[float, float, int]:
    """Resolve (uphill, downhill, transitions) proxy factors for one run."""
    uphill, downhill, transitions = _SIM_BASE_FACTORS.get(wtype, _SIM_DEFAULT_FACTORS)
    if effort >= _SIM_HARD_EFFORT_THRESHOLD:
        d_up, d_down, d_trans = _SIM_HARD_EFFORT_BOOST
        uphill += d_up
        downhill += d_down
        transitions += d_trans
    if m_per_km >= _SIM_VERT_M_PER_KM_THRESHOLD:
        d_up, d_down, _ = _SIM_VERT_BOOST
        uphill += d_up
        downhill += d_down
    return uphill, downhill, transitions


def score_mountain_simulation(
    plan_data: List[dict],
    runs: List[RunLog],
    start_date: date,
    current_week: int,
    *,
    is_trail: bool,
    training_terrain: Optional[str],
    target_elevation_gain_m: Optional[float],
    plan_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Score mountain-race proxy execution for flat-only training setups.

    The score compares planned weekly flat-access simulation targets
    (uphill-effort minutes, downhill eccentric minutes, hike/run transitions)
    against proxies derived from executed runs.
    """
    if not is_trail or training_terrain != "flat":
        return None
    if (target_elevation_gain_m or 0) <= 0:
        return None
    if current_week <= 0:
        return _empty_simulation_result("Plan has not started yet")

    planned_uphill = 0
    planned_downhill = 0
    planned_transitions = 0
    for wk in plan_data:
        week_num = wk.get("week", 0)
        if week_num <= 0 or week_num > current_week:
            continue
        sim = wk.get("vertical_simulation") or {}
        planned_uphill += int(sim.get("uphill_effort_min", 0) or 0)
        planned_downhill += int(sim.get("downhill_eccentric_min", 0) or 0)
        planned_transitions += int(sim.get("hike_run_transition_reps", 0) or 0)

    # Safety fallback for legacy plans without vertical_simulation payload.
    if planned_uphill <= 0 and planned_downhill <= 0 and planned_transitions <= 0:
        return _empty_simulation_result("No simulation targets available in this plan")

    actual_uphill = 0.0
    actual_downhill = 0.0
    actual_transitions = 0

    for run in runs:
        if plan_id is not None and getattr(run, "training_plan_id", None) != plan_id:
            continue

        run_date = _to_date(run.date)
        if run_date is None:
            continue
        delta = (run_date - start_date).days
        if delta < 0:
            continue
        week_idx = delta // 7 + 1
        if week_idx > current_week:
            continue

        duration = float(getattr(run, "duration_minutes", 0) or 0)
        if duration <= 0:
            continue

        wtype = (getattr(run, "workout_type", "") or "easy").lower()
        effort = int(getattr(run, "perceived_effort", 0) or 0)
        distance = float(getattr(run, "distance_km", 0) or 0)
        elevation = float(getattr(run, "elevation_gain_m", 0) or 0)
        m_per_km = (elevation / distance) if distance > 0 else 0.0

        uphill_factor, downhill_factor, transitions = _simulation_factors(
            wtype, effort, m_per_km
        )
        actual_uphill += duration * uphill_factor
        actual_downhill += duration * downhill_factor
        actual_transitions += transitions

    def _ratio(actual: float, planned: float) -> float:
        if planned <= 0:
            return 1.0
        return max(0.0, min(1.2, actual / planned))

    uphill_ratio = _ratio(actual_uphill, planned_uphill)
    downhill_ratio = _ratio(actual_downhill, planned_downhill)
    transition_ratio = _ratio(actual_transitions, planned_transitions)

    score = (
        0.45 * uphill_ratio + 0.35 * downhill_ratio + 0.20 * transition_ratio
    ) * 100.0

    detail = (
        f"Uphill {round(actual_uphill):.0f}/{planned_uphill} min, "
        f"downhill {round(actual_downhill):.0f}/{planned_downhill} min, "
        f"transitions {actual_transitions}/{planned_transitions}"
    )

    return {
        "score": round(min(100.0, max(0.0, score)), 1),
        "detail": detail,
        "planned": {
            "uphill_effort_min": planned_uphill,
            "downhill_eccentric_min": planned_downhill,
            "hike_run_transition_reps": planned_transitions,
        },
        "actual": {
            "uphill_effort_min": int(round(actual_uphill)),
            "downhill_eccentric_min": int(round(actual_downhill)),
            "hike_run_transition_reps": int(actual_transitions),
        },
        "completion_pct": {
            "uphill": int(round(uphill_ratio * 100)),
            "downhill": int(round(downhill_ratio * 100)),
            "transitions": int(round(transition_ratio * 100)),
        },
    }


def build_scenarios(
    vdot_data: Dict,
    target_distance_str: str,
    target_elevation_gain_m: Optional[float] = None,
    trail_runs_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Build Dream/Solid/Tough/Survival race scenarios.

    For trail/ultra goals, ``target_elevation_gain_m`` and
    ``trail_runs_count`` flow through the race predictor so the scenarios
    reflect the actual course difficulty (the predictor already supports
    both signals — see :mod:`app.core.training.race_predictor`).
    """
    current_vdot = vdot_data.get("current")
    if not current_vdot:
        return []

    target_dist = parse_float(target_distance_str)
    if target_dist <= 0:
        return []

    base_time = VDOTCalculator.predict_time_for_distance(
        current_vdot,
        target_dist,
        elevation_gain_m=target_elevation_gain_m,
        trail_runs_count=trail_runs_count,
    )
    if not base_time:
        return []

    scenario_defs = [
        (
            "Dream",
            current_vdot + 2.0,
            15,
            "Everything clicks -- conservative start, strong finish",
        ),
        (
            "Solid",
            current_vdot + 0.5,
            50,
            "Smart race execution -- controlled effort throughout",
        ),
        (
            "Tough",
            current_vdot - 1.0,
            25,
            "Challenging conditions or pacing errors -- grit required",
        ),
        (
            "Survival",
            current_vdot - 3.0,
            10,
            "Worst case -- walk/run to the finish, still get it done",
        ),
    ]

    scenarios = []
    for name, vdot_adj, probability, description in scenario_defs:
        clamped = max(25.0, min(85.0, vdot_adj))
        time_secs = VDOTCalculator.predict_time_for_distance(
            clamped,
            target_dist,
            elevation_gain_m=target_elevation_gain_m,
            trail_runs_count=trail_runs_count,
        )
        if time_secs:
            pace_secs_per_km = time_secs / target_dist
            pace_min = int(pace_secs_per_km // 60)
            pace_sec = int(pace_secs_per_km % 60)
            scenarios.append(
                {
                    "name": name,
                    "time": VDOTCalculator.format_duration(time_secs),
                    "pace": f"{pace_min}:{pace_sec:02d}/km",
                    "probability": probability,
                    "description": description,
                }
            )

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
