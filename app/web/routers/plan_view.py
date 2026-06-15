"""Plan viewing endpoint."""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.application.plan_view_service import PlanViewService
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.plan_helpers import get_plan_or_404, plan_view_context
from app.contexts.plan.plan_type_registry import get_handler_for_plan
from app.contexts.runner.fitness.hr_zone_service import HRZoneService
from app.dependencies import (
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_plan_view_service,
)
from app.models import User
from app.template_helpers import create_templates
from app.utils import persist_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
def view_plan(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_view_service: PlanViewService = Depends(get_plan_view_service),
) -> HTMLResponse:
    """View an existing training plan."""
    try:
        training_plan = get_plan_or_404(plan_id, db, current_user, anonymous_user_id)

        if current_user and training_plan.start_date:
            try:
                adaptation_service = AdaptationService()
                adaptation_service.map_runs_to_plan(plan_id, current_user.id, db)
            except Exception as e:
                logger.warning("Auto-map on view failed: %s", e)

        plan_data = training_plan.plan_data
        plan_data = plan_view_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        if not training_plan.nutrition_plan_data:
            nutrition_plan_raw = nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                training_plan.target_distance_km,
            )
            training_plan.nutrition_plan_data = nutrition_plan_raw
            db.commit()

        nutrition_plan = plan_view_service.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        if not training_plan.hr_zones_data or HRZoneService.zones_are_stale(
            training_plan
        ):
            try:
                user = current_user or SQLAlchemyUserRepository(db).get_by_id(
                    training_plan.user_id
                )
                if user:
                    zones = HRZoneService.compute_and_store_zones(
                        training_plan, user, db
                    )
                    HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
                    training_plan.plan_data = plan_data
                    persist_json(training_plan, "plan_data")
                    db.commit()
            except Exception as e:
                logger.warning("Retroactive HR zone computation failed: %s", e)

        extra = plan_view_service.get_plan_view_data(training_plan, current_user, db)
        extra = get_handler_for_plan(training_plan).enrich_view_context(
            training_plan, db, extra, plan_data
        )

        ctx = plan_view_context(
            request,
            current_user,
            training_plan,
            plan_data,
            nutrition_plan,
            db=db,
            **extra,
        )
        return templates.TemplateResponse(request, "plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating plan: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while generating the plan",
        )


def _find_workout_in_plan(
    plan_data: list, workout_id: str
) -> tuple[Optional[dict], Optional[dict]]:
    """Locate a workout (and its containing week) by DB id within plan_data.

    Returns (week, workout) or (None, None) if not found.
    """
    for week in plan_data:
        for workout in week.get("daily_workouts", []):
            if workout.get("id") == workout_id:
                return week, workout
    return None, None


@router.get("/plan/{plan_id}/day/{workout_id}", response_class=HTMLResponse)
def view_workout_day(
    plan_id: str,
    workout_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_view_service: PlanViewService = Depends(get_plan_view_service),
) -> HTMLResponse:
    """Dedicated detail page for a single day's workout.

    Reuses the same enrichment as the full plan view (DB ids, HR zones,
    baseline recovery, structured steps) so the day page shows the same rich
    workout data the cards do, then narrows to one workout.
    """
    try:
        training_plan = get_plan_or_404(plan_id, db, current_user, anonymous_user_id)

        plan_data = training_plan.plan_data
        plan_data = plan_view_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        # Bring HR-zone labels in line with the full view when available.
        if training_plan.hr_zones_data:
            try:
                HRZoneService.inject_hr_zones_into_plan_data(
                    plan_data, training_plan.hr_zones_data
                )
            except Exception as e:
                logger.warning("Day view HR zone injection failed: %s", e)

        week, workout = _find_workout_in_plan(plan_data, workout_id)
        if not week or not workout:
            raise HTTPException(status_code=404, detail="Workout not found")

        # Per-day calendar label + week date range, mirroring the plan view.
        from app.core.time_utils import local_today
        from app.core.training.plan_calendar import (
            build_week_dates,
            compute_current_week,
            workout_dates,
        )

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        week_num = week.get("week")
        day_num = workout.get("day")
        date_label = None
        is_today = False
        if training_plan.start_date:
            from datetime import datetime as _dt

            sd = training_plan.start_date
            start_d = sd.date() if isinstance(sd, _dt) else sd
            num_weeks = len(plan_data) if plan_data else training_plan.weeks_duration
            labels = workout_dates(start_d, num_weeks)
            date_label = labels.get((week_num, day_num))
            week_dates = build_week_dates(start_d, num_weeks)
            current_week_number = compute_current_week(start_d, local_today())
            current_day = local_today().isoweekday()
            is_today = current_week_number == week_num and current_day == day_num
        else:
            week_dates = None

        # Surface a logged run for this workout, if one is mapped.
        logged_runs_map, _ = plan_view_service.get_logged_runs_map(training_plan.id, db)
        logged_run = logged_runs_map.get(workout_id)

        ctx = {
            "request": request,
            "user": current_user,
            "plan_id": training_plan.id,
            "training_plan": training_plan,
            "week": week,
            "workout": workout,
            "week_num": week_num,
            "day_num": day_num,
            "day_name": day_names[day_num - 1] if day_num else "",
            "date_label": date_label,
            "is_today": is_today,
            "week_dates": week_dates,
            "logged_run": logged_run,
            "is_trail": bool(getattr(training_plan, "is_trail", False)),
        }
        return templates.TemplateResponse(request, "day_detail.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error rendering workout day: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while loading this workout",
        )
