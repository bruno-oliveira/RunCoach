"""Plan adjustment — scale future workout distances based on performance."""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.plan_calendar import compute_current_week
from app.models import (
    DailyWorkout,
    ReadinessLog,
    RunFeedback,
    RunLog,
    TrainingPlan,
    WeeklyPlan,
)
from app.utils import persist_json
from app.utils import to_date as _to_date

from . import change_reasons as _reasons
from ._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    batch_workouts_by_week,
    is_current_week_in_progress,
    parse_plan_data_lookups,
    today_date,
)
from .adjustment_results import (
    record_adaptation_event as _record_adaptation_event,
)
from .change_plan_builder import (
    build_change_plan,
    empty_change_plan,
    snapshot_workouts,
)
from .fitness_signals import FitnessSignalsProvider, default_provider
from .run_mapper import map_runs_to_plan
from .signal_computer import compute_adjustment_signals
from .tuning import RECENCY_HALF_LIFE_WEEKS

logger = logging.getLogger(__name__)


def gather_signals(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    run_map: bool = True,
    fitness_provider: Optional[FitnessSignalsProvider] = None,
) -> Optional[Dict[str, Any]]:
    """Gather runs, workouts, and compute adjustment signals.

    Returns None if insufficient data, otherwise a dict with signals,
    current_week, all_plan_runs, adjustable_weeks, and training_plan.

    ``fitness_provider`` injects VDOT-trend, training-load, and
    mountain-simulation callables. Defaults to the runner-context
    implementations via ``default_provider`` — tests override to avoid
    pulling in the runner context.
    """
    provider = fitness_provider or default_provider()
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return None

    if run_map:
        map_runs_to_plan(plan_id, user_id, db)
    backfill_baselines(training_plan, db)

    hr_zones = None
    if training_plan.hr_zones_data:
        try:
            hr_zones = training_plan.hr_zones_data.get("zones")
        except (AttributeError, TypeError):
            pass

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    current_week = compute_current_week(start_date, today, clamp_min=1, pre_start=1)

    all_plan_runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == plan_id)
        .order_by(RunLog.date.asc())
        .all()
    )

    run_ids = [run.id for run in all_plan_runs]
    run_feedback_list = (
        (db.query(RunFeedback).filter(RunFeedback.run_log_id.in_(run_ids)).all())
        if run_ids
        else []
    )

    if len(all_plan_runs) < 3:
        return None

    half_life_weeks = RECENCY_HALF_LIFE_WEEKS

    def _recency_weight(scheduled_date):
        weeks_ago = max(0, (today - scheduled_date).days) / 7.0
        return 2.0 ** (-weeks_ago / half_life_weeks)

    all_workouts_with_week = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            DailyWorkout.workout_type != "rest",
        )
        .all()
    )

    past_workouts: List[Tuple] = []
    past_workout_ids: set = set()
    for workout, week_number in all_workouts_with_week:
        scheduled_date = start_date + timedelta(
            weeks=(week_number - 1),
            days=(workout.day_of_week - 1),
        )
        if scheduled_date <= today:
            past_workouts.append((workout, scheduled_date))
            past_workout_ids.add(workout.id)

    if not past_workouts:
        return None

    vdot_trend = "stable"
    try:
        vdot_history = provider.get_vdot_history(user_id, weeks=8, db=db)
        vdot_trend = provider.calculate_vdot_trend(vdot_history)
    except Exception as e:
        logger.warning("VDOT trend lookup failed (non-fatal): %s", e)

    training_load = None
    try:
        training_load = provider.get_training_load(user_id, db, lookback_days=42)
    except Exception as e:
        logger.warning("Training load lookup failed (non-fatal): %s", e)

    readiness_logs = _recent_readiness_logs(user_id, today, db)

    signals = compute_adjustment_signals(
        all_plan_runs,
        past_workouts,
        past_workout_ids,
        today,
        plan_id,
        db,
        _recency_weight,
        current_phase=_get_current_phase(training_plan, current_week),
        adaptation_history=training_plan.adaptation_history,
        hr_zones=hr_zones,
        run_feedback_list=run_feedback_list,
        vdot_trend=vdot_trend,
        training_load=training_load,
        readiness_logs=readiness_logs,
        mountain_simulation=provider.score_mountain_simulation(
            training_plan.plan_data or [],
            all_plan_runs,
            start_date,
            current_week,
            is_trail=getattr(training_plan, "is_trail", False),
            training_terrain=getattr(training_plan, "training_terrain", None),
            target_elevation_gain_m=getattr(
                training_plan, "target_elevation_gain_m", None
            ),
            plan_id=training_plan.id,
        ),
    )

    current_day_of_week = today.isoweekday()
    in_progress = is_current_week_in_progress(
        plan_id,
        start_date,
        current_week,
        current_day_of_week,
        db,
    )
    first_adjustable_week = current_week + 1 if in_progress else current_week
    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= first_adjustable_week,
        )
        .all()
    )

    return {
        "training_plan": training_plan,
        "signals": signals,
        "all_plan_runs": all_plan_runs,
        "current_week": current_week,
        "current_day_of_week": current_day_of_week,
        "current_week_in_progress": in_progress,
        "first_adjustable_week": first_adjustable_week,
        "adjustable_weeks": adjustable_weeks,
    }


