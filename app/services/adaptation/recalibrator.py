"""Recalibration and weekly inline suggestions."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import batch_workouts_by_week, parse_plan_data_lookups, today_date
from .performance_analyzer import analyze_performance
from .skipped_detector import detect_skipped_workouts


def recalibrate(
    plan_id: str,
    user_id: str,
    strategy: str,
    db: Session,
) -> Dict[str, Any]:
    """Recalibrate remaining plan weeks based on a user-chosen strategy.

    Strategies:
    - "time_off": Rebuild remaining weeks with a gentler ramp
    - "ahead": Bump up remaining weeks' targets
    """
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"ok": False, "error": "Plan not found"}

    start_date = _to_date(training_plan.start_date)
    if not start_date:
        return {"ok": False, "error": "Plan has no start date"}

    today = today_date()
    current_week = min(
        ((today - start_date).days // 7) + 1,
        training_plan.weeks_duration or 0,
    )

    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)

    weekly_plans = {
        wp.week_number: wp
        for wp in db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    }

    week_ids = [wp.id for wp in weekly_plans.values()]
    workouts_by_week = batch_workouts_by_week(week_ids, db)

    if strategy == "time_off":
        factor = 0.8
    elif strategy == "ahead":
        factor = 1.1
    elif strategy == "missed_week":
        return _recalibrate_missed_week(
            training_plan, plan_data, pd_week, pd_workout,
            weekly_plans, workouts_by_week, current_week, db,
        )
    elif strategy == "recovery_insertion":
        return _recalibrate_recovery_insertion(
            training_plan, plan_data, pd_week, pd_workout,
            weekly_plans, workouts_by_week, current_week, db,
        )
    else:
        return {"ok": False, "error": f"Unknown strategy: {strategy}"}

    weeks_changed = 0
    for week in weekly_plans.values():
        if week.week_number <= current_week:
            continue

        workouts = workouts_by_week.get(week.id, [])
        week_changed = False

        if strategy == "time_off":
            weeks_from_now = week.week_number - current_week
            total_remaining = training_plan.weeks_duration - current_week
            ramp = weeks_from_now / max(total_remaining, 1)
            week_factor = 0.7 + 0.3 * ramp
        else:
            week_factor = factor

        for workout in workouts:
            if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
                continue
            new_dist = round(workout.distance_km * week_factor, 1)
            if abs(new_dist - workout.distance_km) > 0.05:
                workout.distance_km = new_dist
                week_changed = True
                pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                if pd_wo:
                    pd_wo["distance"] = new_dist

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    strategy_labels = {
        "time_off": "Plan recalibrated with a gentler ramp from current fitness.",
        "ahead": "Plan targets increased based on your strong performance.",
    }
    reason = strategy_labels.get(strategy, "Plan recalibrated.")

    _record_recalibration_event(training_plan, strategy, weeks_changed, reason)
    db.commit()

    return {
        "ok": True,
        "strategy": strategy,
        "weeks_changed": weeks_changed,
        "reason": reason,
    }


def get_weekly_suggestions(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[Dict[str, Any]]:
    """Generate per-week suggestion cards for in-plan display."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    total_weeks = training_plan.weeks_duration or 0

    delta_days = (today - start_date).days
    if delta_days < 0:
        return []

    current_week = min((delta_days // 7) + 1, total_weeks)

    perf = analyze_performance(plan_id, db)
    skipped = detect_skipped_workouts(plan_id, db)
    adherence = perf.get("adherence_rate", 0)
    effort_trend = perf.get("effort_trend", "stable")
    avg_effort = perf.get("avg_effort")

    plan_data = training_plan.plan_data if training_plan.plan_data else []

    # Get recent run volumes by week
    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan_id,
        )
        .order_by(RunLog.date.asc())
        .all()
    )

    weekly_actual = defaultdict(float)
    for run in runs:
        rd = _to_date(run.date)
        if rd and start_date:
            d = (rd - start_date).days
            if d >= 0:
                wk = d // 7 + 1
                weekly_actual[wk] += run.distance_km or 0

    exceeding_count = 0
    deficit_count = 0
    for wk in range(max(1, current_week - 3), current_week + 1):
        week_data = next((w for w in plan_data if w.get("week") == wk), None)
        if not week_data:
            continue
        planned = week_data.get("total_km", 0)
        actual = weekly_actual.get(wk, 0)
        if planned > 0:
            ratio = actual / planned
            if ratio >= 1.05:
                exceeding_count += 1
            elif ratio < 0.75:
                deficit_count += 1

    multiplier = training_plan.adjustment_multiplier

    suggestions = []

    for week_data in plan_data:
        wk_num = week_data.get("week", 0)
        if wk_num <= current_week or wk_num > current_week + 3:
            continue

        week_suggestions = _build_week_suggestions(
            week_data, exceeding_count, deficit_count, multiplier,
            skipped, effort_trend, avg_effort, adherence,
        )

        if week_suggestions:
            suggestions.append({
                "week": wk_num,
                "suggestions": week_suggestions[:2],
            })

    return suggestions


