"""Coach summary — cross-context assembler for the analytics "Coach" hub.

Orchestrates the plan adaptation engine, runner fitness services, and
coaching feedback into the read-only payloads the Coach tab renders:

- ``build_coach_summary``  — the 6-signal breakdown ("what your coach sees"),
  current multiplier/direction, form (TSB/CTL/ATL), and race readiness.
- ``build_adaptation_history`` — the persisted adaptation timeline, normalized.
- ``build_coach_patterns`` — recency-weighted pace patterns + week pulse.

All functions are read-only: they never commit. ``preview_adjust_signals``
gathers signals with ``run_map=False`` so no run→workout mapping is written
on a GET request.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.runner.enrichment.week_pulse_generator import get_week_pulse
from app.contexts.runner.fitness.coaching_data import fetch_pattern_candidates
from app.contexts.runner.fitness.readiness_service import ReadinessService
from app.core.coaching.pattern_analyzer import pattern_feedback
from app.core.time_utils import local_today
from app.core.training.plan_calendar import compute_current_week
from app.models import RunLog, TrainingPlan
from app.utils import to_date as _to_date

# Day-of-week labels — plans are 1-indexed Mon..Sun (workout.day) and start on
# the plan's start_date (conventionally a Monday).
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Dead-zone around 1.0 below which an adjustment is treated as "hold" — mirrors
# the ±2% hysteresis the recommendation evaluator uses.
_HOLD_BAND = 0.02

_EVENT_LABELS = {
    "adjust": "Plan adjusted",
    "reset": "Reset to baseline",
    "recalibrate": "Recalibrated",
    "auto_accept": "Auto-applied recommendation",
    "auto_dismiss": "Recommendation dismissed",
}

_PATTERN_TYPES = ("easy", "recovery", "long", "tempo", "interval")


def build_coach_summary(
    plan: TrainingPlan, user_id: str, db: Session
) -> Dict[str, Any]:
    """The consolidated "what your coach sees" payload for a plan."""
    signals = AdaptationService().preview_adjust_signals(plan.id, user_id, db)
    if signals is None:
        return {
            "available": False,
            "reason": "Log 3 runs linked to this plan and I'll start reading your training — pace discipline, fatigue, and where you're gaining.",
        }

    weights = signals.get("phase_weights", {})
    signals_block = {
        "volume": {
            "factor": signals.get("volume_ratio"),
            "weight": weights.get("volume", 0.0),
            "has_data": True,
        },
        "effort": {
            "factor": signals.get("effort_factor"),
            "weight": weights.get("effort", 0.0),
            "has_data": signals.get("avg_effort") is not None,
        },
        "completion": {
            "factor": signals.get("completion_factor"),
            "weight": weights.get("completion", 0.0),
            "has_data": True,
        },
        "hr_zone": {
            "factor": signals.get("hr_zone_factor"),
            "weight": weights.get("hr_zone", 0.0),
            "has_data": signals.get("hr_zone_adherence") is not None,
        },
        "feedback": {
            "factor": signals.get("feedback_factor"),
            "weight": weights.get("feedback", 0.0),
            "has_data": True,
        },
        "readiness": {
            "factor": signals.get("readiness_factor"),
            "weight": weights.get("readiness", 0.0),
            "has_data": (signals.get("readiness_log_count") or 0) >= 3,
        },
    }

    multiplier = signals.get("multiplier", 1.0)
    direction = _direction(multiplier)

    readiness: Optional[Dict[str, Any]] = None
    try:
        readiness = ReadinessService.compute_readiness(plan, user_id, db)
    except Exception:  # readiness is best-effort; never block the summary
        readiness = None

    return {
        "available": True,
        "plan_id": plan.id,
        "multiplier": multiplier,
        "direction": direction,
        "would_change": direction != "hold",
        "overreach_detected": signals.get("overreach_detected", False),
        "current_phase": signals.get("current_phase"),
        "current_week": signals.get("current_week"),
        "signals": signals_block,
        "per_type_ratios": signals.get("per_type_ratios", {}),
        "effort_trend": signals.get("effort_trend"),
        "quality_drift": signals.get("quality_drift"),
        "hr_zone_trend": signals.get("hr_zone_trend"),
        "vdot_trend": signals.get("vdot_trend"),
        "form": {
            "tsb": signals.get("tsb"),
            "ctl": signals.get("ctl"),
            "atl": signals.get("atl"),
            "tsb_form": signals.get("tsb_form"),
        },
        "readiness": readiness,
        "headline_reason": _build_headline(signals, direction, multiplier),
    }


def build_adaptation_history(plan: TrainingPlan) -> Dict[str, Any]:
    """Normalize the persisted ``adaptation_history`` into display rows.

    Events are appended chronologically (capped at 20 by the writers); we
    return them newest-first with a uniform shape and defensive ``.get``
    since the writers store heterogeneous fields.
    """
    raw = plan.adaptation_history or []
    events = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        etype = entry.get("type", "adjust")
        multiplier = entry.get("multiplier")
        pct = (
            round((multiplier - 1.0) * 100)
            if isinstance(multiplier, (int, float))
            else None
        )
        events.append(
            {
                "date": entry.get("date"),
                "type": etype,
                "label": _EVENT_LABELS.get(etype, etype.replace("_", " ").title()),
                "direction": entry.get("direction"),
                "multiplier": multiplier,
                "pct": pct,
                "phase": entry.get("phase"),
                "overreach": entry.get("overreach"),
                "weeks_changed": entry.get("weeks_changed"),
                "week_evaluated": entry.get("week_evaluated"),
                "reason": entry.get("reason"),
            }
        )
    events.reverse()
    return {"available": True, "events": events}


def build_signal_history(plan: TrainingPlan) -> Dict[str, Any]:
    """Per-event signal snapshots for the Signals-tab trend sparklines.

    Reads the ``signals_snapshot`` frozen onto each applied "adjust" event by
    ``plan_adjuster._build_signal_snapshot``. Returned oldest-first so the
    client can plot each signal's factor as a left-to-right time series.
    Older events that predate snapshotting are tolerated (skipped).
    """
    raw = plan.adaptation_history or []
    snapshots: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        snap = entry.get("signals_snapshot")
        if not isinstance(snap, dict):
            continue
        snapshots.append(
            {
                "date": entry.get("date"),
                "direction": entry.get("direction"),
                "multiplier": snap.get("multiplier", entry.get("multiplier")),
                "phase": snap.get("phase", entry.get("phase")),
                "signals": snap.get("signals", {}),
                "form": snap.get("form", {}),
            }
        )
    return {"available": len(snapshots) > 0, "snapshots": snapshots}


def _bucket_runs_by_day(
    runs: List[RunLog], week_start: date
) -> Dict[int, List[RunLog]]:
    """Group runs by 1-based day-of-week offset within the week."""
    by_day: Dict[int, List[RunLog]] = {}
    for run in runs:
        rd = run.date.date() if isinstance(run.date, datetime) else run.date
        if rd is None:
            continue
        offset = (rd - week_start).days
        if 0 <= offset <= 6:
            by_day.setdefault(offset + 1, []).append(run)
    return by_day


def _day_status(day_date: date, today: date, *, is_rest: bool, has_runs: bool) -> str:
    """Derive a 7-day-strip day status from a pure calendar comparison."""
    if day_date == today:
        return "today"
    if day_date < today:
        return "done" if has_runs else ("rest" if is_rest else "missed")
    return "rest" if is_rest else "upcoming"


def build_today(plan: TrainingPlan, user_id: str, db: Session) -> Dict[str, Any]:
    """Current-week execution snapshot for the Coach Hub "Today" tab.

    Returns today's planned workout (if the plan is mid-flight), a 7-day
    execution strip with per-day completion status, and the week's planned vs
    actual volume. Day status is derived from pure calendar comparison so it
    behaves correctly whether the plan is upcoming, in-progress, or finished.
    """
    start = _to_date(plan.start_date) if plan.start_date else None
    plan_data = plan.plan_data or []
    if not start or not plan_data:
        return {
            "available": False,
            "reason": "Pick a plan with a start date to see today's session.",
        }

    today = local_today()
    total_weeks = len(plan_data)
    current_week = compute_current_week(
        start, today, clamp_min=1, total_weeks=total_weeks, pre_start=1
    )
    week_data = next(
        (w for w in plan_data if w.get("week") == current_week),
        plan_data[min(current_week, total_weeks) - 1] if plan_data else None,
    )
    if not week_data:
        return {"available": False, "reason": "No workouts scheduled for this week."}

    week_start = start + timedelta(weeks=current_week - 1)

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan.id,
            RunLog.date >= week_start,
            RunLog.date < week_start + timedelta(days=7),
        )
        .all()
    )
    runs_by_day = _bucket_runs_by_day(runs, week_start)

    workouts_by_day = {
        w.get("day"): w for w in week_data.get("daily_workouts", []) if w.get("day")
    }

    days: List[Dict[str, Any]] = []
    planned_total = 0.0
    actual_total = 0.0
    for d in range(1, 8):
        w = workouts_by_day.get(d) or {}
        wtype = w.get("type", "rest")
        planned_km = round(w.get("distance", 0) or 0, 1)
        day_runs = runs_by_day.get(d, [])
        actual_km = round(sum(r.distance_km or 0 for r in day_runs), 1)
        is_rest = wtype in ("rest", "recovery") and planned_km == 0
        day_date = week_start + timedelta(days=d - 1)

        status = _day_status(day_date, today, is_rest=is_rest, has_runs=bool(day_runs))

        if not is_rest:
            planned_total += planned_km
        actual_total += actual_km

        days.append(
            {
                "day": d,
                "day_name": _DAY_NAMES[d - 1],
                "date": day_date.isoformat(),
                "workout_type": wtype,
                "planned_km": planned_km,
                "actual_km": actual_km,
                "status": status,
                "is_today": day_date == today,
                "logged": bool(day_runs),
            }
        )

    today_offset = (today - week_start).days
    today_block: Optional[Dict[str, Any]] = None
    if 0 <= today_offset <= 6:
        tw = workouts_by_day.get(today_offset + 1)
        if tw:
            today_block = {
                "day_name": _DAY_NAMES[today_offset],
                "date": today.isoformat(),
                "workout_type": tw.get("type"),
                "distance_km": round(tw.get("distance", 0) or 0, 1),
                "description": tw.get("description"),
                "hr_zone_target": tw.get("hr_zone_target"),
                "hr_zone_label": tw.get("hr_zone_label"),
                "duration_min": tw.get("duration_min"),
                "logged": bool(runs_by_day.get(today_offset + 1)),
            }

    pct = round(actual_total / planned_total * 100) if planned_total > 0 else None
    return {
        "available": True,
        "current_week": current_week,
        "total_weeks": total_weeks,
        "phase": week_data.get("phase"),
        "today": today_block,
        "week": days,
        "week_planned_km": round(planned_total, 1),
        "week_actual_km": round(actual_total, 1),
        "week_pct": pct,
    }


def build_training_age(user_id: str, db: Session) -> Dict[str, Any]:
    """Training age + consistency streaks aggregated from all logged runs."""
    runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == user_id, RunLog.date.isnot(None))
        .order_by(RunLog.date.asc())
        .all()
    )
    if not runs:
        return {"available": False}

    def _monday(d: date) -> date:
        return d - timedelta(days=d.weekday())

    dates = [(r.date.date() if isinstance(r.date, datetime) else r.date) for r in runs]
    today = local_today()
    first = dates[0]
    first_monday = _monday(first)
    this_monday = _monday(today)
    weeks_since = (this_monday - first_monday).days // 7 + 1

    active_mondays = sorted({_monday(d) for d in dates})

    longest_streak = 1
    run_len = 1
    for i in range(1, len(active_mondays)):
        if (active_mondays[i] - active_mondays[i - 1]).days == 7:
            run_len += 1
        else:
            run_len = 1
        longest_streak = max(longest_streak, run_len)

    current_streak = 0
    if active_mondays and (this_monday - active_mondays[-1]).days <= 7:
        current_streak = 1
        for i in range(len(active_mondays) - 1, 0, -1):
            if (active_mondays[i] - active_mondays[i - 1]).days == 7:
                current_streak += 1
            else:
                break

    total_runs = len(runs)
    total_km = round(sum(r.distance_km or 0 for r in runs), 1)
    return {
        "available": True,
        "weeks_since_first_run": weeks_since,
        "total_runs": total_runs,
        "total_km": total_km,
        "current_streak_weeks": current_streak,
        "longest_streak_weeks": longest_streak,
        "avg_runs_per_week": round(total_runs / weeks_since, 1) if weeks_since else 0,
    }


def build_coach_patterns(
    plan: TrainingPlan, user_id: str, db: Session
) -> Dict[str, Any]:
    """Recency-weighted pace patterns + the inline week-pulse mood line.

    Trend fields (effort/quality drift) are intentionally left to
    ``build_coach_summary`` to avoid a second signal-gather; this endpoint
    stays light: one ``pattern_feedback`` call per workout type plus the
    week pulse.
    """
    runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan.id,
            RunLog.workout_type.isnot(None),
        )
        .order_by(RunLog.date.desc())
        .all()
    )

    patterns = []
    seen: set = set()
    for run in runs:
        wtype = run.workout_type
        if wtype not in _PATTERN_TYPES or wtype in seen:
            continue
        seen.add(wtype)
        message = pattern_feedback(run, fetch_pattern_candidates(run, db))
        if message:
            patterns.append({"workout_type": wtype, "message": message})

    week_pulse = None
    if plan.start_date:
        start = _to_date(plan.start_date)
        current_week = compute_current_week(
            start, local_today(), clamp_min=1, pre_start=1
        )
        week_pulse = get_week_pulse(plan, current_week, db)

    return {
        "available": True,
        "patterns": patterns,
        "week_pulse": week_pulse,
    }


def _direction(multiplier: float) -> str:
    if multiplier > 1.0 + _HOLD_BAND:
        return "increase"
    if multiplier < 1.0 - _HOLD_BAND:
        return "decrease"
    return "hold"


def _build_headline(signals: Dict[str, Any], direction: str, multiplier: float) -> str:
    """A short, human-readable summary of the current adaptation stance."""
    if direction == "hold":
        parts = ["Your plan is on track — no scaling needed right now."]
    else:
        verb = "step up" if direction == "increase" else "ease back"
        parts = [f"Your coach would {verb} remaining workouts (×{multiplier:.2f})."]

    phase = signals.get("current_phase")
    if phase:
        parts.append(f"You're in the {phase} phase.")

    if signals.get("overreach_detected"):
        parts.append(
            "Overreach detected — load is being held back to protect recovery."
        )

    tsb_form = signals.get("tsb_form")
    tsb = signals.get("tsb")
    if tsb_form and tsb is not None:
        parts.append(f"Form is {tsb_form} (TSB {tsb}).")

    effort_trend = signals.get("effort_trend")
    if effort_trend and effort_trend != "stable":
        parts.append(f"Perceived effort is {effort_trend}.")

    if signals.get("vdot_trend") == "declining":
        parts.append("VDOT is declining — capping volume to avoid overtraining.")

    return " ".join(parts)
