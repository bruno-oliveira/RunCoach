"""Plan viewing endpoint."""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.dependencies import (
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_plan_service,
)
from app.models import User
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.runner.fitness.hr_zone_service import HRZoneService
from app.contexts.plan.plan_helpers import get_plan_or_404, plan_view_context
from app.contexts.plan.plan_service import PlanService
from app.contexts.plan.plan_type_registry import get_handler_for_plan
from app.template_helpers import create_templates
from app.utils import persist_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])
templates = create_templates()


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
async def view_plan(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
    plan_service: PlanService = Depends(get_plan_service),
) -> HTMLResponse:
    """View an existing training plan."""
    try:
        training_plan = get_plan_or_404(
            plan_id, db, current_user, anonymous_user_id
        )

        if current_user and training_plan.start_date:
            try:
                adaptation_service = AdaptationService()
                adaptation_service.map_runs_to_plan(
                    plan_id, current_user.id, db
                )
                adaptation_service.check_alerts(
                    plan_id, current_user.id, db
                )
                adaptation_service.evaluate_recommendation(
                    plan_id, current_user.id, db
                )
            except Exception as e:
                logger.warning(f"Auto-map/alert on view failed: {e}")

        plan_data = training_plan.plan_data
        plan_data = plan_service.enrich_plan_data_with_ids(
            plan_data, training_plan.id, db
        )

        if not training_plan.nutrition_plan_data:
            nutrition_plan_raw = nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                training_plan.target_distance_km,
            )
            training_plan.nutrition_plan_data = nutrition_plan_raw
            db.commit()

        nutrition_plan = plan_service.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        if not training_plan.hr_zones_data:
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
                logger.warning(f"Retroactive HR zone computation failed: {e}")

        extra = plan_service.get_plan_view_data(training_plan, current_user, db)
        extra = get_handler_for_plan(training_plan).enrich_view_context(
            training_plan, db, extra, plan_data
        )

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan, db=db, **extra
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while generating the plan")
