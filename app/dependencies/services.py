"""Stateless service factories — cached one-per-process."""

from functools import lru_cache

from app.application.plan_view_service import PlanViewService
from app.contexts.auth.auth_service import AuthService
from app.contexts.nutrition.favorites_service import FavoritesService
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import PlanService
from app.infrastructure.export.pdf_generator import PDFGenerator
from app.infrastructure.integrations.intervals_service import IntervalsService


@lru_cache
def get_plan_generator() -> TrainingPlanGenerator:
    return TrainingPlanGenerator()


@lru_cache
def get_pdf_generator() -> PDFGenerator:
    return PDFGenerator()


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


@lru_cache
def get_plan_service() -> PlanService:
    return PlanService()


@lru_cache
def get_plan_view_service() -> PlanViewService:
    return PlanViewService()


@lru_cache
def get_intervals_service() -> IntervalsService:
    return IntervalsService()


@lru_cache
def get_adaptation_service() -> AdaptationService:
    return AdaptationService()


@lru_cache
def get_favorites_service() -> FavoritesService:
    return FavoritesService()


def get_nutrition_engine(random_seed: int | None = None) -> NutritionEngine:
    """NutritionEngine is reseedable per-request; do not cache."""
    return NutritionEngine(random_seed=random_seed)


__all__ = [
    "get_plan_generator",
    "get_pdf_generator",
    "get_auth_service",
    "get_plan_service",
    "get_plan_view_service",
    "get_intervals_service",
    "get_adaptation_service",
    "get_favorites_service",
    "get_nutrition_engine",
]
