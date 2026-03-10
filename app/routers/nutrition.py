"""Nutrition-related endpoints."""

import json
import logging
import time

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_optional_user, verify_plan_ownership
from app.models import TrainingPlan, RunLog
from app.core.nutrition_engine import NutritionEngine
from app.services.plan_service import PlanService
from app.schemas import parse_target_distance
from app.services.adaptation_service import AdaptationService
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

        # Use current time to ensure different results each time
        random_seed = int(time.time() * 1000000) % 100000000
        nutrition_engine = NutritionEngine(random_seed=random_seed)

        # Generate new meal blueprint with different randomization
        new_nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            training_plan.current_weekly_km,
            parse_target_distance(training_plan.target_distance),
        )

        # Update the plan with new blueprint
        training_plan.nutrition_plan_data = json.dumps(new_nutrition_plan)
        db.commit()
        logger.info(f"Successfully updated nutrition plan for {plan_id}")

        # Get performance analysis and logged runs for the plan
        adaptation_service = AdaptationService()
        performance_analysis = adaptation_service.analyze_performance(plan_id, db)
        logged_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan_id).all()

        # Convert to map for template lookup (template uses logged_runs.get(workout.id))
        logged_runs_map = {
            run.daily_workout_id: run for run in logged_runs if run.daily_workout_id
        }

        response_data = {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
            "plan": json.loads(training_plan.plan_data),
            "plan_id": training_plan.id,
            "training_plan": training_plan,
            "current_km": training_plan.current_weekly_km,
            "target_distance": training_plan.target_distance,
            "weeks": training_plan.weeks_duration,
            "logged_runs": logged_runs_map,
            "performance_analysis": performance_analysis,
            "success_message": "Generated new meal options with different variety!",
        }

        # Convert nutrition plan to template-compatible format
        response_data["nutrition_plan"] = PlanService.nutrition_for_template(
            training_plan.nutrition_plan_data
        )

        return templates.TemplateResponse("plan.html", response_data)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error randomizing meals")
        error_msg = str(e) if str(e) else f"{type(e).__name__}: Error randomizing meals"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/nutrition-plan/{plan_id}", response_class=HTMLResponse)
async def get_nutrition_plan(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Get detailed nutrition plan for a training plan."""
    try:
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(status_code=403, detail="Not authorized to view this plan")

        nutrition_plan = []
        if training_plan.nutrition_plan_data:
            nutrition_plan = json.loads(training_plan.nutrition_plan_data)

        return templates.TemplateResponse(
            "nutrition.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "nutrition_plan": nutrition_plan,
                "plan_id": plan_id,
                "training_plan": training_plan,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
