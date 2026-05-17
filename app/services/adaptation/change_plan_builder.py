"""Build the ChangePlan payload returned by preview / apply endpoints.

The ChangePlan is the user-facing summary of an adaptation action. It is
populated by snapshotting workouts before and after the mutation, then
merging in protection / unchanged reasons captured by week_adjuster's
optional recorder.

Shape: see plan file or change_plan_modal.html.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from sqlalchemy.orm import Session

from . import change_reasons as _reasons


_DAY_NAMES = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def snapshot_workouts(
    training_plan: TrainingPlan,
    db: Session,
    *,
    week_numbers: Optional[Iterable[int]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Snapshot relevant workouts keyed by daily_workout id.

    If `week_numbers` is provided, restricts to those weeks; otherwise
    snapshots every workout on the plan. Snapshots all relevant fields
    needed to compute distance deltas later.
    """
    q = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == training_plan.id)
    )
    if week_numbers is not None:
        q = q.filter(WeeklyPlan.week_number.in_(list(week_numbers)))
    snap: Dict[str, Dict[str, Any]] = {}
    for workout, week_number in q.all():
        snap[workout.id] = {
            "id": workout.id,
            "week": week_number,
            "day": workout.day_of_week,
            "type": workout.workout_type,
            "distance_km": float(workout.distance_km) if workout.distance_km else 0.0,
            "baseline_distance_km": (
                float(workout.baseline_distance_km)
                if workout.baseline_distance_km
                else None
            ),
            "key_workout_id": workout.key_workout_id,
        }
    return snap


def _classify_unchanged(
    workout_type: Optional[str],
    has_key_workout_id: bool,
    in_window: bool,
) -> Dict[str, Optional[str]]:
    """Pick a default status/reason for an unchanged workout when no
    recorder hint is available."""
    if not in_window:
        return {"status": "past", "reason": None}
    if has_key_workout_id or workout_type in ("tempo", "interval", "hill"):
        return {
            "status": "protected",
            "reason": _reasons.protected_reason_for_workout(
                workout_type, has_key_workout_id
            ),
        }
    return {"status": "unchanged", "reason": None}


