"""Plan adjustment, recalibration, override, and swap endpoints."""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService, type_swapper
from app.contexts.plan.adaptation.missed_week_handler import detect_missed_weeks
from app.contexts.plan.plan_helpers import get_plan_or_404
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.plan.week_adjustment_service import apply_week_action
from app.contexts.runner.fitness.gap_analysis_service import GapAnalysisService
from app.contexts.runner.fitness.readiness_service import ReadinessService
from app.dependencies import get_current_user, get_db
from app.models import TrainingPlan, User
from app.utils import persist_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])


def _check_revision(training_plan: TrainingPlan, if_match: str | None) -> None:
    """Reject 409 if the client's revision is stale.

    `If-Match` is optional — a missing header skips the check, so older
    clients keep working. When present, it must equal the plan's current
    `adaptation_revision`.
    """
    if if_match is None or if_match == "":
        return
    try:
        expected = int(if_match)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-Match must be an integer revision.",
        )
    current = training_plan.adaptation_revision or 0
    if expected != current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "revision_conflict",
                "expected": expected,
                "current": current,
                "message": "Your plan was updated elsewhere — refresh to continue.",
            },
        )


# ---------------------------------------------------------------------------
# Read-only analysis endpoints
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/readiness")
def get_plan_readiness(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get race readiness assessment for a training plan."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    readiness = ReadinessService.compute_readiness(training_plan, current_user.id, db)

    if readiness is None:
        return {
            "available": False,
            "reason": "Set a start date and log some runs first.",
        }

    return {"available": True, **readiness}


@router.get("/api/plan/{plan_id}/gaps")
def get_plan_gaps(
    plan_id: str,
    weekly: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get gap analysis report for a training plan."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    if weekly:
        data = GapAnalysisService.analyze_gaps_weekly(
            training_plan, current_user.id, db
        )
        if data is None:
            return {
                "available": False,
                "reason": "Set a start date and log some runs first.",
            }
        return {"available": True, "weeks": data}

    gaps = GapAnalysisService.analyze_gaps(training_plan, current_user.id, db)

    if gaps is None:
        return {
            "available": False,
            "reason": "Set a start date and log some runs first.",
        }

    return {"available": True, **gaps}


@router.get("/api/plan/{plan_id}/missed-weeks")
def get_missed_weeks(
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
def adjust_plan(
    plan_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adjust future plan weeks based on recent performance data."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    _check_revision(training_plan, if_match)

    adaptation_service = AdaptationService()
    return adaptation_service.adjust_plan(plan_id, current_user.id, db)


@router.post("/api/plan/{plan_id}/adjust/preview")
def preview_adjust_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview what an Adjust Plan would do without committing changes."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.preview_adjust_plan(plan_id, current_user.id, db)


@router.post("/api/plan/{plan_id}/change-plan/mark-seen")
def mark_change_plan_seen(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark the persisted last_change_plan as seen so the modal stops
    auto-opening on next page load."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    adaptation_service = AdaptationService()
    return adaptation_service.mark_change_plan_seen(plan_id, current_user.id, db)


class RecalibrateRequest(BaseModel):
    strategy: str


@router.post("/api/plan/{plan_id}/recalibrate")
def recalibrate_plan(
    plan_id: str,
    body: RecalibrateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recalibrate remaining plan weeks based on user-chosen strategy."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.recalibrate(plan_id, current_user.id, body.strategy, db)


@router.post("/api/plan/{plan_id}/dismiss-alert")
def dismiss_alert(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss an active adaptation alert."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    training_plan.adaptation_alert = None
    db.commit()
    return {"ok": True}


@router.get("/api/plan/{plan_id}/pending-recommendation")
def get_pending_recommendation(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current pending adaptation recommendation, if any."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return {"recommendation": training_plan.pending_recommendation}


@router.post("/api/plan/{plan_id}/accept-recommendation")
def accept_recommendation(
    plan_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accept and apply the pending adaptation recommendation."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    _check_revision(training_plan, if_match)
    adaptation_service = AdaptationService()
    return adaptation_service.accept_recommendation(plan_id, current_user.id, db)


@router.post("/api/plan/{plan_id}/accept-recommendation/preview")
def preview_accept_recommendation(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview what accepting the pending recommendation would do."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    adaptation_service = AdaptationService()
    return adaptation_service.preview_accept_recommendation(
        plan_id, current_user.id, db
    )


@router.post("/api/plan/{plan_id}/dismiss-recommendation")
def dismiss_recommendation(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss the pending recommendation without applying."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    adaptation_service = AdaptationService()
    return adaptation_service.dismiss_recommendation(plan_id, current_user.id, db)


@router.post("/api/plan/{plan_id}/reset-adjustment")
def reset_plan_adjustment(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset plan adjustment, restoring original baseline distances."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.reset_adjustment(plan_id, current_user.id, db)


@router.post("/api/plan/{plan_id}/reset-adjustment/preview")
def preview_reset_plan_adjustment(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview what resetting the adjustment would do."""
    get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    adaptation_service = AdaptationService()
    return adaptation_service.preview_reset_adjustment(plan_id, current_user.id, db)


# ---------------------------------------------------------------------------
# Per-week overrides
# ---------------------------------------------------------------------------


class WeekOverrideRequest(BaseModel):
    action: str


@router.post("/api/plan/{plan_id}/week/{week_number}/override")
def override_plan_week(
    plan_id: str,
    week_number: int,
    body: WeekOverrideRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a per-week override to the plan."""
    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    _check_revision(training_plan, if_match)

    plan_data = training_plan.plan_data if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    payload = apply_week_action(
        body.action,
        training_plan,
        plan_data,
        week_data,
        week_number,
        plan_id,
        db,
    )
    db.commit()

    return {
        "ok": True,
        "action": body.action,
        "week": week_number,
        **payload,
    }


# ---------------------------------------------------------------------------
# Type swap (coach-suggested workout type substitution)
# ---------------------------------------------------------------------------


@router.get("/api/plan/{plan_id}/swap-proposals")
def get_swap_proposals(
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
def apply_type_swap(
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
def swap_plan_days(
    plan_id: str,
    week_number: int,
    body: SwapDaysRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Swap two workouts within the same week."""
    from app.contexts.plan.plan_adjustments import swap_days

    training_plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    if body.source_day == body.target_day:
        return {"ok": True}

    plan_data = training_plan.plan_data if training_plan.plan_data else []
    week_data = next((w for w in plan_data if w.get("week") == week_number), None)
    if not week_data:
        raise HTTPException(status_code=404, detail="Week not found in plan")

    plan_data = swap_days(plan_data, week_number, body.source_day, body.target_day)

    plan_repo = SQLAlchemyPlanRepository(db)
    weekly_plan = plan_repo.get_weekly_plan(plan_id, week_number)
    if weekly_plan:
        db_workouts = plan_repo.list_daily_workouts(weekly_plan.id)
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
    persist_json(training_plan, "plan_data")
    db.commit()

    return {"ok": True}
