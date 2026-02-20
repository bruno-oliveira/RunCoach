"""Plan generation and management endpoints."""

import json
import logging
import os
from typing import Any, Optional

from cachetools import TTLCache
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings

from app.dependencies import (
    get_db,
    get_nutrition_engine,
    get_pdf_generator,
    get_plan_generator,
)
from app.exceptions import (
    DatabaseException,
    InadequateBaseException,
    InsufficientTimeException,
    PlanGenerationException,
    ValidationException,
)
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan
from app.models import PlanCustomization as PlanCustomizationModel
from app.core.nutrition_engine import NutritionEngine
from app.core.pdf_generator import PDFGenerator
from app.core.plan_generator import TrainingPlanGenerator
from app.schemas import DISTANCE_NAMES, PlanRequest, get_mileage_warning, parse_target_distance
from app.dependencies import get_current_user, get_optional_user, verify_plan_ownership
from app.services.adaptation_service import AdaptationService
from app.utils import format_pace

logger = logging.getLogger(__name__)
adaptation_service = AdaptationService()

router = APIRouter(tags=["plans"])
templates = Jinja2Templates(directory="app/templates")


templates.env.filters['format_pace'] = format_pace

user_plans_cache = TTLCache(maxsize=1000, ttl=300)


def get_nutrition_plan_for_template(nutrition_plan_data: str) -> dict[str, Any]:
    """Convert nutrition plan data to template-compatible format."""
    if not nutrition_plan_data:
        return {}

    nutrition_plan = json.loads(nutrition_plan_data)

    # Check if it's the old format (list of daily plans) or new format (blueprint)
    if isinstance(nutrition_plan, list):
        # Old format - convert to new blueprint format
        if nutrition_plan:
            first_day = nutrition_plan[0]
            # Ensure first_day is a dict before calling .get()
            if not isinstance(first_day, dict):
                return {}
            targets = first_day.get("nutrition_targets", {})
            if not isinstance(targets, dict):
                targets = {}
            blueprint = {
                "daily_calories": targets.get("calories", 0),
                "protein_g": targets.get("protein", 0),
                "carbs_g": targets.get("carbs", 0),
                "fats_g": targets.get("fat", 0),
                "meal_suggestions": {},
                "general_tips": first_day.get("nutrition_tips", []),
                "hydration_guide": {
                    "daily_target": "2000ml",
                    "pre_run": "300-500ml, 2 hours before",
                    "during_run": "200-400ml per hour",
                    "post_run": "150% of fluid lost",
                    "tips": ["Stay hydrated throughout the day"],
                },
            }

            for daily_plan in nutrition_plan:
                # Skip non-dict items in the list
                if not isinstance(daily_plan, dict):
                    continue
                meals = daily_plan.get("meals", {})
                if not isinstance(meals, dict):
                    continue
                for meal_type, meal_data in meals.items():
                    if meal_type not in blueprint["meal_suggestions"]:
                        blueprint["meal_suggestions"][meal_type] = []
                    blueprint["meal_suggestions"][meal_type].append(meal_data)

            return blueprint
        return {}

    # New blueprint format - transform to template-expected structure
    # Ensure nutrition_plan is a dict before accessing
    if not isinstance(nutrition_plan, dict):
        return {}

    targets = nutrition_plan.get("nutrition_targets", {})
    if not isinstance(targets, dict):
        targets = {}

    meal_options = nutrition_plan.get("meal_options", {})
    if not isinstance(meal_options, dict):
        meal_options = {}

    general_tips = nutrition_plan.get("general_tips", [])
    if not isinstance(general_tips, list):
        general_tips = []

    hydration_guide = nutrition_plan.get("hydration_guide", {})
    if not isinstance(hydration_guide, dict):
        hydration_guide = {}

    return {
        "daily_calories": targets.get("calories", 0),
        "protein_g": targets.get("protein", 0),
        "carbs_g": targets.get("carbs", 0),
        "fats_g": targets.get("fat", 0),
        "meal_suggestions": meal_options,
        "general_tips": general_tips,
        "hydration_guide": hydration_guide,
        "pre_run_meal": nutrition_plan.get("pre_run_meal"),
        "post_run_meal": nutrition_plan.get("post_run_meal"),
    }


