"""Plan creation, customization, and deletion business logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.domain.repositories import IPlanRepository, IUserRepository
from app.infrastructure.config import settings
from app.models import TrainingPlan, User
from app.schemas import PlanRequest
from app.utils import parse_race_time_to_seconds

from . import plan_creation_helpers as _create
from . import plan_lifecycle_service as _lifecycle

if TYPE_CHECKING:
    # Type-only: the engine is injected by the caller, so the plan context does
    # not depend on the nutrition context at runtime.
    from app.application.ports import NutritionEngine

logger = logging.getLogger(__name__)


def _default_user_repo_factory(db: Session) -> IUserRepository:
    """Lazy default so the plan context carries no static edge to the auth
    context's concrete repository — the composition root can still override it."""
    from app.application.ports import SQLAlchemyUserRepository

    return SQLAlchemyUserRepository(db)


class PlanService:
    """Encapsulates plan lifecycle operations.

    Accepts repository factories so tests / non-SQLAlchemy adapters can supply
    their own implementations of the IPlanRepository / IUserRepository protocols.
    """

    MAX_PLANS_PER_USER = settings.max_plans_per_user

    def __init__(
        self,
        plan_repo_factory: Callable[
            [Session], IPlanRepository
        ] = SQLAlchemyPlanRepository,
        user_repo_factory: Callable[
            [Session], IUserRepository
        ] = _default_user_repo_factory,
    ) -> None:
        self._adaptation_service = AdaptationService()
        self._plan_repo_factory = plan_repo_factory
        self._user_repo_factory = user_repo_factory

    def has_reached_plan_limit(self, user_id: str, db: Session) -> bool:
        return _lifecycle.has_reached_plan_limit(user_id, db)

    def get_or_create_anonymous_user(
        self,
        current_user: Optional[User],
        anonymous_user_id: Optional[str],
        db: Session,
    ) -> User:
        if current_user:
            return current_user

        if anonymous_user_id:
            user = self._user_repo_factory(db).get_by_id(anonymous_user_id)
            if user and not user.google_id and not user.email:
                return user

        user = User(id=anonymous_user_id) if anonymous_user_id else User()
        db.add(user)
        db.flush()
        return user

    def find_duplicate(
        self,
        plan_request: PlanRequest,
        user_id: str,
        db: Session,
    ) -> Optional[TrainingPlan]:
        race_time_seconds = (
            parse_race_time_to_seconds(plan_request.recent_race_time)
            if plan_request.recent_race_time
            else None
        )
        return self._plan_repo_factory(db).find_duplicate(
            user_id, plan_request, race_time_seconds
        )

    def create_plan(
        self,
        plan_request: PlanRequest,
        user: User,
        db: Session,
        plan_generator: TrainingPlanGenerator,
        nutrition_engine: NutritionEngine,
    ) -> tuple[TrainingPlan, list[dict]]:
        existing = self.find_duplicate(plan_request, user.id, db)
        if existing:
            logger.info(
                "Duplicate plan detected for user %s — returning existing plan %s",
                user.id,
                existing.id,
            )
            return existing, existing.plan_data if existing.plan_data else []

        effective_vdot = plan_request.goal_vdot or plan_request.vdot

        trail_profile = None
        if plan_request.is_trail:
            from app.core.training.trail_profile import classify_trail

            trail_profile = classify_trail(
                plan_request.target_distance,
                plan_request.target_elevation_gain_m or 0.0,
            )

        plan_data = plan_generator.generate_plan(
            plan_request.current_km,
            plan_request.target_distance,
            plan_request.weeks,
            plan_request.max_runs_per_week,
            vdot=effective_vdot,
            terrain=plan_request.resolved_training_terrain(),
            trail_profile=trail_profile,
            intensive_weekend_enabled=plan_request.intensive_weekend_enabled,
        )

        try:
            training_plan = _create.persist_plan_core(plan_request, user, plan_data, db)
            _create.persist_weekly_workouts(training_plan, plan_data, db)
            # Persist the stated race before zones so the LTHR estimate and the
            # stored HR zones are grounded on the number the runner gave us.
            _create.persist_race_effort_run(plan_request, user, db)
            _create.attach_hr_zones(training_plan, user, plan_data, db)
            _create.attach_nutrition(
                training_plan, plan_request, plan_data, nutrition_engine
            )
            _create.attach_race_protocol(training_plan, plan_request)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return training_plan, plan_data

    def customize_plan(
        self,
        training_plan: TrainingPlan,
        week_number: int,
        adjustment_type: str,
        adjustment_value: str,
        db: Session,
    ) -> Any:
        return _lifecycle.customize_plan(
            training_plan, week_number, adjustment_type, adjustment_value, db
        )

    def delete_plan(self, training_plan: TrainingPlan, db: Session) -> None:
        return _lifecycle.delete_plan(training_plan, db)
