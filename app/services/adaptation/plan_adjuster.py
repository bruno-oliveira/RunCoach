"""Plan adjustment — scale future workout distances based on performance."""

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import (
    ANNOTATION_RE,
    backfill_baselines,
    batch_workouts_by_week,
    parse_plan_data_lookups,
    today_date,
)
from .run_mapper import map_runs_to_plan

logger = logging.getLogger(__name__)


def adjust_plan(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Adjust future plan weeks using full-history weighted signals.

    Uses exponential decay (half-life = 3 weeks) so all past workouts
    contribute, but recent performance weighs more heavily.  Combines
    volume adherence (50%), perceived effort (30%), and completion
    rate (20%) into a single multiplier.
    """
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"adjusted": False, "reason": "Plan not found"}
    if not training_plan.start_date:
        return {"adjusted": False, "reason": "Plan has no start date."}

    # Auto-map any unmapped runs before adjusting
    map_runs_to_plan(plan_id, user_id, db)
    backfill_baselines(training_plan, db)

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    days_elapsed = (today - start_date).days
    current_week = max(1, days_elapsed // 7 + 1)

    all_plan_runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == plan_id)
        .all()
    )

    if len(all_plan_runs) < 3:
        return {
            "adjusted": False,
            "reason": "Not enough data (need at least 3 logged runs linked to this plan)",
            "total_runs": len(all_plan_runs),
        }

    half_life_weeks = 3.0

    def _recency_weight(scheduled_date):
        weeks_ago = max(0, (today - scheduled_date).days) / 7.0
        return 2.0 ** (-weeks_ago / half_life_weeks)

    # Gather all past non-rest workouts with scheduled dates
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
        return {"adjusted": False, "reason": "No past workouts to evaluate yet."}

    signals = _compute_adjustment_signals(
        all_plan_runs, past_workouts, past_workout_ids,
        today, plan_id, db, _recency_weight,
    )
    multiplier = signals["multiplier"]

    current_day_of_week = today.isoweekday()
    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= current_week,
        )
        .all()
    )

    if not adjustable_weeks:
        return {
            "adjusted": False,
            **{k: signals[k] for k in (
                "multiplier", "volume_ratio", "avg_effort", "completion_rate",
            )},
            "total_runs": len(all_plan_runs),
            "weeks_changed": 0,
            "reason": "No remaining workouts to adjust.",
        }

    weeks_changed, any_distance_changed = _apply_adjustment_to_future_weeks(
        training_plan, adjustable_weeks, multiplier, db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
    )

    from datetime import datetime, timezone
    training_plan.adjustment_multiplier = multiplier
    training_plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    volume_ratio = signals["volume_ratio"]
    completion_rate = signals["completion_rate"]
    avg_effort = signals["avg_effort"]
    direction = "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
    reason_parts = [f"Remaining workouts {direction} (x{multiplier})."]
    reason_parts.append(
        f"Volume ratio: {round(volume_ratio, 2)}, "
        f"completion: {round(completion_rate * 100)}%."
    )
    if avg_effort is not None:
        reason_parts.append(f"Avg effort: {round(avg_effort, 1)}/10.")

    logger.info(
        "adjust_plan result: multiplier=%.2f raw=%.3f "
        "volume_ratio=%.2f effort_factor=%.2f(avg=%.1f) "
        "completion_factor=%.2f(rate=%.2f) runs=%d",
        multiplier,
        signals["raw_multiplier"],
        volume_ratio,
        signals["effort_factor"],
        avg_effort if avg_effort is not None else 0,
        signals["completion_factor"],
        completion_rate,
        len(all_plan_runs),
    )

    return {
        "adjusted": any_distance_changed,
        **signals,
        "total_runs": len(all_plan_runs),
        "weeks_changed": weeks_changed,
        "reason": " ".join(reason_parts),
    }


def _compute_adjustment_signals(
    all_plan_runs: List,
    past_workouts: List[Tuple],
    past_workout_ids: set,
    today,
    plan_id: str,
    db: Session,
    recency_weight_fn,
) -> Dict[str, Any]:
    """Compute volume, effort, and completion signals for plan adjustment."""
    # Volume adherence (weight 50%)
    planned_weighted = 0.0
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        dist = workout.baseline_distance_km or workout.distance_km or 0
        planned_weighted += dist * w

    actual_weighted = 0.0
    for run in all_plan_runs:
        run_date = _to_date(run.date) if run.date else today
        w = recency_weight_fn(run_date)
        actual_weighted += (run.distance_km or 0) * w

    volume_ratio = max(0.5, min(1.5,
        actual_weighted / planned_weighted if planned_weighted > 0 else 1.0
    ))

    # Effort signal (weight 30%)
    effort_sum = 0.0
    effort_weight_sum = 0.0
    for run in all_plan_runs:
        if run.perceived_effort is not None:
            run_date = _to_date(run.date) if run.date else today
            w = recency_weight_fn(run_date)
            effort_sum += run.perceived_effort * w
            effort_weight_sum += w

    if effort_weight_sum > 0:
        avg_effort = effort_sum / effort_weight_sum
        if avg_effort <= 3:
            effort_factor = 1.08
        elif avg_effort <= 5:
            effort_factor = 1.03
        elif avg_effort <= 7:
            effort_factor = 1.00
        elif avg_effort <= 8.5:
            effort_factor = 0.95
        else:
            effort_factor = 0.88
    else:
        effort_factor = 1.0
        avg_effort = None

    # Completion rate (weight 20%)
    completed_ids = set()
    if past_workout_ids:
        completed_rows = (
            db.query(RunLog.daily_workout_id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.in_(past_workout_ids),
            )
            .all()
        )
        completed_ids = {row[0] for row in completed_rows}

    scheduled_weighted = 0.0
    completed_weighted = 0.0
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        scheduled_weighted += w
        if workout.id in completed_ids:
            completed_weighted += w

    completion_rate = (
        completed_weighted / scheduled_weighted
        if scheduled_weighted > 0 else 0.0
    )

    if completion_rate >= 0.9:
        completion_factor = 1.05
    elif completion_rate >= 0.7:
        completion_factor = 1.00
    elif completion_rate >= 0.5:
        completion_factor = 0.95
    else:
        completion_factor = 0.90

    raw_multiplier = (
        (volume_ratio * 0.50)
        + (effort_factor * 0.30)
        + (completion_factor * 0.20)
    )
    multiplier = round(max(0.85, min(1.15, raw_multiplier)), 2)

    return {
        "multiplier": multiplier,
        "volume_ratio": round(volume_ratio, 2),
        "effort_factor": round(effort_factor, 2),
        "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
        "completion_rate": round(completion_rate, 2),
        "completion_factor": round(completion_factor, 2),
        "raw_multiplier": round(raw_multiplier, 3),
    }


def _apply_adjustment_to_future_weeks(
    training_plan: TrainingPlan,
    future_weeks: List,
    multiplier: float,
    db: Session,
    *,
    current_week: int | None = None,
    current_day_of_week: int | None = None,
) -> Tuple[int, bool]:
    """Apply the adjustment multiplier to future weeks.

    Returns (weeks_changed, any_distance_changed).
    """
    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    workouts_by_week = batch_workouts_by_week(
        [week.id for week in future_weeks], db
    )

    weeks_changed = 0
    any_distance_changed = False

    for week in future_weeks:
        workouts = workouts_by_week.get(week.id, [])
        week_changed = False

        for workout in workouts:
            if (
                workout.workout_type == "rest"
                or not workout.distance_km
                or workout.distance_km <= 0
            ):
                continue

            if (
                current_week is not None
                and current_day_of_week is not None
                and week.week_number == current_week
                and workout.day_of_week < current_day_of_week
            ):
                continue

            base_distance = workout.baseline_distance_km or workout.distance_km

            if workout.workout_type == "long" and multiplier < 1.0:
                new_distance = round(base_distance, 1)
            elif workout.workout_type in ("interval", "tempo", "hill"):
                quality_mult = 1.0 + (multiplier - 1.0) * 0.5
                new_distance = max(1.0, round(base_distance * quality_mult, 1))
            else:
                new_distance = max(1.0, round(base_distance * multiplier, 1))
            old_distance = workout.distance_km

            if new_distance == old_distance:
                continue

            workout.distance_km = new_distance
            any_distance_changed = True
            week_changed = True

            is_protected = workout.workout_type == "long" and multiplier < 1.0

            clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
            if multiplier != 1.0 and not is_protected:
                adjust_note = f"(Adjusted: x{multiplier})"
                workout.notes = (
                    f"{clean_notes} {adjust_note}".strip()
                    if clean_notes
                    else adjust_note
                )
            else:
                workout.notes = clean_notes or None

            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = new_distance
                pd_clean = ANNOTATION_RE.sub(
                    "", pd_wo.get("notes", pd_wo.get("description", ""))
                ).strip()
                if multiplier != 1.0 and not is_protected:
                    adjust_note = f"(Adjusted: x{multiplier})"
                    pd_wo["notes"] = (
                        f"{pd_clean} {adjust_note}".strip()
                        if pd_clean
                        else adjust_note
                    )
                else:
                    pd_wo["notes"] = pd_clean

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.plan_data = json.dumps(plan_data)
    return weeks_changed, any_distance_changed


def reset_adjustment(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Reset plan to original baseline distances, removing any adjustment."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"reset": False, "reason": "Plan not found"}

    has_adjustment = training_plan.adjustment_multiplier is not None
    has_recalibration = training_plan.last_recalibrated_at is not None

    if not has_adjustment and not has_recalibration:
        return {"reset": False, "reason": "Plan has no active adjustment."}

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    all_weeks = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    )

    workouts_by_week_map = batch_workouts_by_week(
        [week.id for week in all_weeks], db
    )

    weeks_changed = 0
    for week in all_weeks:
        workouts = workouts_by_week_map.get(week.id, [])
        week_changed = False

        for workout in workouts:
            if not workout.baseline_distance_km:
                clean = ANNOTATION_RE.sub("", workout.notes or "").strip()
                if clean != (workout.notes or "").strip():
                    workout.notes = clean or None
                continue

            if workout.distance_km != workout.baseline_distance_km:
                workout.distance_km = workout.baseline_distance_km
                week_changed = True

            clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
            workout.notes = clean_notes or None

            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = workout.baseline_distance_km
                pd_clean = ANNOTATION_RE.sub(
                    "", pd_wo.get("notes", pd_wo.get("description", "")),
                ).strip()
                pd_wo["notes"] = pd_clean

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.adjustment_multiplier = None
    training_plan.last_recalibrated_at = None
    training_plan.plan_data = json.dumps(plan_data)
    db.commit()

    return {
        "reset": True,
        "weeks_changed": weeks_changed,
        "reason": "Plan restored to original distances.",
    }
