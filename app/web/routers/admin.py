"""Admin console — operator-only tools for exercising integrations.

Gated by ``get_admin_user`` (``settings.admin_email``). Currently hosts a
send-to-watch tester: preview the Intervals.icu workout text a plan day would
produce, then push it via the normal ``/api/intervals/push-workout`` endpoint.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.workout_steps.intervals_export import build_intervals_workout
from app.dependencies import get_admin_user, get_db
from app.schemas import IntervalsPushRequest
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

admin_router = APIRouter(tags=["admin"])
templates = create_templates()


@admin_router.get("/admin", response_class=HTMLResponse)
def admin_console(
    request: Request,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the admin console (operator only)."""
    plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(admin_user.id)
    plan_options = [
        {
            "id": plan.id,
            "label": f"{plan.target_distance} · {plan.weeks_duration}wk · {plan.id[:8]}",
        }
        for plan in plans
    ]
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "request": request,
            "user": admin_user,
            "current_page": "admin",
            "plan_options": plan_options,
            "intervals_connected": bool(admin_user.intervals_athlete_id),
        },
    )


@admin_router.post("/api/admin/intervals/preview")
def admin_intervals_preview(
    payload: IntervalsPushRequest,
    admin_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Preview the Intervals.icu workout for a plan day — no side effects.

    Lets the operator eyeball the converter output (step text, pace zones,
    moving-time estimate) before actually pushing it to a watch.
    """
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(
        payload.plan_id, admin_user.id
    )
    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_data = training_plan.plan_data or []
    week_data = next((w for w in plan_data if w.get("week") == payload.week), None)
    if week_data is None:
        raise HTTPException(status_code=404, detail="Week not found")
    day_data = next(
        (d for d in week_data.get("daily_workouts", []) if d.get("day") == payload.day),
        None,
    )
    if day_data is None:
        raise HTTPException(status_code=404, detail="Day not found")

    try:
        workout = build_intervals_workout(day_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "workout_type": day_data.get("type"),
        "key_workout_name": day_data.get("key_workout_name"),
        "distance_km": day_data.get("distance"),
        **workout,
    }
