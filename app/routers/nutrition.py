"""Nutrition-related endpoints."""

import json
import logging
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_optional_user
from app.models import TrainingPlan, RunLog
from app.core.nutrition_engine import NutritionEngine
from app.routers.plans import get_nutrition_plan_for_template
from app.schemas import parse_target_distance
from app.services.adaptation_service import AdaptationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nutrition"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/randomize-meals", response_class=HTMLResponse)
async def randomize_meals(
    request: Request,
    plan_id: str = Form(...),
    current_user = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Generate different meal suggestions for the nutrition blueprint."""
    try:
        logger.info(f"Looking for plan with id: {plan_id} (type: {type(plan_id).__name__})")
        logger.info(f"Request form data: {await request.form()}")
        
        # Also check for plans in the database for debugging
        all_plans = db.query(TrainingPlan).all()
        logger.info(f"Total plans in database: {len(all_plans)}")
        if all_plans:
            logger.info(f"Plan IDs in database: {[p.id for p in all_plans[:5]]}")
        
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        logger.info(f"Found training_plan: {training_plan is not None}")
        if not training_plan:
            logger.error(f"Plan not found. Looking for plan_id: {plan_id}")
            raise HTTPException(status_code=404, detail="Plan not found")

        # Use current time with nanoseconds to ensure different results each time
        random_seed = int(time.time() * 1000000) % 100000000
        logger.info(f"Randomizing meals for plan {plan_id} with seed: {random_seed}")

        # Store old meal data for comparison
        old_meals = None
        if training_plan.nutrition_plan_data:
            try:
                old_meals = json.loads(training_plan.nutrition_plan_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse existing nutrition data for plan {plan_id}")

        nutrition_engine = NutritionEngine(random_seed=random_seed)

        # Generate new meal blueprint with different randomization
        new_nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            training_plan.current_weekly_km,
            parse_target_distance(training_plan.target_distance),
        )

        # Log comparison
        if old_meals and isinstance(old_meals, dict) and isinstance(new_nutrition_plan, dict):
            old_meal_options = old_meals.get("meal_options", {})
            if isinstance(old_meal_options, dict):
                old_breakfast = [
                    m["name"]
                    for m in old_meal_options.get("breakfast", [])
                    if isinstance(m, dict) and "name" in m
                ]
            else:
                old_breakfast = []

            new_meal_options = new_nutrition_plan.get("meal_options", {})
            if isinstance(new_meal_options, dict):
                new_breakfast = [
                    m["name"]
                    for m in new_meal_options.get("breakfast", [])
                    if isinstance(m, dict) and "name" in m
                ]
            else:
                new_breakfast = []

            logger.info(f"Old breakfast options: {old_breakfast}")
            logger.info(f"New breakfast options: {new_breakfast}")
        else:
            logger.info("No previous meal data to compare (or data is not a dict)")

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
        response_data["nutrition_plan"] = get_nutrition_plan_for_template(
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