# How far back the readiness signal looks for self-reported check-ins. Matches
# the recency horizon the other signals weight over, so a stale week-old morning
# doesn't keep dragging the plan.
_READINESS_LOOKBACK_DAYS = 21


def _recent_readiness_logs(user_id: str, today, db: Session) -> List[ReadinessLog]:
    """Recent scored readiness check-ins feeding the adaptation readiness signal.

    Only logs with a derived ``score`` count — a check-in with no scorable input
    contributes nothing. Returns [] when the user has never checked in, in which
    case the signal falls back to its objective TSB proxy.
    """
    since = today - timedelta(days=_READINESS_LOOKBACK_DAYS)
    return (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == user_id,
            ReadinessLog.date >= since,
            ReadinessLog.score.isnot(None),
        )
        .order_by(ReadinessLog.date.desc())
        .all()
    )


def preview_adjust_signals(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Read-only: the full adaptation signal breakdown, without any writes.

    Unlike ``preview_adjust_plan`` (which mutates then rolls back), this
    calls ``gather_signals`` with ``run_map=False`` so no run→workout
    mapping is committed — safe to call on a GET request. Returns the
    complete ``compute_adjustment_signals`` dict (every factor, weight,
    TSB/form, trends) plus ``current_week`` and ``adjustable_week_count``,
    or ``None`` when there is insufficient data (fewer than 3 linked runs,
    no start date, or no past workouts to evaluate).
    """
    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None
    signals = dict(gathered["signals"])
    signals["current_week"] = gathered["current_week"]
    signals["adjustable_week_count"] = len(gathered["adjustable_weeks"])
    return signals


def _get_current_phase(training_plan: TrainingPlan, current_week: int) -> str:
    plan_data = training_plan.plan_data or []
    for week in plan_data:
        if week.get("week") == current_week:
            return week.get("phase", "build")
    return "build"


def reset_adjustment(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Reset plan to original baseline distances, removing any adjustment."""
    return _run_reset(plan_id, user_id, db, mode="applied")


def preview_reset_adjustment(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Preview the reset action without persisting."""
    try:
        result = _run_reset(plan_id, user_id, db, mode="preview")
    finally:
        db.rollback()
        db.expire_all()
    return result["change_plan"] if "change_plan" in result else result


def _strip_annotations(text: Optional[str]) -> str:
    """Remove adaptation annotations from a notes/description string."""
    return ANNOTATION_RE.sub("", text or "").strip()


def _run_reset(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    mode: str,
) -> Dict[str, Any]:
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan:
        cp = empty_change_plan(
            action="reset",
            mode=mode,
            headline_reason="Plan not found.",
        )
        return {"reset": False, "reason": "Plan not found", "change_plan": cp}

    has_adjustment = training_plan.adjustment_multiplier is not None
    has_recalibration = training_plan.last_recalibrated_at is not None

    if not has_adjustment and not has_recalibration:
        cp = empty_change_plan(
            action="reset",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_NO_ACTIVE_ADJUSTMENT,
        )
        return {
            "reset": False,
            "reason": "Plan has no active adjustment.",
            "change_plan": cp,
        }

    # Reset restores distance = baseline_distance_km, so a baseline frozen to
    # an already-adjusted value would restore the inflated distance. Normalize
    # first (recovers true baselines, strips stale notes) so reset returns the
    # genuine originals. Reset does not go through gather_signals, so this is
    # the only place the normalize pass runs for this flow.
    backfill_baselines(training_plan, db)

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    all_weeks = (
        db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan_id).all()
    )

    workouts_by_week_map = batch_workouts_by_week([week.id for week in all_weeks], db)

    before = snapshot_workouts(training_plan, db)

    weeks_changed = 0
    for week in all_weeks:
        workouts = workouts_by_week_map.get(week.id, [])
        week_changed = False

        for workout in workouts:
            if not workout.baseline_distance_km:
                clean = _strip_annotations(workout.notes)
                if clean != (workout.notes or "").strip():
                    workout.notes = clean or None
                continue

            if workout.distance_km != workout.baseline_distance_km:
                workout.distance_km = workout.baseline_distance_km
                week_changed = True

            workout.notes = _strip_annotations(workout.notes) or None

            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = workout.baseline_distance_km
                pd_wo["notes"] = _strip_annotations(
                    pd_wo.get("notes", pd_wo.get("description", ""))
                )

        if week_changed:
            weeks_changed += 1
            new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.plan_data = plan_data
    persist_json(training_plan, "plan_data")

    after = snapshot_workouts(training_plan, db)

    change_plan = build_change_plan(
        action="reset",
        mode=mode,
        training_plan=training_plan,
        before=before,
        after=after,
        recorder=None,
        signals={},
        multiplier=None,
        vdot_change=None,
        headline_reason="Plan restored to original baseline distances.",
    )

    if mode == "applied":
        training_plan.adjustment_multiplier = None
        training_plan.last_recalibrated_at = None
        training_plan.last_change_plan = change_plan
        _record_adaptation_event(
            training_plan,
            {
                "type": "reset",
                "weeks_changed": weeks_changed,
                "reason": "Plan restored to original baseline distances.",
            },
        )
        db.commit()

    return {
        "reset": True,
        "weeks_changed": weeks_changed,
        "reason": "Plan restored to original distances.",
        "change_plan": change_plan,
    }
