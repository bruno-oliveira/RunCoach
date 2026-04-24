"""Plan adjustment, recalibration, override, and swap endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.services.adaptation import type_swapper
from app.services.adaptation.missed_week_handler import detect_missed_weeks
from app.services.adaptation_service import AdaptationService
from app.services.gap_analysis_service import GapAnalysisService
from app.services.plan_helpers import get_plan_or_404
from app.services.readiness_service import ReadinessService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])


# ---------------------------------------------------------------------------
# Read-only analysis endpoints
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/readiness")
async def get_plan_readiness(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get race readiness assessment for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    readiness = ReadinessService.compute_readiness(
        training_plan, current_user.id, db
    )

    if readiness is None:
        return {"available": False, "reason": "Set a start date and log some runs first."}

    return {"available": True, **readiness}


@router.get("/api/plan/{plan_id}/gaps")
async def get_plan_gaps(
    plan_id: str,
    weekly: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get gap analysis report for a training plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    if weekly:
        data = GapAnalysisService.analyze_gaps_weekly(
            training_plan, current_user.id, db
        )
        if data is None:
            return {"available": False, "reason": "Set a start date and log some runs first."}
        return {"available": True, "weeks": data}

    gaps = GapAnalysisService.analyze_gaps(
        training_plan, current_user.id, db
    )

    if gaps is None:
        return {"available": False, "reason": "Set a start date and log some runs first."}

    return {"available": True, **gaps}


@router.get("/api/plan/{plan_id}/suggestions")
async def get_plan_suggestions(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get per-week adaptive suggestions for upcoming plan weeks."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    suggestions = adaptation_service.get_weekly_suggestions(
        plan_id, current_user.id, db
    )
    return {"suggestions": suggestions}


@router.get("/api/plan/{plan_id}/missed-weeks")
async def get_missed_weeks(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detect fully missed weeks (0 runs logged)."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    missed = detect_missed_weeks(plan_id, current_user.id, db)
    return {"missed_weeks": missed, "count": len(missed)}


# ---------------------------------------------------------------------------
# Adjustment / recalibration
# ---------------------------------------------------------------------------


@router.post("/api/plan/{plan_id}/adjust")
async def adjust_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adjust future plan weeks based on recent performance data."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.adjust_plan(plan_id, current_user.id, db)


class RecalibrateRequest(BaseModel):
    strategy: str  # "time_off" | "ahead" | "missed_week" | "recovery_insertion"


@router.post("/api/plan/{plan_id}/recalibrate")
async def recalibrate_plan(
    plan_id: str,
    body: RecalibrateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recalibrate remaining plan weeks based on user-chosen strategy."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.recalibrate(
        plan_id, current_user.id, body.strategy, db
    )


@router.post("/api/plan/{plan_id}/dismiss-alert")
async def dismiss_alert(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss an active adaptation alert."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )
    training_plan.adaptation_alert = None
    db.commit()
    return {"ok": True}


@router.post("/api/plan/{plan_id}/reset-adjustment")
async def reset_plan_adjustment(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset plan adjustment, restoring original baseline distances."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.reset_adjustment(plan_id, current_user.id, db)


# ---------------------------------------------------------------------------
# Per-week overrides
# ---------------------------------------------------------------------------


class WeekOverrideRequest(BaseModel):
    action: str  # "skip_bump" | "reduce_30" | "bump" | "ease_deficit" | "extend_long_run" | "reset_week"


@router.post("/api/plan/{plan_id}/week/{week_number}/override")
async def override_plan_week(
    plan_id: str,
    week_number: int,
    body: WeekOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a per-week override to the plan."""
    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    plan_data = training_plan.plan_data if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    _apply_week_action(body.action, training_plan, plan_data, week_data, week_number, plan_id, db)

    training_plan.plan_data = plan_data
    db.commit()

    return {"ok": True, "action": body.action, "week": week_number}


def _apply_week_action(
    action: str,
    training_plan: TrainingPlan,
    plan_data: list,
    week_data: dict,
    week_number: int,
    plan_id: str,
    db: Session,
) -> None:
    """Dispatch and execute a per-week override action."""
    if action == "skip_bump":
        _action_skip_bump(week_data, plan_id, week_number, db)
    elif action == "reduce_30":
        _action_reduce_30(plan_data, plan_id, week_number, db)
    elif action == "bump":
        _action_bump(week_data, training_plan, plan_id, week_number, db)
    elif action == "ease_deficit":
        _action_scale_week(week_data, plan_id, week_number, 0.85, db)
    elif action == "extend_long_run":
        _action_extend_long_run(week_data, plan_id, week_number, db)
    elif action == "reset_week":
        _action_reset_week(week_data, plan_id, week_number, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


def _get_week_workouts(plan_id: str, week_number: int, db: Session):
    """Fetch weekly plan and its workouts."""
    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .first()
    )
    if not weekly_plan:
        return None, []
    workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
        .all()
    )
    return weekly_plan, workouts


