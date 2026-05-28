"""Gap analysis service for plan-centric training insights.

Orchestrates AdaptationService, ReadinessService, and RacePredictorService
to produce a structured gap report showing where a runner stands relative
to their plan targets.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.fitness.readiness_scoring import score_mountain_simulation
from app.core.coaching.verdict import verdict_from_thresholds
from app.core.training.plan_calendar import compute_current_week
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog, TrainingPlan
from app.utils import parse_race_time_to_seconds
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

# Ladder thresholds (best→worst) for the on_track/close/behind/far_behind verdict.
# Deficit/gap ladders are "lower is better"; completion is "higher is better".
_VOLUME_DEFICIT_THRESHOLDS = (5, 15, 30)  # percent below planned weekly volume
_LONG_RUN_DEFICIT_THRESHOLDS = (5, 20, 40)  # percent below planned peak long run
_ELEVATION_DEFICIT_THRESHOLDS = (10, 30, 50)  # percent below expected vert
_PACE_GAP_THRESHOLDS = (5, 15, 30)  # seconds/km slower than target
_COMPLETION_RATE_THRESHOLDS = (85, 70, 50)  # percent of workouts completed
_COMPLETION_LABELS = ("on_track", "close", "needs_attention", "far_behind")


class _PlanGapContext:
    """Shared setup data for gap analysis: parsed plan, logged runs, and week state."""

    __slots__ = (
        "plan",
        "plan_data",
        "start_date",
        "total_weeks",
        "current_week",
        "runs",
    )

    def __init__(
        self,
        plan: TrainingPlan,
        plan_data: List[dict],
        start_date: date,
        total_weeks: int,
        current_week: int,
        runs: List[RunLog],
    ) -> None:
        self.plan = plan
        self.plan_data = plan_data
        self.start_date = start_date
        self.total_weeks = total_weeks
        self.current_week = current_week
        self.runs = runs


def _load_gap_context(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
    *,
    require_runs: bool,
) -> Optional[_PlanGapContext]:
    """Parse plan data, fetch runs, and compute the current-week cursor.

    Returns None if any precondition for gap analysis is not met:
    plan hasn't started, no duration, no plan_data, or (when
    ``require_runs`` is True) no logged runs yet.
    """
    start_date = _to_date(plan.start_date)
    if not start_date:
        return None

    total_weeks = plan.weeks_duration or 0
    if total_weeks == 0:
        return None

    if (date.today() - start_date).days < 0:
        return None  # plan hasn't started

    current_week = compute_current_week(
        start_date, date.today(), total_weeks=total_weeks
    )
    if current_week < 1:
        return None

    plan_data = plan.plan_data if plan.plan_data else []
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
    if require_runs and not runs:
        return None

    return _PlanGapContext(plan, plan_data, start_date, total_weeks, current_week, runs)


def _bucket_runs_by_week(
    runs: List[RunLog], start_date: date, current_week: int
) -> tuple[Dict[int, float], Dict[int, float]]:
    """Group runs into (week_num → total_km) and (week_num → longest_km).

    Runs before plan start or after the current week are dropped.
    """
    weekly_km: Dict[int, float] = {}
    weekly_longest: Dict[int, float] = {}

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

    return weekly_km, weekly_longest


def _weekly_breakpoint(
    wk_data: dict, weekly_km: Dict[int, float], weekly_longest: Dict[int, float]
) -> dict:
    """Build one per-week trend-chart datapoint."""
    wk_num = wk_data.get("week", 0)
    planned_km = wk_data.get("total_km", 0)
    actual_km = weekly_km.get(wk_num, 0)

    planned_long = 0.0
    for wo in wk_data.get("daily_workouts", []):
        if wo.get("type") == "long":
            planned_long = max(planned_long, wo.get("distance", 0))
    actual_long = weekly_longest.get(wk_num, 0)

    volume_pct = round(actual_km / planned_km * 100, 1) if planned_km > 0 else 0
    long_run_pct = round(actual_long / planned_long * 100, 1) if planned_long > 0 else 0

    return {
        "week": wk_num,
        "volume_pct": min(150, volume_pct),
        "long_run_pct": min(150, long_run_pct),
        "actual_km": round(actual_km, 1),
        "planned_km": round(planned_km, 1),
    }


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
        ctx = _load_gap_context(plan, user_id, db, require_runs=True)
        if ctx is None:
            return None

        prediction_data = RacePredictorService.get_predictions_for_user(user_id, db)

        volume_gap = _compute_volume_gap(
            ctx.plan_data, ctx.runs, ctx.start_date, ctx.current_week
        )
        long_run_gap = _compute_long_run_gap(
            ctx.plan_data, ctx.runs, plan.target_distance_km
        )
        pace_gap = _compute_pace_gap(plan, ctx.runs, prediction_data)
        consistency = _compute_consistency(plan, ctx.runs, db, ctx.current_week)
        fitness = _compute_fitness_trajectory(plan, prediction_data)
        elevation_gap = _compute_elevation_gap(
            plan, ctx.plan_data, ctx.runs, ctx.current_week
        )
        mountain_simulation = score_mountain_simulation(
            ctx.plan_data,
            ctx.runs,
            ctx.start_date,
            ctx.current_week,
            is_trail=getattr(plan, "is_trail", False),
            training_terrain=getattr(plan, "training_terrain", None),
            target_elevation_gain_m=getattr(plan, "target_elevation_gain_m", None),
            plan_id=plan.id,
        )

        top_actions = _generate_top_actions(
            volume_gap,
            long_run_gap,
            pace_gap,
            consistency,
            fitness,
            mountain_simulation,
            ctx.current_week,
            ctx.total_weeks,
        )

        return {
            "volume_gap": volume_gap,
            "long_run_gap": long_run_gap,
            "pace_gap": pace_gap,
            "consistency": consistency,
            "fitness_trajectory": fitness,
            "elevation_gap": elevation_gap,
            "mountain_simulation_gap": mountain_simulation,
            "top_actions": top_actions,
            "current_week": ctx.current_week,
            "total_weeks": ctx.total_weeks,
        }

    @staticmethod
    def analyze_gaps_weekly(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return per-week gap breakpoints for trend charts.

        Each entry contains the week number and % of target achieved
        for volume and long run.
        """
        ctx = _load_gap_context(plan, user_id, db, require_runs=False)
        if ctx is None:
            return None

        weekly_km, weekly_longest = _bucket_runs_by_week(
            ctx.runs,
            ctx.start_date,
            ctx.current_week,
        )

        breakpoints: list[dict] = []
        for wk_data in ctx.plan_data:
            if wk_data.get("week", 0) > ctx.current_week:
                break
            breakpoints.append(_weekly_breakpoint(wk_data, weekly_km, weekly_longest))

        return breakpoints


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
        verdict = verdict_from_thresholds(deficit_pct, _VOLUME_DEFICIT_THRESHOLDS)

    return {
        "planned_weekly_avg_km": round(planned_avg, 1),
        "actual_weekly_avg_km": round(actual_avg, 1),
        "deficit_pct": max(0, deficit_pct),
        "verdict": verdict,
    }


