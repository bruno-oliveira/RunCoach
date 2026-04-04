"""Gap analysis service for plan-centric training insights.

Orchestrates AdaptationService, ReadinessService, and RacePredictorService
to produce a structured gap report showing where a runner stands relative
to their plan targets.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.core.training.vdot_calculator import VDOTCalculator
from app.services.adaptation_service import AdaptationService
from app.services.race_predictor_service import RacePredictorService
from app.services.readiness_service import ReadinessService
from app.utils import parse_race_time_to_seconds, to_date as _to_date

logger = logging.getLogger(__name__)


class GapAnalysisService:
    """Computes per-plan gap analysis across multiple dimensions."""

    @staticmethod
    def analyze_gaps(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Build a full gap report for a training plan.

        Returns None if there's insufficient data.
        """
        start_date = _to_date(plan.start_date)
        if not start_date:
            return None

        today = date.today()
        total_weeks = plan.weeks_duration or 0
        if total_weeks == 0:
            return None

        delta_days = (today - start_date).days
        if delta_days < 0:
            return None  # plan hasn't started

        current_week = min((delta_days // 7) + 1, total_weeks)

        # ── Parse plan data ──
        plan_data = json.loads(plan.plan_data) if plan.plan_data else []
        if not plan_data:
            return None

        # ── Fetch runs ──
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= datetime.combine(start_date, datetime.min.time()),
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        if not runs:
            return None

        # ── Fetch prediction data once for pace + fitness ──
        prediction_data = RacePredictorService.get_predictions_for_user(user_id, db)

        # ── Compute dimensions ──
        volume_gap = _compute_volume_gap(plan_data, runs, start_date, current_week)
        long_run_gap = _compute_long_run_gap(plan_data, runs, plan.target_distance_km)
        pace_gap = _compute_pace_gap(plan, runs, prediction_data)
        consistency = _compute_consistency(plan, runs, db, current_week)
        fitness = _compute_fitness_trajectory(plan, prediction_data)

        top_actions = _generate_top_actions(
            volume_gap, long_run_gap, pace_gap, consistency, fitness, current_week, total_weeks
        )

        return {
            "volume_gap": volume_gap,
            "long_run_gap": long_run_gap,
            "pace_gap": pace_gap,
            "consistency": consistency,
            "fitness_trajectory": fitness,
            "top_actions": top_actions,
            "current_week": current_week,
            "total_weeks": total_weeks,
        }

    @staticmethod
    def analyze_gaps_weekly(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return per-week gap breakpoints for trend charts.

        Each entry contains the week number and % of target achieved
        for volume, long run, and pace.
        """
        start_date = _to_date(plan.start_date)
        if not start_date:
            return None

        today = date.today()
        total_weeks = plan.weeks_duration or 0
        if total_weeks == 0:
            return None

        current_week = min((today - start_date).days // 7 + 1, total_weeks)
        if current_week < 1:
            return None

        plan_data = json.loads(plan.plan_data) if plan.plan_data else []
        if not plan_data:
            return None

        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= datetime.combine(start_date, datetime.min.time()),
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        # Bucket runs into weeks
        weekly_km: Dict[int, float] = {}
        weekly_longest: Dict[int, float] = {}
        weekly_paces: Dict[int, List[float]] = {}

        for run in runs:
            run_date = _to_date(run.date)
            if not run_date:
                continue
            delta = (run_date - start_date).days
            if delta < 0:
                continue
            wk = delta // 7 + 1
            if wk > current_week:
                continue
            weekly_km[wk] = weekly_km.get(wk, 0) + run.distance_km
            weekly_longest[wk] = max(weekly_longest.get(wk, 0), run.distance_km)
            if run.avg_pace_min_km:
                weekly_paces.setdefault(wk, []).append(run.avg_pace_min_km)

        weekly_breakpoints = []
        for wk_data in plan_data:
            wk_num = wk_data.get("week", 0)
            if wk_num > current_week:
                break

            planned_km = wk_data.get("total_km", 0)
            actual_km = weekly_km.get(wk_num, 0)

            # Find planned long run distance for this week
            planned_long = 0
            for wo in wk_data.get("daily_workouts", []):
                if wo.get("type") == "long":
                    planned_long = max(planned_long, wo.get("distance", 0))

            actual_long = weekly_longest.get(wk_num, 0)

            volume_pct = round(actual_km / planned_km * 100, 1) if planned_km > 0 else 0
            long_run_pct = round(actual_long / planned_long * 100, 1) if planned_long > 0 else 0

            weekly_breakpoints.append({
                "week": wk_num,
                "volume_pct": min(150, volume_pct),
                "long_run_pct": min(150, long_run_pct),
                "actual_km": round(actual_km, 1),
                "planned_km": round(planned_km, 1),
            })

        return weekly_breakpoints


# ──────────────────────────────────────────────────────────────────────
# Internal dimension computations
# ──────────────────────────────────────────────────────────────────────


def _compute_volume_gap(
    plan_data: List[dict],
    runs: List[RunLog],
    start_date: date,
    current_week: int,
) -> Dict[str, Any]:
    """Compare planned vs actual weekly volume."""
    planned_weekly = [w.get("total_km", 0) for w in plan_data]

    # Bucket actual runs into weeks
    actual_weekly = [0.0] * len(planned_weekly)
    for run in runs:
        run_date = _to_date(run.date)
        if not run_date:
            continue
        delta = (run_date - start_date).days
        if delta < 0:
            continue
        wk_idx = delta // 7
        if wk_idx < len(actual_weekly):
            actual_weekly[wk_idx] += run.distance_km

    weeks_to_check = min(current_week, len(planned_weekly))
    if weeks_to_check == 0:
        return {
            "planned_weekly_avg_km": 0,
            "actual_weekly_avg_km": 0,
            "deficit_pct": 0,
            "verdict": "on_track",
        }

    planned_avg = sum(planned_weekly[:weeks_to_check]) / weeks_to_check
    actual_avg = sum(actual_weekly[:weeks_to_check]) / weeks_to_check

    if planned_avg <= 0:
        deficit_pct = 0
        verdict = "on_track"
    else:
        deficit_pct = round((1 - actual_avg / planned_avg) * 100, 1)
        if deficit_pct <= 5:
            verdict = "on_track"
        elif deficit_pct <= 15:
            verdict = "close"
        elif deficit_pct <= 30:
            verdict = "behind"
        else:
            verdict = "far_behind"

    return {
        "planned_weekly_avg_km": round(planned_avg, 1),
        "actual_weekly_avg_km": round(actual_avg, 1),
        "deficit_pct": max(0, deficit_pct),
        "verdict": verdict,
    }


def _compute_long_run_gap(
    plan_data: List[dict],
    runs: List[RunLog],
    target_distance_km: float,
) -> Dict[str, Any]:
    """Compare planned peak long run vs actual longest run."""
    planned_long = 0.0
    for week in plan_data:
        for wo in week.get("daily_workouts", []):
            if wo.get("type") == "long":
                planned_long = max(planned_long, wo.get("distance", 0))

    if planned_long == 0:
        # Fallback: ~75% of race distance
        planned_long = target_distance_km * 0.75

    actual_longest = max((r.distance_km for r in runs), default=0)

    if planned_long <= 0:
        return {
            "target_km": 0,
            "longest_actual_km": round(actual_longest, 1),
            "deficit_pct": 0,
            "verdict": "on_track",
        }

    deficit_pct = round((1 - actual_longest / planned_long) * 100, 1)

    if deficit_pct <= 5:
        verdict = "on_track"
    elif deficit_pct <= 20:
        verdict = "close"
    elif deficit_pct <= 40:
        verdict = "behind"
    else:
        verdict = "far_behind"

    return {
        "target_km": round(planned_long, 1),
        "longest_actual_km": round(actual_longest, 1),
        "deficit_pct": max(0, deficit_pct),
        "verdict": verdict,
    }


def _compute_pace_gap(
    plan: TrainingPlan,
    runs: List[RunLog],
    prediction_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare target pace vs current running pace."""
    target_pace = plan.goal_pace
    if not target_pace:
        current_vdot = prediction_data.get("current_vdot")
        if current_vdot:
            pred_time = VDOTCalculator.predict_time_for_distance(
                current_vdot, plan.target_distance_km
            )
            if pred_time:
                target_pace = pred_time / 60 / plan.target_distance_km

    # Current pace from recent runs (last 4 weeks)
    recent_runs = [
        r for r in runs
        if r.avg_pace_min_km and r.avg_pace_min_km > 0
    ][-20:]  # last 20 runs max

    if not recent_runs or not target_pace:
        return {
            "target_pace_min_km": target_pace,
            "current_pace_min_km": None,
            "gap_seconds": 0,
            "verdict": "insufficient_data",
        }

    current_pace = sum(r.avg_pace_min_km for r in recent_runs) / len(recent_runs)
    gap_seconds = round((current_pace - target_pace) * 60)

    if gap_seconds <= 5:
        verdict = "on_track"
    elif gap_seconds <= 15:
        verdict = "close"
    elif gap_seconds <= 30:
        verdict = "behind"
    else:
        verdict = "far_behind"

    return {
        "target_pace_min_km": round(target_pace, 2),
        "current_pace_min_km": round(current_pace, 2),
        "gap_seconds": max(0, gap_seconds),
        "verdict": verdict,
    }


def _compute_consistency(
    plan: TrainingPlan,
    runs: List[RunLog],
    db: Session,
    current_week: int,
) -> Dict[str, Any]:
    """Compute workout completion rate and skipped/rescheduled counts."""
    adaptation_service = AdaptationService()
    skipped_data = adaptation_service.detect_skipped_workouts(plan.id, db)

    perf = adaptation_service.analyze_performance(plan.id, db)
    adherence = perf.get("adherence_rate", 0)

    completion_rate = round(adherence)

    if completion_rate >= 85:
        verdict = "on_track"
    elif completion_rate >= 70:
        verdict = "close"
    elif completion_rate >= 50:
        verdict = "needs_attention"
    else:
        verdict = "far_behind"

    return {
        "completion_rate_pct": completion_rate,
        "skipped_workouts": skipped_data.get("skipped", 0),
        "rescheduled_workouts": skipped_data.get("rescheduled", 0),
        "verdict": verdict,
    }


def _compute_fitness_trajectory(
    plan: TrainingPlan,
    prediction_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Assess VDOT trajectory relative to goal."""
    current_vdot = prediction_data.get("current_vdot")
    trend = prediction_data.get("vdot_trend", "stable")

    if not current_vdot:
        return {
            "current_vdot": None,
            "needed_vdot_for_goal": None,
            "vdot_trend": "stable",
            "on_track": None,
        }

    # Compute needed VDOT from goal time if available
    needed_vdot = None
    if plan.goal_time:
        goal_seconds = parse_race_time_to_seconds(plan.goal_time)
        if goal_seconds and plan.target_distance_km > 0:
            # Search for the VDOT that yields the goal time
            for test_vdot_10x in range(250, 850):
                test_vdot = test_vdot_10x / 10.0
                pred = VDOTCalculator.predict_time_for_distance(
                    test_vdot, plan.target_distance_km
                )
                if pred and pred <= goal_seconds:
                    needed_vdot = test_vdot
                    break

    on_track = None
    if needed_vdot is not None:
        vdot_gap = needed_vdot - current_vdot
        if vdot_gap <= 0:
            on_track = True
        elif vdot_gap <= 2.0 and trend == "improving":
            on_track = True
        elif vdot_gap <= 1.0:
            on_track = True
        else:
            on_track = False

    return {
        "current_vdot": current_vdot,
        "needed_vdot_for_goal": needed_vdot,
        "vdot_trend": trend,
        "on_track": on_track,
    }


def _generate_top_actions(
    volume: Dict,
    long_run: Dict,
    pace: Dict,
    consistency: Dict,
    fitness: Dict,
    current_week: int,
    total_weeks: int,
) -> List[str]:
    """Generate prioritized, actionable recommendations."""
    actions = []
    weeks_left = total_weeks - current_week

    # Consistency is the foundation
    if consistency.get("verdict") in ("needs_attention", "far_behind"):
        actions.append(
            "Focus on completing scheduled easy runs — consistency matters "
            "more than intensity right now"
        )

    # Volume gap
    v_deficit = volume.get("deficit_pct", 0)
    if v_deficit > 15:
        actions.append(
            f"Weekly volume is {v_deficit:.0f}% below plan — "
            "add short easy runs or extend existing ones to close the gap"
        )

    # Long run gap
    lr_deficit = long_run.get("deficit_pct", 0)
    lr_target = long_run.get("target_km", 0)
    lr_actual = long_run.get("longest_actual_km", 0)
    if lr_deficit > 15 and weeks_left > 2:
        km_gap = lr_target - lr_actual
        ramp = round(km_gap / max(weeks_left - 1, 1), 1)
        actions.append(
            f"Increase long run by ~{ramp} km/week to close the "
            f"{km_gap:.0f} km gap before taper"
        )

    # Pace gap
    if pace.get("verdict") in ("behind", "far_behind"):
        actions.append(
            "Add one tempo session per week to bring pace closer to target"
        )

    # Fitness trajectory
    if fitness.get("on_track") is False:
        needed = fitness.get("needed_vdot_for_goal")
        current = fitness.get("current_vdot")
        if needed and current:
            actions.append(
                f"VDOT gap: {current} vs {needed} needed — "
                "include quality speed work to improve fitness"
            )

    # Cap at 3 actions
    if not actions:
        actions.append("You're on track — keep following the plan!")

    return actions[:3]