@router.post("/generate-plan", response_class=HTMLResponse)
async def generate_plan(
    request: Request,
    response: Response,
    current_km: float = Form(...),
    target_distance: str = Form(...),
    weeks: int = Form(...),
    max_runs_per_week: int = Form(4),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    plan_generator: TrainingPlanGenerator = Depends(get_plan_generator),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
) -> HTMLResponse:
    """Generate a personalized training plan."""
    # Debug: log auth state
    logger.info(f"Generate plan - current_user: {current_user.id if current_user else 'None'}")
    logger.info(f"Generate plan - anonymous_user_id cookie: {request.cookies.get('anonymous_user_id', 'NO COOKIE')}")
    logger.info(f"Generate plan - access_token cookie: {request.cookies.get('access_token', 'NO COOKIE')[:20] if request.cookies.get('access_token') else 'NO COOKIE'}...")

    # Validate input using Pydantic
    try:
        # Convert string target_distance to float
        target_distance_parsed = float(target_distance)

        plan_request = PlanRequest(
            current_km=current_km,
            target_distance=target_distance_parsed,
            weeks=weeks,
            max_runs_per_week=max_runs_per_week,
        )
    except InsufficientTimeException as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": e.user_message,
                "error_type": "insufficient_time",
                "suggestion": e.suggestion,
            },
        )
    except InadequateBaseException as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": e.user_message,
                "error_type": "inadequate_base",
                "suggestion": e.suggestion,
            },
        )
    except ValidationException as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": e.user_message,
                "error_type": "validation",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": f"Invalid input: {str(e)}",
                "error_type": "general",
            },
        )

    # Check 3-plan limit for logged-in users
    if current_user:
        plan_count = db.query(TrainingPlan).filter(
            TrainingPlan.user_id == current_user.id
        ).count()
        if plan_count >= 3:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "user": current_user,
                    "google_client_id": settings.google_client_id,
                    "error": "You've reached the maximum of 3 training plans. Please delete an existing plan before creating a new one.",
                    "error_type": "plan_limit",
                },
            )

    # Check for high mileage warning
    warning_message = get_mileage_warning(
        plan_request.target_distance, plan_request.current_km
    )

    try:
        # Generate training plan
        plan_data = plan_generator.generate_plan(
            plan_request.current_km,
            plan_request.target_distance,
            plan_request.weeks,
            plan_request.max_runs_per_week,
        )

        if current_user:
            user = current_user
        else:
            if anonymous_user_id:
                user = db.query(User).filter(User.id == anonymous_user_id).first()
                if not user or (user.google_id or user.email):
                    user = User()
                    db.add(user)
                    db.flush()
            else:
                user = User()
                db.add(user)
                db.flush()

        training_plan = TrainingPlan(
            user_id=user.id,
            current_weekly_km=plan_request.current_km,
            target_distance=str(plan_request.target_distance),  # Store as string for DB
            weeks_duration=plan_request.weeks,
            max_runs_per_week=plan_request.max_runs_per_week,
            plan_data=json.dumps(plan_data),
        )

        db.add(training_plan)
        db.flush()

        # Save weekly plans and daily workouts
        for week_data in plan_data:
            weekly_plan = WeeklyPlan(
                training_plan_id=training_plan.id,
                week_number=week_data["week"],
                total_km=week_data["total_km"],
                workout_types=json.dumps(week_data.get("workout_distribution", {})),
            )
            db.add(weekly_plan)
            db.flush()

            for day_workout in week_data.get("daily_workouts", []):
                daily_workout = DailyWorkout(
                    weekly_plan_id=weekly_plan.id,
                    day_of_week=day_workout["day"],
                    workout_type=day_workout["type"],
                    distance_km=day_workout.get("distance", 0),
                    intensity=day_workout.get("intensity", "low"),
                    notes=day_workout.get("notes", ""),
                )
                db.add(daily_workout)

        # Generate nutrition plan
        nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            plan_request.current_km,
            plan_request.target_distance,
        )

        # Store nutrition plan with training plan
        training_plan.nutrition_plan_data = json.dumps(nutrition_plan)

        db.commit()

        user_plans_cache.pop(f"plans_{user.id}", None)
        logger.info(f"Invalidated plans cache for user {user.id}")

        response_data = {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
            "plan": plan_data,
            "plan_id": training_plan.id,
            "training_plan": training_plan,
            "current_km": training_plan.current_weekly_km,
            "target_distance": training_plan.target_distance,
            "weeks": training_plan.weeks_duration,
            "nutrition_plan": get_nutrition_plan_for_template(
                training_plan.nutrition_plan_data
            ),
            "logged_runs": {},  # New plan has no logged runs yet
            "performance_analysis": None,
            "progress_data": None,
        }

        if warning_message:
            response_data["warning"] = warning_message

        template_response = templates.TemplateResponse("plan.html", response_data)

        if not current_user:
            template_response.set_cookie(
                key="anonymous_user_id",
                value=user.id,
                max_age=30 * 24 * 60 * 60,
                httponly=True,
                samesite="lax",
                secure=not settings.debug,
            )

        return template_response

    except PlanGenerationException as e:
        db.rollback()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": e.user_message,
                "error_type": "plan_generation",
            },
        )
    except DatabaseException as e:
        db.rollback()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": "Database error occurred. Please try again.",
                "error_type": "database",
            },
        )
    except Exception as e:
        logger.exception("Plan generation failed")
        db.rollback()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "error": f"An unexpected error occurred: {str(e)}",
                "error_type": "general",
            },
        )


