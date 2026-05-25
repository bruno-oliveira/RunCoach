"""Stateless service factories — cached one-per-process."""

from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.contexts.nutrition.favorites_service import FavoritesService
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import PlanService
from app.contexts.runner.fitness.performance_service import PerformanceService
from app.domain.coaching import CoachNarrator
from app.infrastructure.config import settings
from app.infrastructure.database import get_db
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.integrations.strava_service import StravaService


@lru_cache
def get_plan_generator() -> TrainingPlanGenerator:
    return TrainingPlanGenerator()


@lru_cache
def get_pdf_generator() -> PDFGenerator:
    return PDFGenerator()


@lru_cache
def get_performance_plan_generator() -> PerformancePlanGenerator:
    return PerformancePlanGenerator()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


@lru_cache
def get_plan_service() -> PlanService:
    return PlanService()


@lru_cache
def get_strava_service() -> StravaService:
    return StravaService()


@lru_cache
def get_adaptation_service() -> AdaptationService:
    return AdaptationService()


@lru_cache
def get_favorites_service() -> FavoritesService:
    return FavoritesService()


def get_nutrition_engine(random_seed: int | None = None) -> NutritionEngine:
    """NutritionEngine is reseedable per-request; do not cache."""
    return NutritionEngine(random_seed=random_seed)


def get_performance_service(db: Session = Depends(get_db)) -> PerformanceService:
    """PerformanceService holds a DB session, so it must be per-request."""
    return PerformanceService(db)


class _NullCoachNarrator:
    """Fallback narrator when the Coach AI is disabled — always defers to the
    deterministic note."""

    def generate_note(self, context: dict[str, Any]) -> Optional[str]:
        return None


@lru_cache
def get_coach_narrator() -> CoachNarrator:
    """The Coach's Note narrator. AI-backed when an Anthropic key is configured,
    otherwise a null narrator so the feature degrades to the deterministic note.

    Cached one-per-process so the narrator's TTL cache is shared across requests.
    """
    if settings.is_coach_ai_enabled:
        from app.infrastructure.integrations.anthropic_narrator import (
            AnthropicCoachNarrator,
        )

        return AnthropicCoachNarrator(
            api_key=settings.anthropic_api_key, model=settings.coach_ai_model
        )
    return _NullCoachNarrator()


__all__ = [
    "get_plan_generator",
    "get_pdf_generator",
    "get_performance_plan_generator",
    "get_auth_service",
    "get_plan_service",
    "get_strava_service",
    "get_adaptation_service",
    "get_favorites_service",
    "get_nutrition_engine",
    "get_performance_service",
    "get_coach_narrator",
]