def _build_week_suggestions(
    week_data: Dict,
    exceeding_count: int,
    deficit_count: int,
    multiplier,
    skipped: Dict,
    effort_trend: str,
    avg_effort,
    adherence: float,
) -> List[Dict[str, Any]]:
    """Build suggestion cards for a single upcoming week."""
    week_suggestions = []

    if exceeding_count >= 3:
        pct = (
            "+" + str(round((multiplier - 1) * 100)) + "%"
            if multiplier and multiplier > 1
            else "+8%"
        )
        week_suggestions.append({
            "type": "exceeding",
            "message": (
                f"You've exceeded targets {exceeding_count} weeks in a row "
                f"— this week's distances have been bumped {pct}"
            ),
            "action": "accept",
        })

    if deficit_count >= 2 and not any(s["type"] == "exceeding" for s in week_suggestions):
        week_suggestions.append({
            "type": "deficit",
            "message": "Volume has been below target — consider adding an extra easy run this week",
            "action": "accept",
        })

    long_wo = next(
        (wo for wo in week_data.get("daily_workouts", []) if wo.get("type") == "long"),
        None,
    )
    if long_wo and skipped.get("skipped", 0) > 2:
        km = long_wo.get("distance", 0)
        week_suggestions.append({
            "type": "long_run",
            "message": (
                f"Long run completion is behind — consider extending "
                f"Sunday's run to {round(km + 2)}km"
            ),
            "action": "accept",
        })

    if effort_trend == "increasing" and avg_effort and avg_effort > 7:
        is_recovery = week_data.get("phase", "").lower() in ("recovery", "taper")
        if is_recovery:
            week_suggestions.append({
                "type": "effort_recovery",
                "message": "Effort trending high — this recovery week is well-timed",
                "action": None,
            })
        else:
            week_suggestions.append({
                "type": "effort_high",
                "message": "Effort is trending high — consider reducing intensity this week",
                "action": "reduce",
            })

    if adherence < 60 and not any(s["type"] in ("deficit",) for s in week_suggestions):
        week_suggestions.append({
            "type": "adherence",
            "message": "Consistency is low — focus on completing the key workouts this week",
            "action": None,
        })

    return week_suggestions


# ---------------------------------------------------------------------------
# Missed-week detection and recalibration
# ---------------------------------------------------------------------------


