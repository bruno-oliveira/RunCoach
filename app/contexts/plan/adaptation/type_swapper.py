"""Workout type substitution based on coaching feedback patterns.

Detects recurring problems with specific workout types and proposes
swaps to better-suited alternatives.  Proposals are presented to the
user as suggestions; on acceptance the workout is regenerated.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan

from ._helpers import today_date
from app.contexts.plan.plan_date_utils import compute_current_week
from app.utils import to_date as _to_date
from app.contexts.plan.repositories import SQLAlchemyPlanRepository

logger = logging.getLogger(__name__)

# Minimum number of runs with the same issue before proposing a swap
_MIN_PATTERN_COUNT = 3

# Swap rules: (from_type, condition) -> (to_type, reason)
# Applied in priority order.
_SWAP_RULES = [
    {
        "from": "tempo",
        "condition": "too_hard",
        "to": "easy",
        "to_label": "progression run",
        "reason": (
            "You've found tempo runs consistently difficult. "
            "A progression run (easy start, building to tempo pace) "
            "lets you practice threshold pace with less fatigue."
        ),
    },
    {
        "from": "interval",
        "condition": "too_hard",
        "to": "fartlek",
        "to_label": "fartlek",
        "reason": (
            "Structured intervals have been tough. Fartlek gives you "
            "the same stimulus with more flexibility to adjust effort."
        ),
    },
    {
        "from": "vo2max",
        "condition": "too_hard",
        "to": "fartlek",
        "to_label": "fartlek",
        "reason": (
            "VO2max intervals have been consistently hard. "
            "Fartlek offers similar aerobic gains with more recovery flexibility."
        ),
    },
    {
        "from": "long",
        "condition": "incomplete",
        "to": "long",
        "to_label": "shorter long run",
        "reason": (
            "Long run completion has been low. Reducing the target "
            "distance helps build confidence and consistency."
        ),
    },
]


def get_swap_proposals(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[Dict[str, Any]]:
    """Analyze run history and propose workout type swaps.

    Looks at logged runs linked to this plan, detects recurring issues
    (too hard, too slow, incomplete) for specific workout types, and
    returns a list of proposed swaps for upcoming workouts.

    Returns:
        List of proposal dicts: [{week, day, from_type, to_type,
        to_label, reason, workout_id}]
    """
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    current_week = compute_current_week(start_date, today, clamp_min=1, pre_start=1)

    # Get all runs linked to this plan with quality data
    linked_runs = (
        db.query(RunLog, DailyWorkout.workout_type)
        .join(DailyWorkout, RunLog.daily_workout_id == DailyWorkout.id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.quality_label.isnot(None),
        )
        .all()
    )

    if len(linked_runs) < _MIN_PATTERN_COUNT:
        return []

    # Count quality labels per planned workout type
    type_issues: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    type_totals: Dict[str, int] = defaultdict(int)

    for run, planned_type in linked_runs:
        if not planned_type:
            continue
        type_totals[planned_type] += 1
        label = run.quality_label or ""
        if label == "Too hard":
            type_issues[planned_type]["too_hard"] += 1
        elif label == "Too easy":
            type_issues[planned_type]["too_easy"] += 1

    # Check long run completion separately (runs with distance < 70% of planned)
    long_runs = (
        db.query(RunLog, DailyWorkout)
        .join(DailyWorkout, RunLog.daily_workout_id == DailyWorkout.id)
        .filter(
            RunLog.training_plan_id == plan_id,
            DailyWorkout.workout_type == "long",
        )
        .all()
    )
    if long_runs:
        incomplete_count = sum(
            1 for run, workout in long_runs
            if (run.distance_km or 0) < (workout.distance_km or 0) * 0.70
        )
        if incomplete_count >= _MIN_PATTERN_COUNT:
            type_issues["long"]["incomplete"] = incomplete_count

    # Match issues against swap rules
    triggered_rules: List[Dict[str, Any]] = []
    for rule in _SWAP_RULES:
        from_type = rule["from"]
        condition = rule["condition"]
        count = type_issues.get(from_type, {}).get(condition, 0)
        if count >= _MIN_PATTERN_COUNT:
            triggered_rules.append({
                **rule,
                "count": count,
                "total": type_totals.get(from_type, 0),
            })

    if not triggered_rules:
        return []

    # Find the next upcoming workout matching each triggered rule
    future_workouts = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= current_week,
        )
        .all()
    )

    current_day_of_week = today.isoweekday()
    proposals = []
    used_workout_ids = set()

    for rule in triggered_rules:
        from_type = rule["from"]
        for workout, week_num in future_workouts:
            if workout.id in used_workout_ids:
                continue
            if workout.workout_type != from_type:
                continue
            # Skip workouts earlier today or in the past within current week
            if (week_num == current_week
                    and workout.day_of_week <= current_day_of_week):
                continue

            used_workout_ids.add(workout.id)
            proposals.append({
                "workout_id": workout.id,
                "week": week_num,
                "day": workout.day_of_week,
                "from_type": from_type,
                "to_type": rule["to"],
                "to_label": rule["to_label"],
                "reason": rule["reason"],
                "pattern_count": rule["count"],
                "pattern_total": rule["total"],
            })
            break  # Only propose the next one per rule

    return proposals


def apply_swap(
    workout_id: str,
    plan_id: str,
    user_id: str,
    to_type: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Apply a type swap to a specific workout.

    Updates the workout type and description.  Does not regenerate
    structured content (steps/segments) — the swap is a type and
    description change that simplifies the next session.

    Returns:
        Dict with swap details, or None if the workout was not found.
    """
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
    if not training_plan:
        return None

    workout = db.query(DailyWorkout).filter(
        DailyWorkout.id == workout_id,
    ).first()
    if not workout:
        return None

    if training_plan.training_terrain == "flat" and to_type == "hill":
        return {
            "swapped": False,
            "reason": "Flat-terrain plans do not allow hill workout substitutions.",
        }

    old_type = workout.workout_type
    workout.workout_type = to_type

    # Update description to reflect the swap
    swap_note = f"(Swapped from {old_type}: coach suggestion)"
    clean_notes = (workout.notes or "").strip()
    workout.notes = f"{clean_notes} {swap_note}".strip() if clean_notes else swap_note

    # Update plan_data JSON
    try:
        plan_data = training_plan.plan_data if training_plan.plan_data else []
        week_plan = db.query(WeeklyPlan).filter(
            WeeklyPlan.id == workout.weekly_plan_id
        ).first()
        if week_plan:
            for week in plan_data:
                if week.get("week") != week_plan.week_number:
                    continue
                for w in week.get("daily_workouts", []):
                    if w.get("day") == workout.day_of_week:
                        w["type"] = to_type
                        w["description"] = workout.notes
                        break
            training_plan.plan_data = plan_data
    except Exception as e:
        logger.warning("Failed to update plan_data JSON for type swap: %s", e)

    db.commit()

    logger.info(
        "Type swap applied: plan=%s workout=%s %s->%s",
        plan_id, workout_id, old_type, to_type,
    )

    return {
        "swapped": True,
        "workout_id": workout_id,
        "old_type": old_type,
        "new_type": to_type,
    }