def _sync_plan_data_distances(week_data: dict, workouts: list) -> None:
    """Sync plan_data JSON distances from DB workout objects."""
    for wo_data in week_data.get("daily_workouts", []):
        for db_wo in workouts:
            if db_wo.day_of_week == wo_data.get("day"):
                wo_data["distance"] = db_wo.distance_km
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_skip_bump(week_data, plan_id, week_number, db):
    _, workouts = _get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.baseline_distance_km:
            wo.distance_km = wo.baseline_distance_km
    _sync_plan_data_distances(week_data, workouts)


def _action_reduce_30(plan_data, plan_id, week_number, db):
    factor = 0.7
    for target_week in range(week_number, min(week_number + 2, len(plan_data) + 1)):
        tw_data = next((w for w in plan_data if w.get("week") == target_week), None)
        if not tw_data:
            continue
        _, workouts = _get_week_workouts(plan_id, target_week, db)
        for wo in workouts:
            if wo.distance_km:
                wo.distance_km = round(wo.distance_km * factor, 1)
        for wo_data in tw_data.get("daily_workouts", []):
            if "distance" in wo_data:
                wo_data["distance"] = round(wo_data["distance"] * factor, 1)
        tw_data["total_km"] = round(
            sum(wo.distance_km for wo in workouts if wo.distance_km), 1
        )


def _action_bump(week_data, training_plan, plan_id, week_number, db):
    multiplier = training_plan.adjustment_multiplier or 1.08
    _, workouts = _get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.distance_km:
            if not wo.baseline_distance_km:
                wo.baseline_distance_km = wo.distance_km
            wo.distance_km = round(wo.distance_km * multiplier, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] * multiplier, 1)
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_scale_week(week_data, plan_id, week_number, factor, db):
    _, workouts = _get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.distance_km:
            if not wo.baseline_distance_km:
                wo.baseline_distance_km = wo.distance_km
            wo.distance_km = round(wo.distance_km * factor, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] * factor, 1)
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_extend_long_run(week_data, plan_id, week_number, db):
    _, workouts = _get_week_workouts(plan_id, week_number, db)
    long_wo = next((wo for wo in workouts if wo.workout_type == "long"), None)
    if long_wo and long_wo.distance_km:
        if not long_wo.baseline_distance_km:
            long_wo.baseline_distance_km = long_wo.distance_km
        long_wo.distance_km = round(long_wo.distance_km + 2, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if wo_data.get("type") == "long" and "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] + 2, 1)
            break
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_reset_week(week_data, plan_id, week_number, db):
    _, workouts = _get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.baseline_distance_km is not None:
            wo.distance_km = wo.baseline_distance_km
            wo.baseline_distance_km = None
    _sync_plan_data_distances(week_data, workouts)


# ---------------------------------------------------------------------------
# Type swap (coach-suggested workout type substitution)
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/swap-proposals")
async def get_swap_proposals(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get coach-suggested workout type swap proposals based on run patterns."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    proposals = type_swapper.get_swap_proposals(plan_id, current_user.id, db)
    return {"proposals": proposals}


class SwapTypeRequest(BaseModel):
    workout_id: str
    to_type: str


@router.post("/api/plan/{plan_id}/swap-type")
async def apply_type_swap(
    plan_id: str,
    body: SwapTypeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply an accepted workout type swap to a specific workout."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    result = type_swapper.apply_swap(
        body.workout_id, plan_id, current_user.id, body.to_type, db
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Workout not found")
    return result


# ---------------------------------------------------------------------------
# Day swap
# ---------------------------------------------------------------------------


class SwapDaysRequest(BaseModel):
    source_day: int
    target_day: int


@router.post("/api/plan/{plan_id}/week/{week_number}/swap-days")
async def swap_plan_days(
    plan_id: str,
    week_number: int,
    body: SwapDaysRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Swap two workouts within the same week."""
    from app.services.plan_adjustments import swap_days

    training_plan = get_plan_or_404(
        plan_id, db, current_user, require_user_match=True
    )

    if body.source_day == body.target_day:
        return {"ok": True}

    plan_data = training_plan.plan_data if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    plan_data = swap_days(plan_data, week_number, body.source_day, body.target_day)

    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .first()
    )
    if weekly_plan:
        db_workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
            .all()
        )
        src_db = next(
            (wo for wo in db_workouts if wo.day_of_week == body.source_day), None
        )
        tgt_db = next(
            (wo for wo in db_workouts if wo.day_of_week == body.target_day), None
        )
        if src_db and tgt_db:
            src_db.day_of_week, tgt_db.day_of_week = (
                tgt_db.day_of_week,
                src_db.day_of_week,
            )

    training_plan.plan_data = plan_data
    db.commit()

    return {"ok": True}
