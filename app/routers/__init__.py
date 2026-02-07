"""API routers for RunCoach application."""

from app.routers.auth import auth_router
from app.routers.nutrition import router as nutrition_router
from app.routers.plans import router as plans_router
from app.routers.recipes import router as recipes_router
from app.routers.runs import adaptive_router, runs_router
from app.routers.strength import router as strength_router
from app.routers.analytics import analytics_router, analytics_page_router

__all__ = ["auth_router", "plans_router", "nutrition_router", "recipes_router", "runs_router", "adaptive_router", "strength_router", "analytics_router", "analytics_page_router"]