@router.post("/customize-plan", response_class=HTMLResponse)
async def customize_plan(
    request: Request,
    plan_id: str = Form(...),
    week_number: int = Form(...),
    adjustment_type: str = Form(...),
    adjustment_value: str = Form(...),
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    """Handle plan customization with simple interface."""
    try:
        # Get existing plan
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(status_code=403, detail="Not authorized to modify this plan")

        plan_data = json.loads(training_plan.plan_data)

        # Get nutrition plan for template
        nutrition_plan = get_nutrition_plan_for_template(
            training_plan.nutrition_plan_data
        )

        # Apply customization based on adjustment type
        if adjustment_type == "intensity":
            plan_data = _adjust_intensity(plan_data, week_number, adjustment_value)
        elif adjustment_type == "workout_swap":
            plan_data = _swap_workout(plan_data, week_number, adjustment_value)
        elif adjustment_type == "distance":
            plan_data = _adjust_distance(plan_data, week_number, float(adjustment_value))
        elif adjustment_type == "ai_suggest":
            plan_data = _apply_ai_suggestions(plan_data, week_number, adjustment_value)

        # Track customization in database
        customization = PlanCustomizationModel(
            training_plan_id=plan_id,
            week_number=week_number,
            adjustment_type=adjustment_type,
            adjustment_value=adjustment_value,
        )
        db.add(customization)

        # Update database
        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        return templates.TemplateResponse(
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": plan_data,
                "plan_id": training_plan.id,
                "training_plan": training_plan,
                "current_km": training_plan.current_weekly_km,
                "target_distance": training_plan.target_distance,
                "weeks": training_plan.weeks_duration,
                "nutrition_plan": nutrition_plan,
                "progress_data": None,
            },
        )

    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": plan_data if "plan_data" in locals() else [],
                "plan_id": plan_id,
                "nutrition_plan": get_nutrition_plan_for_template(
                    training_plan.nutrition_plan_data
                )
                if training_plan and training_plan.nutrition_plan_data
                else {},
                "progress_data": None,
                "error": f"Error customizing plan: {str(e)}",
            },
        )


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
async def view_plan(
    plan_id: str,
    request: Request,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    nutrition_engine: NutritionEngine = Depends(get_nutrition_engine),
) -> HTMLResponse:
    """View an existing training plan."""
    try:
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(status_code=403, detail="Not authorized to view this plan")

        plan_data = json.loads(training_plan.plan_data)

        # Generate nutrition plan for existing plans if not present
        if not training_plan.nutrition_plan_data:
            nutrition_plan_raw = nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                parse_target_distance(training_plan.target_distance),
            )
            training_plan.nutrition_plan_data = json.dumps(nutrition_plan_raw)
            db.commit()

        # Transform nutrition data to template-compatible format
        nutrition_plan = get_nutrition_plan_for_template(
            training_plan.nutrition_plan_data
        )
        logger.info(f"Nutrition plan for template: {nutrition_plan}")

        # Get performance analysis
        performance_analysis = adaptation_service.analyze_performance(plan_id, db)

        # Get logged runs for this plan
        from app.models import RunLog
        logged_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan_id)
            .order_by(RunLog.date.desc())
            .all()
        )

        # Create a map of workout_id -> run for easy lookup
        logged_runs_map = {run.daily_workout_id: run for run in logged_runs if run.daily_workout_id}

        # Compute Strava fitness metrics if user has Strava connected
        strava_fitness = None
        if current_user and current_user.strava_athlete_id:
            from app.core.adaptive_plan_generator import AdaptivePlanGenerator
            adaptive_gen = AdaptivePlanGenerator()
            strava_fitness = adaptive_gen.calculate_current_fitness_metrics(
                current_user.id, db
            )

        # Compute progress data for plan vs actual charts
        progress_data = None
        if current_user and logged_runs:
            from app.services.performance_service import PerformanceService
            perf_service = PerformanceService(db)
            try:
                progress_data = perf_service.get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Could not compute progress data: {e}")

        return templates.TemplateResponse(
            "plan.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plan": plan_data,
                "plan_id": training_plan.id,
                "training_plan": training_plan,
                "current_km": training_plan.current_weekly_km,
                "target_distance": training_plan.target_distance,
                "weeks": training_plan.weeks_duration,
                "nutrition_plan": nutrition_plan,
                "performance_analysis": performance_analysis,
                "logged_runs": logged_runs_map,
                "strava_fitness": strava_fitness,
                "progress_data": progress_data,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-plans")
async def list_my_plans(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """List all training plans for current user."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    try:
        cache_key = f"plans_{current_user.id}"

        if cache_key in user_plans_cache:
            plans = user_plans_cache[cache_key]
            logger.info(f"Using cached plans for user {current_user.id}")
        else:
            plans = (
                db.query(TrainingPlan)
                .filter(TrainingPlan.user_id == current_user.id)
                .order_by(TrainingPlan.created_at.desc())
                .all()
            )
            user_plans_cache[cache_key] = plans
            logger.info(f"Cached plans for user {current_user.id}")
        
        # Parse target distance for display
        for plan in plans:
            td = parse_target_distance(plan.target_distance)
            plan.target_distance_display = DISTANCE_NAMES.get(td, f"{td}km")

        return templates.TemplateResponse(
            "my_plans.html",
            {
                "request": request,
                "user": current_user,
                "google_client_id": settings.google_client_id,
                "plans": plans,
                "plan_count": len(plans),
                "max_plans": 3,
            },
        )
    except Exception as e:
        logger.error(f"Error listing plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/plan/{plan_id}/performance")
async def get_plan_performance(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get performance analysis for a training plan."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == current_user.id
    ).first()
    
    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    analysis = adaptation_service.analyze_performance(plan_id, db)
    should_adapt, reason = adaptation_service.should_adapt_plan(plan_id, db)
    
    return {
        **analysis,
        "should_adapt": should_adapt,
        "adaptation_reason": reason
    }


@router.post("/api/plan/{plan_id}/adapt")
async def adapt_plan(
    plan_id: str,
    current_week: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adapt future weeks of a plan based on performance."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == current_user.id
    ).first()
    
    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    result = adaptation_service.adapt_future_weeks(plan_id, db, current_week)

    return result


@router.post("/api/plan/{plan_id}/adapt-from-strava")
async def adapt_plan_from_strava(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adapt future weeks of a plan based on Strava fitness metrics."""
    if not current_user.strava_athlete_id:
        raise HTTPException(status_code=400, detail="Strava not connected")

    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == current_user.id,
    ).first()

    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    result = adaptation_service.adapt_plan_from_fitness(
        plan_id, current_user.id, db
    )

    return result


@router.post("/api/plan/{plan_id}/save")
async def save_plan_to_account(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save/claim a plan to the current user's account."""
    training_plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()

    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Check if plan already belongs to this user
    if training_plan.user_id == current_user.id:
        return {"message": "Plan already saved to your account", "plan_id": plan_id}

    # Only allow claiming plans owned by anonymous users
    plan_owner = db.query(User).filter(User.id == training_plan.user_id).first()
    if plan_owner and (plan_owner.google_id or plan_owner.email):
        raise HTTPException(status_code=403, detail="This plan belongs to another user")

    # Transfer ownership to current user
    training_plan.user_id = current_user.id
    db.commit()

    return {"message": "Plan saved to your account", "plan_id": plan_id}


@router.delete("/api/plan/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a training plan owned by the current user."""
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == current_user.id,
    ).first()

    if not training_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Delete associated records (weekly plans cascade to daily workouts)
    weekly_plans = db.query(WeeklyPlan).filter(
        WeeklyPlan.training_plan_id == plan_id
    ).all()
    for wp in weekly_plans:
        db.query(DailyWorkout).filter(
            DailyWorkout.weekly_plan_id == wp.id
        ).delete()
    db.query(WeeklyPlan).filter(
        WeeklyPlan.training_plan_id == plan_id
    ).delete()

    # Delete run logs
    db.query(RunLog).filter(RunLog.training_plan_id == plan_id).delete()

    # Delete customizations
    db.query(PlanCustomizationModel).filter(
        PlanCustomizationModel.training_plan_id == plan_id
    ).delete()

    # Delete the plan itself
    db.delete(training_plan)
    db.commit()

    # Invalidate cache
    user_plans_cache.pop(f"plans_{current_user.id}", None)

    return {"message": "Plan deleted successfully"}


@router.get("/download-pdf/{plan_id}")
async def download_pdf(
    plan_id: str,
    anonymous_user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    pdf_generator: PDFGenerator = Depends(get_pdf_generator),
) -> FileResponse:
    """Download training plan as PDF."""
    try:
        # Get plan from database
        training_plan = (
            db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if not verify_plan_ownership(training_plan, current_user, anonymous_user_id):
            raise HTTPException(status_code=403, detail="Not authorized to download this plan")

        # Validate plan data exists
        if not training_plan.plan_data:
            raise HTTPException(status_code=400, detail="No training plan data found")

        # Parse plan data
        try:
            plan_data = json.loads(training_plan.plan_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid training plan data format"
            )

        if not plan_data:
            raise HTTPException(status_code=400, detail="Empty training plan data")

        # Generate PDF using ReportLab
        pdf_path = pdf_generator.generate_pdf(plan_data, training_plan)

        # Verify PDF was created
        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=500, detail="PDF generation failed - file not created"
            )

        # Check PDF file size
        file_size = os.path.getsize(pdf_path)
        if file_size < 1000:  # Should be at least 1KB for a valid PDF
            raise HTTPException(
                status_code=500, detail="PDF generation failed - file too small"
            )

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"running_plan_{plan_id}.pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF generation error")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# Helper functions for plan customization
def _adjust_intensity(
    plan_data: list[dict], week_number: int, intensity_level: str
) -> list[dict]:
    """Adjust workout intensity for a specific week."""
    for week in plan_data:
        if week["week"] == week_number:
            for workout in week.get("daily_workouts", []):
                if workout["type"] != "rest":
                    workout["intensity"] = intensity_level
                    if intensity_level == "low":
                        workout["notes"] = (
                            workout["notes"]
                            .replace("threshold", "easy")
                            .replace("tempo", "easy")
                        )
                    elif intensity_level == "high":
                        workout["notes"] = (
                            workout["notes"]
                            .replace("easy", "tempo")
                            .replace("recovery", "moderate")
                        )
    return plan_data


def _swap_workout(
    plan_data: list[dict], week_number: int, swap_info: str
) -> list[dict]:
    """Swap workout types for a specific week."""
    try:
        day, new_type = swap_info.split(",")
        day = int(day)

        for week in plan_data:
            if week["week"] == week_number:
                for workout in week.get("daily_workouts", []):
                    if workout["day"] == day:
                        old_type = workout["type"]
                        workout["type"] = new_type

                        if new_type == "rest":
                            workout["distance"] = 0
                            workout["notes"] = "Rest day for recovery"
                        elif old_type == "rest" and new_type != "rest":
                            workout["distance"] = 5.0
                            workout["notes"] = f"Easy {new_type} run - focus on form"

                        workout["intensity"] = (
                            "low" if new_type in ["rest", "easy"] else "medium"
                        )
    except (ValueError, TypeError):
        pass  # Invalid swap format, ignore

    return plan_data


def _adjust_distance(
    plan_data: list[dict], week_number: int, distance_change: float
) -> list[dict]:
    """Adjust distances for all workouts in a week."""
    for week in plan_data:
        if week["week"] == week_number:
            current_total = sum(
                w.get("distance", 0) for w in week.get("daily_workouts", [])
            )

            if current_total > 0:
                ratio = (current_total + distance_change) / current_total

                for workout in week.get("daily_workouts", []):
                    if workout["distance"] > 0:
                        workout["distance"] = round(workout["distance"] * ratio, 1)

                week["total_km"] = round(week["total_km"] + distance_change, 1)

    return plan_data


def _apply_ai_suggestions(
    plan_data: list[dict], week_number: int, preference: str
) -> list[dict]:
    """Apply AI-powered suggestions based on user preferences."""
    for week in plan_data:
        if week["week"] == week_number:
            if preference == "more_rest":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        workout["type"] = "rest"
                        workout["distance"] = 0
                        workout["notes"] = "Additional rest day for recovery"
                        week["total_km"] = round(
                            week["total_km"] - workout.get("distance", 0), 1
                        )
                        break

            elif preference == "more_speed":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        workout["type"] = "interval"
                        workout["intensity"] = "high"
                        workout["notes"] = (
                            "Speed work: 6x400m at 5K pace with 400m recovery"
                        )
                        break

            elif preference == "more_endurance":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "long":
                        workout["distance"] = round(workout["distance"] * 1.2, 1)
                        week["total_km"] = round(
                            week["total_km"] + (workout["distance"] * 0.2), 1
                        )
                        workout["notes"] = (
                            f'Extended long run: {workout["distance"]}km at '
                            "conversational pace"
                        )
                        break

    return plan_data
