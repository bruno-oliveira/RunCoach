"""Nutrition-related endpoints."""

import json
import logging

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_nutrition_engine, get_optional_user, get_plan_service, verify_plan_ownership
from app.models import TrainingPlan
from app.services.plan_service import PlanService
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nutrition"])
templates = create_templates()


@router.post("/randomize-meals", response_class=HTMLResponse)
async def randomize_meals(
    request: Request,
    plan_id: str = Form(...),
    anonymous_user_id: Optional[str] = Cookie(None),
    current_user = Depends(get_optional_user),
    db: Session = Depends(get_db),
    plan_service: PlanService = Depends(get_plan_service),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
) -> HTMLResponse:
    """Generate different meal suggestions for the nutrition blueprint."""
    try:
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(status_code=403, detail="Not authorized to modify this plan")

        # Generate new meal blueprint with different randomization
        new_nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            training_plan.current_weekly_km,
            training_plan.target_distance_km,
        )

        # Update the plan with new blueprint
        training_plan.nutrition_plan_data = json.dumps(new_nutrition_plan)
        db.commit()
        logger.info("Successfully updated nutrition plan for %s", plan_id)

        from app.routers.plan_helpers import plan_view_context

        plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []
        plan_data = plan_service.enrich_plan_data_with_ids(plan_data, training_plan.id, db)
        nutrition_plan = plan_service.nutrition_for_template(training_plan.nutrition_plan_data)
        extra = plan_service.get_plan_view_data(training_plan, current_user, db)

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan, **extra
        )
        ctx["success_message"] = "Generated new meal options with different variety!"

        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Error randomizing meals")
        raise HTTPException(status_code=500, detail="An internal error occurred while randomizing meals")