def detect_missed_weeks(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[int]:
    """Return a list of fully missed week numbers (0 runs logged)."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    total_weeks = training_plan.weeks_duration or 0
    current_week = min(((today - start_date).days // 7) + 1, total_weeks)

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan_id,
        )
        .all()
    )

    weekly_runs: Dict[int, int] = defaultdict(int)
    for run in runs:
        rd = _to_date(run.date)
        if rd and start_date:
            d = (rd - start_date).days
            if d >= 0:
                wk = d // 7 + 1
                weekly_runs[wk] += 1

    missed = []
    for wk in range(1, current_week):
        if weekly_runs.get(wk, 0) == 0:
            missed.append(wk)
    return missed


def _recalibrate_missed_week(
    training_plan: TrainingPlan,
    plan_data: list,
    pd_week: Dict,
    pd_workout: Dict,
    weekly_plans: Dict,
    workouts_by_week: Dict,
    current_week: int,
    db: Session,
) -> Dict[str, Any]:
    """Recalibrate after a missed week.

    Strategy:
    1. Scale the next week's distances by a phase-aware ease-in factor
       (base=80%, build=75%, peak=65%, taper=80%)
    2. Shift subsequent week targets down by 1 week (repeat the progression)
    3. If a taper week exists at the end, shrink it by 1 week to preserve race date
    """
    # Phase-aware ease-in factors (improvement #6)
    _PHASE_EASE_IN = {
        "base": 0.80,
        "build": 0.75,
        "peak": 0.65,
        "taper": 0.80,
    }

    total_weeks = training_plan.weeks_duration or 0
    future_weeks = sorted(
        wk for wk in weekly_plans if wk > current_week and wk <= total_weeks
    )

    if not future_weeks:
        return {"ok": False, "error": "No future weeks to adjust"}

    # Step 1: Phase-aware ease-in for the immediate next week
    ease_in_week = future_weeks[0]
    phase = pd_week.get(ease_in_week, {}).get("phase", "build")
    ease_factor = _PHASE_EASE_IN.get(phase, 0.70)

    ease_workouts = workouts_by_week.get(
        weekly_plans[ease_in_week].id, []
    )
    for workout in ease_workouts:
        if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
            continue
        workout.distance_km = round(workout.distance_km * ease_factor, 1)
        pd_wo = pd_workout.get((ease_in_week, workout.day_of_week))
        if pd_wo:
            pd_wo["distance"] = workout.distance_km

    new_total = round(sum(w.distance_km for w in ease_workouts if w.distance_km), 1)
    if ease_in_week in weekly_plans:
        weekly_plans[ease_in_week].total_km = new_total
    if ease_in_week in pd_week:
        pd_week[ease_in_week]["total_km"] = new_total

    # Step 2: Shift remaining weeks' distances down by 1 slot
    remaining = [w for w in future_weeks if w > ease_in_week]
    if len(remaining) >= 2:
        for i in range(len(remaining) - 1):
            target_wk = remaining[i]
            source_wk = remaining[i + 1]
            target_workouts = workouts_by_week.get(weekly_plans[target_wk].id, [])
            source_workouts = workouts_by_week.get(weekly_plans[source_wk].id, [])
            source_dists = {w.day_of_week: w.distance_km for w in source_workouts}
            for wo in target_workouts:
                if wo.day_of_week in source_dists and source_dists[wo.day_of_week]:
                    wo.distance_km = source_dists[wo.day_of_week]
                    pd_wo = pd_workout.get((target_wk, wo.day_of_week))
                    if pd_wo:
                        pd_wo["distance"] = wo.distance_km
            wk_total = round(sum(w.distance_km for w in target_workouts if w.distance_km), 1)
            if target_wk in weekly_plans:
                weekly_plans[target_wk].total_km = wk_total
            if target_wk in pd_week:
                pd_week[target_wk]["total_km"] = wk_total

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    reason = (
        f"Plan recalibrated for a missed week: next week eased to {int(ease_factor*100)}% "
        f"({phase} phase), remaining weeks shifted to preserve race date."
    )
    _record_recalibration_event(training_plan, "missed_week", len(future_weeks), reason)
    db.commit()

    return {
        "ok": True,
        "strategy": "missed_week",
        "weeks_changed": len(future_weeks),
        "reason": reason,
    }


def _recalibrate_recovery_insertion(
    training_plan: TrainingPlan,
    plan_data: list,
    pd_week: Dict,
    pd_workout: Dict,
    weekly_plans: Dict,
    workouts_by_week: Dict,
    current_week: int,
    db: Session,
) -> Dict[str, Any]:
    """Insert an ad-hoc recovery week (improvement #7).

    Converts the next non-recovery week into a recovery week by scaling
    all workouts to 60% of their current distance, preserving structure
    but reducing load.
    """
    total_weeks = training_plan.weeks_duration or 0

    # Don't allow more than 2 recovery insertions per plan
    history = training_plan.adaptation_history or []
    insertion_count = sum(
        1 for e in history if e.get("type") == "recalibrate" and e.get("strategy") == "recovery_insertion"
    )
    if insertion_count >= 2:
        return {"ok": False, "error": "Maximum recovery insertions (2) already used for this plan."}

    # Find the next non-recovery week
    target_week_num = None
    for wk_num in sorted(weekly_plans.keys()):
        if wk_num <= current_week or wk_num > total_weeks:
            continue
        week_data = pd_week.get(wk_num, {})
        if not week_data.get("is_recovery", False):
            target_week_num = wk_num
            break

    if target_week_num is None:
        return {"ok": False, "error": "No eligible week found for recovery insertion."}

    # Scale all workouts in that week to 60%
    recovery_factor = 0.60
    workouts = workouts_by_week.get(weekly_plans[target_week_num].id, [])

    for workout in workouts:
        if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
            continue
        workout.distance_km = round(workout.distance_km * recovery_factor, 1)
        pd_wo = pd_workout.get((target_week_num, workout.day_of_week))
        if pd_wo:
            pd_wo["distance"] = workout.distance_km

    new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
    weekly_plans[target_week_num].total_km = new_total
    if target_week_num in pd_week:
        pd_week[target_week_num]["total_km"] = new_total
        pd_week[target_week_num]["is_recovery"] = True
        pd_week[target_week_num]["recovery_inserted"] = True

    training_plan.plan_data = plan_data
    training_plan.adaptation_alert = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    training_plan.last_adjusted_at = now
    training_plan.last_recalibrated_at = now

    reason = (
        f"Week {target_week_num} converted to recovery (60% volume). "
        "Listen to your body — easy pace only this week."
    )
    _record_recalibration_event(training_plan, "recovery_insertion", 1, reason)
    db.commit()

    return {
        "ok": True,
        "strategy": "recovery_insertion",
        "weeks_changed": 1,
        "target_week": target_week_num,
        "reason": reason,
    }


def _record_recalibration_event(
    training_plan: TrainingPlan,
    strategy: str,
    weeks_changed: int,
    reason: str,
) -> None:
    """Append a recalibration event to adaptation_history."""
    from ._helpers import today_date
    event = {
        "date": today_date().isoformat(),
        "type": "recalibrate",
        "strategy": strategy,
        "weeks_changed": weeks_changed,
        "reason": reason,
    }
    history = training_plan.adaptation_history or []
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history
