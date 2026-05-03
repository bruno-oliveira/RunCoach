"""Plan creation, customization, and deletion business logic."""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.generators.plan_generator import TrainingPlanGenerator
from app.config import settings
from app.models import TrainingPlan, User
from app.schemas import PlanRequest
from app.services.adaptation import AdaptationService
from .plan_view_service import PlanViewService
from app.utils import parse_race_time_to_seconds

from . import plan_creation_helpers as _create
from . import plan_lifecycle_service as _lifecycle

logger = logging.getLogger(__name__)


class PlanService:
    """Encapsulates plan lifecycle operations."""

    MAX_PLANS_PER_USER = settings.max_plans_per_user

    def __init__(self) -> None:
        self._adaptation_service = AdaptationService()
        self._plan_view_service = PlanViewService()

    def has_reached_plan_limit(self, user_id: str, db: Session) -> bool:
        return _lifecycle.has_reached_plan_limit(user_id, db)

    def get_or_create_anonymous_user(self,
        current_user: Optional[User],
        anonymous_user_id: Optional[str],
        db: Session,
    ) -> User:
        if current_user:
            return current_user

        if anonymous_user_id:
            user = db.query(User).filter(User.id == anonymous_user_id).first()
            if user and not user.google_id and not user.email:
                return user

        user = User(id=anonymous_user_id) if anonymous_user_id else User()
        db.add(user)
        db.flush()
        return user

    def find_duplicate(self,
        plan_request: PlanRequest,
        user_id: str,
        db: Session,
    ) -> Optional[TrainingPlan]:
        race_time_seconds = (
            parse_race_time_to_seconds(plan_request.recent_race_time)
            if plan_request.recent_race_time
            else None
        )
        filters = [
            TrainingPlan.user_id == user_id,
            TrainingPlan.current_weekly_km == plan_request.current_km,
            TrainingPlan.target_distance == str(plan_request.target_distance),
            TrainingPlan.weeks_duration == plan_request.weeks,
            TrainingPlan.max_runs_per_week == plan_request.max_runs_per_week,
        ]
        if plan_request.body_weight_kg is not None:
            filters.append(TrainingPlan.body_weight_kg == plan_request.body_weight_kg)
        else:
            filters.append(TrainingPlan.body_weight_kg.is_(None))
        if plan_request.recent_race_distance_km is not None:
            filters.append(
                TrainingPlan.recent_race_distance_km == plan_request.recent_race_distance_km
            )
        else:
            filters.append(TrainingPlan.recent_race_distance_km.is_(None))
        if race_time_seconds is not None:
            filters.append(TrainingPlan.recent_race_time_seconds == race_time_seconds)
        else:
            filters.append(TrainingPlan.recent_race_time_seconds.is_(None))
        if plan_request.vdot is not None:
            filters.append(TrainingPlan.vdot == plan_request.vdot)
        else:
            filters.append(TrainingPlan.vdot.is_(None))
        return db.query(TrainingPlan).filter(*filters).first()

    def create_plan(self,
        plan_request: PlanRequest,
        user: User,
        db: Session,
        plan_generator: TrainingPlanGenerator,
        nutrition_engine: NutritionEngine,
        profile: Optional[dict] = None,
    ) -> tuple[TrainingPlan, list[dict]]:
        existing = self.find_duplicate(plan_request, user.id, db)
        if existing:
            logger.info(
                f"Duplicate plan detected for user {user.id} — returning existing plan {existing.id}"
            )
            return existing, existing.plan_data if existing.plan_data else []

        effective_vdot = plan_request.goal_vdot or plan_request.vdot
        plan_data = plan_generator.generate_plan(
            plan_request.current_km,
            plan_request.target_distance,
            plan_request.weeks,
            plan_request.max_runs_per_week,
            vdot=effective_vdot,
            profile=profile,
            terrain=plan_request.terrain,
        )

        try:
            training_plan = _create.persist_plan_core(plan_request, user, plan_data, db)
            _create.persist_weekly_workouts(training_plan, plan_data, db)
            _create.attach_hr_zones(training_plan, user, plan_data, db)
            _create.attach_nutrition(training_plan, plan_request, plan_data, nutrition_engine)
            _create.attach_race_protocol(training_plan, plan_request)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return training_plan, plan_data

    def customize_plan(self, training_plan, week_number, adjustment_type, adjustment_value, db):
        return _lifecycle.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )

    def delete_plan(self, training_plan, db):
        return _lifecycle.delete_plan(training_plan, db)

    # Delegation to PlanViewService — kept for backward compatibility
    def enrich_plan_data_with_ids(self, plan_data, training_plan_id, db):
        return self._plan_view_service.enrich_plan_data_with_ids(plan_data, training_plan_id, db)

    def nutrition_for_template(self, nutrition_plan_data):
        return self._plan_view_service.nutrition_for_template(nutrition_plan_data)

    def get_logged_runs_map(self, training_plan_id, db):
        return self._plan_view_service.get_logged_runs_map(training_plan_id, db)

    def get_adjustment_hints(self, training_plan, performance_analysis, db):
        return self._plan_view_service.get_adjustment_hints(training_plan, performance_analysis, db)

    def get_feedback_map(self, logged_runs, db):
        return self._plan_view_service.get_feedback_map(logged_runs, db)

    def get_completion_stats(self, training_plan, db):
        return self._plan_view_service.get_completion_stats(training_plan, db)

    def get_next_plan_cta(self, target_distance_km):
        return self._plan_view_service.get_next_plan_cta(target_distance_km)

    def get_plan_view_data(self, training_plan, current_user, db):
        return self._plan_view_service.get_plan_view_data(training_plan, current_user, db)
