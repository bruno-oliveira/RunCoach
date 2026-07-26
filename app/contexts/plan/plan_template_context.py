"""Template context building for plan views."""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func

from app.core.coaching.readiness_checkin import score_checkin
from app.core.coaching.today_card import TodayCard, build_today_card
from app.core.time_utils import local_today
from app.core.training.plan_calendar import (
    build_week_dates,
    compute_current_week,
    ensure_seven_days,
    next_monday,
    workout_dates,
)
from app.core.training.strength_plan import derive_experience_level
from app.core.training.watch_mirror import sessions_behind, synced_day_keys
from app.infrastructure.config import settings
from app.models import (
    ReadinessLog,
    RunFeedback,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)

_PACE_BADGE_WINDOW_DAYS = 7


def plan_view_context(
    request: Request,
    current_user: Optional[User],
    training_plan: TrainingPlan,
    plan_data: list[dict],
    nutrition_plan: dict,
    db: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the standard plan.html template context dict."""
    plan_data = ensure_seven_days(plan_data)

    start_date_val = None
    current_week_number = None
    week_dates = None
    workout_date_labels: dict[tuple[int, int], str] = {}
    today_obj = local_today()

    plan_completed = False
    if training_plan.start_date:
        sd = training_plan.start_date
        start_date_val = (
            sd.date()
            if isinstance(sd, datetime)
            else sd
            if isinstance(sd, date)
            else sd
        )
        num_weeks = len(plan_data) if plan_data else training_plan.weeks_duration
        week_dates = build_week_dates(start_date_val, num_weeks)
        current_week_number = compute_current_week(start_date_val, today_obj)
        if current_week_number and current_week_number > num_weeks:
            current_week_number = None
            plan_completed = True
        workout_date_labels = workout_dates(start_date_val, num_weeks)

    pace_zones_updated_recent = _compute_pace_zone_badge(db, training_plan.id)
    adaptation_state = _build_adaptation_state(training_plan)
    long_run_warning = _build_long_run_warning(training_plan, plan_data)
    frequency_warning = _build_frequency_warning(training_plan, plan_data)

    today_workout_overlay = _build_today_workout_overlay(
        db,
        current_user,
        plan_data,
        start_date_val,
        today_obj,
        current_week_number,
    )

    today_card = _build_today_card(
        db,
        current_user,
        plan_data,
        start_date_val,
        today_obj,
        current_week_number,
        today_workout_overlay,
    )

    ctx: dict[str, Any] = {
        "request": request,
        "user": current_user,
        "google_client_id": settings.google_client_id,
        "plan": plan_data,
        "plan_id": training_plan.id,
        "training_plan": training_plan,
        "current_km": training_plan.current_weekly_km,
        "experience_level": derive_experience_level(
            training_plan.current_weekly_km or 0
        ),
        "target_distance": training_plan.target_distance,
        "is_trail": bool(getattr(training_plan, "is_trail", False)),
        "target_elevation_gain_m": getattr(
            training_plan, "target_elevation_gain_m", None
        ),
        "weeks": training_plan.weeks_duration,
        "nutrition_plan": nutrition_plan,
        "nutrition_phases": (
            training_plan.nutrition_phases_data
            if training_plan.nutrition_phases_data
            else {}
        ),
        "race_protocol": (
            training_plan.race_protocol_data if training_plan.race_protocol_data else {}
        ),
        "vdot": training_plan.vdot,
        "logged_runs": {},
        "performance_analysis": None,
        "progress_data": None,
        "start_date": start_date_val,
        "current_week_number": current_week_number,
        "plan_completed": plan_completed,
        "today_iso": today_obj.isoformat(),
        "current_day_of_week": today_obj.isoweekday(),
        "week_dates": week_dates,
        "workout_date_labels": workout_date_labels,
        "next_monday": next_monday(),
        "pace_zones_updated_recent": pace_zones_updated_recent,
        "today_workout_overlay": today_workout_overlay,
        "today_card": today_card,
        "adaptation_state": adaptation_state,
        "adaptation_revision": training_plan.adaptation_revision or 0,
        "long_run_warning": long_run_warning,
        "frequency_warning": frequency_warning,
        "intervals_connected": bool(current_user and current_user.intervals_athlete_id),
        # Watch-mirror state, read from what we last put on the calendar rather
        # than from a browser flag, so it survives a reload.
        "watch_sync_enabled": bool(training_plan.watch_sync_enabled),
        "watch_sessions_behind": sessions_behind(training_plan, today=today_obj),
        "watch_sync_error": training_plan.watch_sync_error,
        "watch_synced_days": synced_day_keys(training_plan),
        "watch_setup_confirmed": bool(
            current_user and current_user.watch_setup_confirmed_at
        ),
    }
    ctx.update(extra)
    return ctx


def _build_long_run_warning(
    training_plan: TrainingPlan, plan_data: list[dict]
) -> Optional[dict]:
    """Non-blocking warning when the plan's peak long run falls short of race
    specificity (too little base × timeline to ramp safely).

    Only race plans (distance/trail) are assessed — fitness plans have no race
    distance to be specific for. Pure read of the stored plan, so it also
    applies retroactively to plans created before the check existed.
    """
    if getattr(training_plan, "plan_type", "distance") not in ("distance",):
        return None

    target_distance = training_plan.target_distance_km
    if not target_distance or target_distance <= 0:
        return None

    peak_long_run = 0.0
    for week in plan_data or []:
        if week.get("is_recovery"):
            continue
        for workout in week.get("daily_workouts", []) or []:
            if workout.get("type") == "long":
                peak_long_run = max(peak_long_run, workout.get("distance", 0) or 0)

    if peak_long_run <= 0:
        return None

    trail_profile = None
    if bool(getattr(training_plan, "is_trail", False)):
        from app.core.training.trail_profile import classify_trail

        trail_profile = classify_trail(
            target_distance,
            getattr(training_plan, "target_elevation_gain_m", None) or 0.0,
        )

    from app.core.training.long_run_calculator import assess_long_run_adequacy

    return assess_long_run_adequacy(
        peak_long_run,
        target_distance,
        experience_level=derive_experience_level(training_plan.current_weekly_km or 0),
        trail_profile=trail_profile,
        training_terrain=getattr(training_plan, "training_terrain", None),
        weeks=training_plan.weeks_duration,
    )


def _build_frequency_warning(
    training_plan: TrainingPlan, plan_data: list[dict]
) -> Optional[dict]:
    """Non-blocking advisory when a low run frequency caps weekly volume below
    the runner's established base (they could add a day and keep their mileage).

    Race plans only; fitness plans target a gentler peak by design. Pure read of
    the stored plan, so it also applies retroactively to existing plans.
    """
    if getattr(training_plan, "plan_type", "distance") not in ("distance",):
        return None

    max_runs = getattr(training_plan, "max_runs_per_week", None)
    current_km = training_plan.current_weekly_km or 0
    if not max_runs or current_km <= 0:
        return None

    realized_peak = 0.0
    for week in plan_data or []:
        if week.get("is_recovery"):
            continue
        total = sum(
            (w.get("distance", 0) or 0) for w in week.get("daily_workouts", []) or []
        )
        realized_peak = max(realized_peak, total)

    if realized_peak <= 0:
        return None

    from app.core.training.long_run_calculator import (
        assess_frequency_volume_adequacy,
    )

    return assess_frequency_volume_adequacy(
        current_km,
        realized_peak,
        max_runs,
        weeks=training_plan.weeks_duration,
    )


def _build_adaptation_state(training_plan: TrainingPlan) -> dict:
    """Adaptation is now fully user-driven via the "Adjust my plan" intent
    menu, so there is no passive alert/recommendation surface. Retained as a
    stable ``{"kind": "none"}`` payload for the client (APP_CTX + change-plan
    patch) so existing JS keeps working without special-casing."""
    return {"kind": "none"}


def today_card_for_plan(
    db: Any, current_user: Optional[User], training_plan: TrainingPlan
) -> Optional[TodayCard]:
    """Build just the Today card for a plan, from the plan alone.

    The page gets its card as part of :func:`plan_view_context`; this is the
    entry point for re-reading it after a check-in, so the advisory under
    today's session has exactly one implementation rather than a Python copy
    and a JavaScript one that drift.

    ``plan_data`` is not id-enriched here, so ``session.workout_id`` is ``None``
    — callers that need the link should render the page.
    """
    if not training_plan.start_date:
        return None

    plan_data = ensure_seven_days(training_plan.plan_data or [])
    sd = training_plan.start_date
    start_date_val = sd.date() if isinstance(sd, datetime) else sd
    today_obj = local_today()
    num_weeks = len(plan_data) if plan_data else training_plan.weeks_duration
    current_week_number = compute_current_week(start_date_val, today_obj)
    if not current_week_number or current_week_number > num_weeks:
        return None

    overlay = _build_today_workout_overlay(
        db, current_user, plan_data, start_date_val, today_obj, current_week_number
    )
    return _build_today_card(
        db,
        current_user,
        plan_data,
        start_date_val,
        today_obj,
        current_week_number,
        overlay,
    )


def _build_today_card(
    db: Any,
    current_user: Optional[User],
    plan_data: list[dict],
    start_date_val: Optional[date],
    today_obj: date,
    current_week_number: Optional[int],
    overlay: dict[str, dict],
) -> Optional[TodayCard]:
    """Resolve today's session + this morning's check-in into one view model.

    Returns ``None`` for anyone the card can't speak to — a signed-out visitor
    on a shared plan, or a plan with no start date and therefore no "today".
    The pure assembly lives in ``core.coaching.today_card``; this is the I/O.
    """
    if db is None or current_user is None or start_date_val is None:
        return None
    if current_week_number is None:
        return None

    week = next(
        (w for w in plan_data if w.get("week") == current_week_number),
        None,
    )
    if week is None:
        return None

    day_of_week = today_obj.isoweekday()
    workout = next(
        (
            w
            for w in week.get("daily_workouts", []) or []
            if w.get("day") == day_of_week
        ),
        None,
    )

    logged_km = (
        db.query(func.sum(RunLog.distance_km))
        .filter(
            RunLog.user_id == current_user.id,
            RunLog.date >= today_obj,
            RunLog.date < today_obj + timedelta(days=1),
        )
        .scalar()
    )

    readiness = (
        db.query(ReadinessLog)
        .filter(
            ReadinessLog.user_id == current_user.id,
            ReadinessLog.date == today_obj,
        )
        .first()
    )
    assessment = (
        score_checkin(
            sleep_hours=readiness.sleep_hours,
            sleep_quality=readiness.sleep_quality,
            energy=readiness.energy,
            soreness=readiness.soreness,
            stress=readiness.stress,
        )
        if readiness is not None
        else None
    )

    return build_today_card(
        today=today_obj,
        workout=workout,
        week_number=current_week_number,
        total_weeks=len(plan_data) or None,
        phase=week.get("phase"),
        logged_km=logged_km,
        readiness_band=assessment.band if assessment else None,
        readiness_score=assessment.score if assessment else None,
        readiness_label=assessment.label if assessment else None,
        readiness_drivers=assessment.drivers if assessment else None,
        fatigue_softened=bool(
            overlay.get(f"{current_week_number}-{day_of_week}", {}).get(
                "is_fatigue_softened"
            )
        ),
    )


_QUALITY_WORKOUT_TYPES = frozenset({"tempo", "interval", "vo2max", "hill", "long"})


def _build_today_workout_overlay(
    db: Any,
    current_user: Optional[User],
    plan_data: list[dict],
    start_date_val: Optional[date],
    today_obj: date,
    current_week_number: Optional[int],
) -> dict[str, dict]:
    """Compute per-day rationale prefixes ("After yesterday's…", fatigue softening).

    Returns a dict keyed by (week, day_of_week) → {"rationale_prefix": str, "is_fatigue_softened": bool}.
    The template uses the overlay to render dynamic context without persisting it.
    """
    if (
        db is None
        or current_user is None
        or start_date_val is None
        or current_week_number is None
    ):
        return {}

    user_runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id)
        .order_by(RunLog.date.desc())
        .limit(6)
        .all()
    )
    last_3 = user_runs[:3]
    prev_run = _most_recent_within_two_days(user_runs, today_obj)

    fatigue_softened = _detect_fatigue_softening(last_3, db)

    overlay: dict[str, dict] = {}
    for week in plan_data:
        wk_num = week.get("week")
        if not wk_num or wk_num != current_week_number:
            continue
        for workout in week.get("daily_workouts", []) or []:
            day = workout.get("day")
            wtype = (workout.get("type") or "").lower()
            if not day or not wtype:
                continue
            sched_date = start_date_val + timedelta(weeks=wk_num - 1, days=day - 1)
            if sched_date != today_obj:
                continue

            prefix = _coaching_prefix(prev_run)
            fatigue_active = fatigue_softened and wtype in _QUALITY_WORKOUT_TYPES
            if not prefix and not fatigue_active:
                continue
            overlay[f"{wk_num}-{day}"] = {
                "rationale_prefix": prefix,
                "is_fatigue_softened": fatigue_active,
            }
    return overlay


def _most_recent_within_two_days(runs: list, today_obj: date) -> Any:
    """Return the most recent run logged within the last 2 calendar days."""
    cutoff = today_obj - timedelta(days=2)
    for run in runs:
        run_date = run.date
        if isinstance(run_date, datetime):
            run_date = run_date.date()
        if run_date and run_date >= cutoff and run_date <= today_obj:
            return run
    return None


def _coaching_prefix(prev_run: Any) -> Optional[str]:
    if prev_run is None:
        return None
    prev_type = (getattr(prev_run, "workout_type", None) or "").lower()
    effort = getattr(prev_run, "perceived_effort", None)
    if prev_type in ("tempo", "interval", "vo2max") and (effort or 0) >= 7:
        return f"After yesterday's hard {prev_type}, "
    if prev_type == "long" and (effort or 0) >= 6:
        return "After yesterday's long run, "
    if prev_type == "easy" and effort is not None and effort <= 4:
        return "Yesterday was easy and well-controlled — "
    return None


def _detect_fatigue_softening(runs: list, db: Any) -> bool:
    """Recent runs averaged ≥8 effort with ≥2 warning feedbacks → soften today."""
    if len(runs) < 3:
        return False
    efforts = [
        getattr(r, "perceived_effort", None)
        for r in runs
        if getattr(r, "perceived_effort", None) is not None
    ]
    if len(efforts) < 3 or sum(efforts) / len(efforts) < 8:
        return False
    run_ids = [r.id for r in runs]
    warning_count = (
        db.query(RunFeedback)
        .filter(
            RunFeedback.run_log_id.in_(run_ids),
            RunFeedback.overall_sentiment == "warning",
        )
        .count()
    )
    return warning_count >= 2


def _compute_pace_zone_badge(db: Any, plan_id: str) -> Optional[dict]:
    """Return badge info for the most recent pace-zone refresh, if within window."""
    if db is None or plan_id is None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=_PACE_BADGE_WINDOW_DAYS)
    latest = (
        db.query(WeeklyPlan.pace_zones_updated_at)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.pace_zones_updated_at.isnot(None),
            WeeklyPlan.pace_zones_updated_at >= cutoff,
        )
        .order_by(WeeklyPlan.pace_zones_updated_at.desc())
        .first()
    )
    if not latest or latest[0] is None:
        return None
    updated_at = latest[0]
    days_ago = max(0, (now - updated_at).days)
    return {
        "updated_at": updated_at,
        "days_ago": days_ago,
        "label": (
            "Paces just updated"
            if days_ago == 0
            else f"Paces updated {days_ago} day{'s' if days_ago != 1 else ''} ago"
        ),
    }