def _compute_elevation_gap(
    plan: TrainingPlan,
    plan_data: List[dict],
    runs: List[RunLog],
    current_week: int,
) -> Optional[Dict[str, Any]]:
    """Track vertical-gain progress against the race's elevation target.

    Only fires for trail plans (``plan.is_trail``). The weekly target is
    apportioned by week_km / total_planned_km — i.e., bigger volume weeks
    own a bigger slice of the race's vert. We compare against actual
    ``RunLog.elevation_gain_m`` summed across the same weeks.
    """
    if not getattr(plan, "is_trail", False):
        return None
    target_total = float(getattr(plan, "target_elevation_gain_m", 0) or 0)
    if target_total <= 0:
        return None

    total_planned_km = sum(w.get("total_km", 0) for w in plan_data)
    if total_planned_km <= 0:
        return None

    expected_so_far = 0.0
    for week in plan_data:
        if week.get("week", 0) > current_week:
            break
        share = week.get("total_km", 0) / total_planned_km
        expected_so_far += target_total * share

    actual_so_far = sum((r.elevation_gain_m or 0) for r in runs)

    if expected_so_far <= 0:
        verdict = "on_track"
        deficit_pct = 0.0
    else:
        deficit_pct = round((1 - actual_so_far / expected_so_far) * 100, 1)
        verdict = verdict_from_thresholds(deficit_pct, _ELEVATION_DEFICIT_THRESHOLDS)

    return {
        "race_target_m": round(target_total, 0),
        "expected_so_far_m": round(expected_so_far, 0),
        "actual_so_far_m": round(actual_so_far, 0),
        "deficit_pct": max(0.0, deficit_pct),
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
    verdict = verdict_from_thresholds(deficit_pct, _LONG_RUN_DEFICIT_THRESHOLDS)

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
    recent_runs = [r for r in runs if r.avg_pace_min_km and r.avg_pace_min_km > 0][
        -20:
    ]  # last 20 runs max

    if not recent_runs or not target_pace:
        return {
            "target_pace_min_km": target_pace,
            "current_pace_min_km": None,
            "gap_seconds": 0,
            "verdict": "insufficient_data",
        }

    current_pace = sum(r.avg_pace_min_km for r in recent_runs) / len(recent_runs)
    gap_seconds = round((current_pace - target_pace) * 60)
    verdict = verdict_from_thresholds(gap_seconds, _PACE_GAP_THRESHOLDS)

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
    from app.contexts.plan.adaptation import AdaptationService

    adaptation_service = AdaptationService()
    skipped_data = adaptation_service.detect_skipped_workouts(plan.id, db)

    perf = adaptation_service.analyze_performance(plan.id, db)
    adherence = perf.get("adherence_rate", 0)

    completion_rate = round(adherence)
    verdict = verdict_from_thresholds(
        completion_rate,
        _COMPLETION_RATE_THRESHOLDS,
        _COMPLETION_LABELS,
        higher_is_better=True,
    )

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
    mountain_simulation: Optional[Dict[str, Any]],
    current_week: int,
    total_weeks: int,
) -> List[Dict[str, Any]]:
    """Generate prioritized, actionable recommendations.

    Each action is a dict:
      {message, action_type, week_number?, payload?, label?}

    ``action_type`` is one of:
      - "extend_long_run"     → per-week override at week_number
      - "bump_volume"         → per-week override "bump" at week_number
      - "view_swap_proposals" → open type-swap proposals modal
      - "adjust_plan"         → trigger /adjust endpoint
      - None                  → informational only
    """
    actions: List[Dict[str, Any]] = []
    weeks_left = total_weeks - current_week
    next_week = min(current_week + 1, total_weeks)

    # Consistency is the foundation
    if consistency.get("verdict") in ("needs_attention", "far_behind"):
        actions.append(
            {
                "message": (
                    "Focus on completing scheduled easy runs — consistency matters "
                    "more than intensity right now"
                ),
                "action_type": None,
            }
        )

    # Volume gap
    v_deficit = volume.get("deficit_pct", 0)
    if v_deficit > 15:
        actions.append(
            {
                "message": (
                    f"Weekly volume is {v_deficit:.0f}% below plan — "
                    "add short easy runs or extend existing ones to close the gap"
                ),
                "action_type": "bump_volume",
                "week_number": next_week,
                "label": f"Bump week {next_week}",
                "payload": {"action": "bump"},
            }
        )

    # Long run gap
    lr_deficit = long_run.get("deficit_pct", 0)
    lr_target = long_run.get("target_km", 0)
    lr_actual = long_run.get("longest_actual_km", 0)
    if lr_deficit > 15 and weeks_left > 2:
        km_gap = lr_target - lr_actual
        ramp = round(km_gap / max(weeks_left - 1, 1), 1)
        actions.append(
            {
                "message": (
                    f"Increase long run by ~{ramp} km/week to close the "
                    f"{km_gap:.0f} km gap before taper"
                ),
                "action_type": "extend_long_run",
                "week_number": next_week,
                "label": f"Extend week {next_week} long run",
                "payload": {"action": "extend_long_run"},
            }
        )

    # Pace gap
    if pace.get("verdict") in ("behind", "far_behind"):
        actions.append(
            {
                "message": (
                    "Add one tempo session per week to bring pace closer to target"
                ),
                "action_type": "view_swap_proposals",
                "label": "Review swap proposals",
            }
        )

    # Fitness trajectory
    if fitness.get("on_track") is False:
        needed = fitness.get("needed_vdot_for_goal")
        current = fitness.get("current_vdot")
        if needed and current:
            actions.append(
                {
                    "message": (
                        f"VDOT gap: {current} vs {needed} needed — "
                        "include quality speed work to improve fitness"
                    ),
                    "action_type": "adjust_plan",
                    "label": "Recalibrate plan",
                }
            )

    # Mountain-from-flat simulation execution
    if mountain_simulation is not None:
        sim_score = mountain_simulation.get("score", 0)
        if sim_score < 70:
            comp = mountain_simulation.get("completion_pct", {})
            actions.append(
                {
                    "message": (
                        "Mountain simulation execution is behind target "
                        f"(uphill {comp.get('uphill', 0)}%, "
                        f"downhill {comp.get('downhill', 0)}%). "
                        "Prioritize incline/stairs blocks and eccentric downhill prep this week"
                    ),
                    "action_type": None,
                }
            )

    # Cap at 3 actions
    if not actions:
        actions.append(
            {
                "message": "You're on track — keep following the plan!",
                "action_type": None,
            }
        )

    return actions[:3]
