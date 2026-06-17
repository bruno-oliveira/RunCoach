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

from sqlalchemy.orm import Session

from app.models import DailyWorkout, TrainingPlan, WeeklyPlan

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


def _classify_unchanged(in_window: bool) -> Dict[str, Optional[str]]:
    """Pick a default status/reason for an unchanged workout when no
    recorder hint is available.

    Quality (tempo/interval/hill) and key workouts used to be flagged
    "protected" here, but they now adapt via the adjuster (which records an
    explicit changed/unchanged hint for each), so the fallback is simply
    "unchanged" within the decision window.
    """
    if not in_window:
        return {"status": "past", "reason": None}
    return {"status": "unchanged", "reason": None}


def _classify_workout_change(
    b: Optional[Dict[str, Any]],
    a: Optional[Dict[str, Any]],
    *,
    week: int,
    day: int,
    recorder_by_key: Dict[tuple, Dict[str, Any]],
    current_week: Optional[int],
    current_day_of_week: Optional[int],
) -> tuple[str, Optional[str], float, float]:
    """Resolve ``(status, reason, old_dist, new_dist)`` for one workout.

    Prefers the user-visible (1-decimal) distance delta over the raw delta so a
    sub-0.1 km change isn't surfaced as "Increased" on a row whose displayed
    km are identical. Falls back to the recorder hint, then to the
    in/out-of-window default.
    """
    old_dist = float(b["distance_km"]) if b else 0.0
    new_dist = float(a["distance_km"]) if a else 0.0
    display_changed = round(old_dist, 1) != round(new_dist, 1)

    rec = recorder_by_key.get((week, day))
    if display_changed:
        return "changed", (rec.get("reason") if rec else None), old_dist, new_dist
    if rec is not None:
        return rec.get("status", "unchanged"), rec.get("reason"), old_dist, new_dist

    in_window = not (
        current_week is not None
        and current_day_of_week is not None
        and week == current_week
        and day < current_day_of_week
    )
    classification = _classify_unchanged(in_window)
    return classification["status"], classification["reason"], old_dist, new_dist


def _compute_no_change_reasons(
    all_weeks: List[Dict[str, Any]],
    workouts_changed_count: int,
    multiplier: Optional[float],
    extra_no_change_reasons: Optional[List[str]],
) -> List[str]:
    """Explain why nothing changed (empty plan, all protected, neutral
    multiplier, or identical distances), plus any caller-supplied extras."""
    no_change_reasons: List[str] = []
    if not all_weeks:
        no_change_reasons.append(_reasons.NO_CHANGE_NO_REMAINING_WORKOUTS)
    elif workouts_changed_count == 0:
        if all(
            wo["status"] == "protected" for wk in all_weeks for wo in wk["workouts"]
        ):
            no_change_reasons.append(_reasons.NO_CHANGE_ALL_PROTECTED)
        elif multiplier is not None and abs(multiplier - 1.0) < 0.02:
            no_change_reasons.append(_reasons.NO_CHANGE_MULTIPLIER_NEUTRAL)
        else:
            no_change_reasons.append(_reasons.NO_CHANGE_DISTANCES_IDENTICAL)
    for extra in extra_no_change_reasons or []:
        if extra not in no_change_reasons:
            no_change_reasons.append(extra)
    return no_change_reasons


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

        status, reason, old_dist, new_dist = _classify_workout_change(
            b,
            a,
            week=week,
            day=day,
            recorder_by_key=recorder_by_key,
            current_week=current_week,
            current_day_of_week=current_day_of_week,
        )
        delta = round(new_dist - old_dist, 2)

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
        bucket["workouts"].append(
            {
                "day": _DAY_NAMES.get(day, str(day)),
                "day_num": day,
                "type": wtype or "easy",
                "old_distance_km": round(old_dist, 1),
                "new_distance_km": round(new_dist, 1),
                "delta_km": delta,
                "status": status,
                "reason": reason,
            }
        )

    all_weeks: List[Dict[str, Any]] = []
    for week in sorted(week_buckets.keys()):
        bucket = week_buckets[week]
        bucket["total_km_before"] = round(bucket["total_km_before"], 1)
        bucket["total_km_after"] = round(bucket["total_km_after"], 1)
        bucket["workouts"].sort(key=lambda w: w["day_num"])
        all_weeks.append(bucket)

    # Only show weeks that contain at least one workout the user can see
    # changed. Weeks where everything is protected/unchanged would otherwise
    # appear in the modal with a misleading delta chip.
    weeks_list = [
        wk for wk in all_weeks if any(w["status"] == "changed" for w in wk["workouts"])
    ]

    total_before = round(sum(w["total_km_before"] for w in weeks_list), 1)
    total_after = round(sum(w["total_km_after"] for w in weeks_list), 1)

    no_change_reasons = _compute_no_change_reasons(
        all_weeks, workouts_changed_count, multiplier, extra_no_change_reasons
    )

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
        "patch": _build_patch(training_plan, weeks_list),
    }
    if mode == "applied":
        plan["seen"] = False
    return plan


def _build_patch(
    training_plan: TrainingPlan,
    weeks_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Produce the flat payload the client uses to patch the DOM in place.

    Lives on every change_plan so the same payload works for applied and
    preview (preview clients ignore it; applied clients refresh from it
    without a page reload).
    """
    from app.contexts.plan.plan_template_context import _build_adaptation_state

    workout_changes: List[Dict[str, Any]] = []
    week_totals: List[Dict[str, Any]] = []
    for wk in weeks_list:
        week_totals.append({"week": wk["week"], "total_km": wk["total_km_after"]})
        for wo in wk["workouts"]:
            if wo.get("status") != "changed":
                continue
            workout_changes.append(
                {
                    "week": wk["week"],
                    "day": wo["day_num"],
                    "new_distance_km": wo["new_distance_km"],
                }
            )

    return {
        "adaptation_revision": training_plan.adaptation_revision or 0,
        "week_totals": week_totals,
        "workout_changes": workout_changes,
        "adaptation_state": _build_adaptation_state(training_plan),
    }


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
        "patch": {
            "adaptation_revision": 0,
            "week_totals": [],
            "workout_changes": [],
            "adaptation_state": {"kind": "none"},
        },
    }
    if mode == "applied":
        plan["seen"] = False
    return plan
