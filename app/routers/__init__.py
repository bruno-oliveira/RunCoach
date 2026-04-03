"""API routers for RunCoach application."""

from app.routers.adaptive import adaptive_router
from app.routers.auth import auth_router
from app.routers.nutrition import router as nutrition_router
from app.routers.plans import router as plans_router
from app.routers.recipes import router as recipes_router
from app.routers.runs import runs_router
from app.routers.performance import router as performance_router
from app.routers.analytics import analytics_router, analytics_page_router
from app.routers.strava import strava_router
from app.routers.triathlon import router as triathlon_router

__all__ = ["adaptive_router", "auth_router", "plans_router", "nutrition_router", "recipes_router", "runs_router", "performance_router", "analytics_router", "analytics_page_router", "strava_router", "triathlon_router"]
