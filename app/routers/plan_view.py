"""Plan viewing endpoint."""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.nutrition.nutrition_engine import NutritionEngine
from app.dependencies import (
    get_db,
    get_nutrition_engine,
    get_optional_user,
    get_plan_service,
)
from app.models import User
from app.services.adaptation import AdaptationService
from app.services.fitness.hr_zone_service import HRZoneService
from app.services.fitness.performance_service import PerformanceService
from app.services.plans.plan_helpers import get_plan_or_404, plan_view_context
from app.services.plans.plan_service import PlanService
from app.template_helpers import create_templates
from app.utils import format_pace

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
                user = current_user or db.query(User).filter(
                    User.id == training_plan.user_id
                ).first()
                if user:
                    zones = HRZoneService.compute_and_store_zones(
                        training_plan, user, db
                    )
                    HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
                    training_plan.plan_data = plan_data
                    db.commit()
            except Exception as e:
                logger.warning(f"Retroactive HR zone computation failed: {e}")

        extra = plan_service.get_plan_view_data(training_plan, current_user, db)

        if training_plan.plan_type == "performance":
            try:
                perf_service = PerformanceService(db)
                from app.core.generators.performance_plan_generator import PerformancePlanGenerator
                gen = PerformancePlanGenerator()
                zones = gen.calculate_training_zones(
                    training_plan.goal_pace, training_plan.max_heart_rate
                )
                for zone_data in zones.values():
                    zone_data["pace_formatted"] = format_pace(zone_data["pace"])
                    if "pace_range" in zone_data:
                        pr = zone_data["pace_range"]
                        zone_data["pace_range_formatted"] = (
                            f"{format_pace(pr[0])} - {format_pace(pr[1])}"
                        )
                extra["training_zones"] = zones
                extra["today_workout"] = perf_service.get_todays_workout(training_plan)
                extra["perf_progress_data"] = perf_service.get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Performance context enrichment failed: {e}")

        if training_plan.plan_type == "fitness":
            try:
                from app.core.generators.fitness_plan_generator import FitnessPlanGenerator
                from app.core.training.vdot_calculator import VDOTCalculator
                gen = FitnessPlanGenerator()
                vdot = training_plan.vdot
                zones = gen.calculate_training_zones(vdot, training_plan.max_heart_rate)
                for zone_data in zones.values():
                    zone_data["pace_formatted"] = format_pace(zone_data["pace"])
                    if "pace_range" in zone_data:
                        pr = zone_data["pace_range"]
                        zone_data["pace_range_formatted"] = (
                            f"{format_pace(pr[0])} - {format_pace(pr[1])}"
                        )
                extra["training_zones"] = zones
                focus_area = training_plan.target_distance.replace("fitness_", "") if training_plan.target_distance.startswith("fitness_") else "vo2max"
                extra["fitness_focus_area"] = focus_area
                phase_durations = gen._calculate_fitness_phases(
                    training_plan.weeks_duration, focus_area
                )
                from app.core.generators.fitness_plan_generator import _PHASE_METADATA
                extra["phases"] = {
                    phase: {"weeks": phase_durations[phase], **_PHASE_METADATA[phase]}
                    for phase in phase_durations
                }
                time_trial_weeks = []
                for week_data in plan_data:
                    if week_data.get("is_time_trial_week"):
                        for dw in week_data.get("daily_workouts", []):
                            if dw.get("type") == "time_trial":
                                time_trial_weeks.append({
                                    "week": week_data["week"],
                                    "distance": dw.get("distance", 0),
                                    "description": dw.get("description", ""),
                                })
                extra["time_trial_weeks"] = time_trial_weeks
                if vdot:
                    vdot_zones = VDOTCalculator.get_pace_zones(vdot)
                    extra["vdot_zones"] = vdot_zones
            except Exception as e:
                logger.warning(f"Fitness context enrichment failed: {e}")

        ctx = plan_view_context(
            request, current_user, training_plan, plan_data, nutrition_plan, db=db, **extra
        )
        return templates.TemplateResponse("plan.html", ctx)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while generating the plan")