def build_change_plan(
    *,
    action: str,
    mode: str,
    training_plan: TrainingPlan,
    before: Dict[str, Dict[str, Any]],
    after: Dict[str, Dict[str, Any]],
    recorder: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, Any]] = None,
    multiplier: Optional[float] = None,
    vdot_change: Optional[Dict[str, Any]] = None,
    extra_no_change_reasons: Optional[List[str]] = None,
    headline_reason: Optional[str] = None,
    current_week: Optional[int] = None,
    current_day_of_week: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the ChangePlan dict.

    `before` and `after` are snapshots keyed by workout id (use
    snapshot_workouts). `recorder` is the optional per-workout hint list
    week_adjuster produces — used to surface protected / quality-half-
    scaled / long-run-floor reasons.
    """
    recorder_by_key: Dict[tuple, Dict[str, Any]] = {}
    for entry in recorder or []:
        recorder_by_key[(entry["week"], entry["day"])] = entry

    week_buckets: Dict[int, Dict[str, Any]] = {}
    workouts_changed_count = 0
    workouts_protected_count = 0

    all_ids = set(before.keys()) | set(after.keys())
    for wid in all_ids:
        b = before.get(wid)
        a = after.get(wid)
        ref = a or b
        if ref is None:
            continue
        week = ref["week"]
        day = ref["day"]
        wtype = ref["type"]

        old_dist = float(b["distance_km"]) if b else 0.0
        new_dist = float(a["distance_km"]) if a else 0.0
        delta = round(new_dist - old_dist, 2)
        # Status must reflect what the user actually sees: distances are
        # rounded to 1 decimal in the UI, so a sub-0.1 raw delta would
        # surface as "Increased" on a row whose old/new km display the
        # same value. Compare the rounded values instead.
        old_display = round(old_dist, 1)
        new_display = round(new_dist, 1)
        display_changed = old_display != new_display

        in_window = True
        if (
            current_week is not None
            and current_day_of_week is not None
            and week == current_week
            and day < current_day_of_week
        ):
            in_window = False

        rec = recorder_by_key.get((week, day))
        if display_changed:
            status = "changed"
            reason = rec.get("reason") if rec else None
        elif rec is not None:
            status = rec.get("status", "unchanged")
            reason = rec.get("reason")
        else:
            classification = _classify_unchanged(
                wtype,
                bool(ref.get("key_workout_id")),
                in_window,
            )
            status = classification["status"]
            reason = classification["reason"]

        if status == "changed":
            workouts_changed_count += 1
        elif status == "protected":
            workouts_protected_count += 1

        # Skip "past" workouts entirely — they're not in the user's
        # decision window and we don't want them cluttering the modal.
        if status == "past":
            continue

        bucket = week_buckets.setdefault(
            week,
            {
                "week": week,
                "total_km_before": 0.0,
                "total_km_after": 0.0,
                "workouts": [],
            },
        )
        bucket["total_km_before"] += old_dist
        bucket["total_km_after"] += new_dist
        bucket["workouts"].append({
            "day": _DAY_NAMES.get(day, str(day)),
            "day_num": day,
            "type": wtype or "easy",
            "old_distance_km": round(old_dist, 1),
            "new_distance_km": round(new_dist, 1),
            "delta_km": delta,
            "status": status,
            "reason": reason,
        })

    weeks_list: List[Dict[str, Any]] = []
    for week in sorted(week_buckets.keys()):
        bucket = week_buckets[week]
        bucket["total_km_before"] = round(bucket["total_km_before"], 1)
        bucket["total_km_after"] = round(bucket["total_km_after"], 1)
        bucket["workouts"].sort(key=lambda w: w["day_num"])
        weeks_list.append(bucket)

    total_before = round(sum(w["total_km_before"] for w in weeks_list), 1)
    total_after = round(sum(w["total_km_after"] for w in weeks_list), 1)

    no_change_reasons: List[str] = []
    if not weeks_list:
        no_change_reasons.append(_reasons.NO_CHANGE_NO_REMAINING_WORKOUTS)
    elif workouts_changed_count == 0:
        if all(
            wo["status"] == "protected"
            for wk in weeks_list
            for wo in wk["workouts"]
        ):
            no_change_reasons.append(_reasons.NO_CHANGE_ALL_PROTECTED)
        elif multiplier is not None and abs(multiplier - 1.0) < 0.02:
            no_change_reasons.append(_reasons.NO_CHANGE_MULTIPLIER_NEUTRAL)
        else:
            no_change_reasons.append(_reasons.NO_CHANGE_DISTANCES_IDENTICAL)
    for extra in extra_no_change_reasons or []:
        if extra not in no_change_reasons:
            no_change_reasons.append(extra)

    did_change = workouts_changed_count > 0 or bool(vdot_change)
    if mode == "preview":
        would_change = did_change
        did_change_field = False
    else:
        would_change = did_change
        did_change_field = did_change

    plan = {
        "action": action,
        "mode": mode,
        "would_change": would_change,
        "did_change": did_change_field,
        "computed_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "summary": {
            "multiplier": multiplier,
            "vdot_change": vdot_change,
            "total_km_before": total_before,
            "total_km_after": total_after,
            "total_km_delta": round(total_after - total_before, 1),
            "weeks_affected": [w["week"] for w in weeks_list],
            "workouts_changed_count": workouts_changed_count,
            "workouts_protected_count": workouts_protected_count,
        },
        "weeks": weeks_list,
        "signals": signals or {},
        "reason": headline_reason,
        "no_change_reasons": no_change_reasons if not did_change else [],
    }
    if mode == "applied":
        plan["seen"] = False
    return plan


def empty_change_plan(
    *,
    action: str,
    mode: str,
    headline_reason: str,
    no_change_reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a ChangePlan for the early-exit case where the action
    cannot proceed (e.g., insufficient data, plan not started)."""
    plan = {
        "action": action,
        "mode": mode,
        "would_change": False,
        "did_change": False,
        "computed_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "summary": {
            "multiplier": None,
            "vdot_change": None,
            "total_km_before": 0.0,
            "total_km_after": 0.0,
            "total_km_delta": 0.0,
            "weeks_affected": [],
            "workouts_changed_count": 0,
            "workouts_protected_count": 0,
        },
        "weeks": [],
        "signals": {},
        "reason": headline_reason,
        "no_change_reasons": no_change_reasons or [headline_reason],
    }
    if mode == "applied":
        plan["seen"] = False
    return plan
