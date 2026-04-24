"""API routers for RunCoach application."""

from app.routers.auth import auth_router
from app.routers.nutrition import router as nutrition_router
from app.routers.plans import router as plans_router
from app.routers.readiness import router as readiness_router
from app.routers.recipes import router as recipes_router
from app.routers.recipes_pages import router as recipes_page_router
from app.routers.runs import runs_router
from app.routers.performance import router as performance_router
from app.routers.performance_pages import router as performance_page_router
from app.routers.analytics import analytics_router
from app.routers.analytics_pages import router as analytics_page_router
from app.routers.strava import strava_router
from app.routers.triathlon import router as triathlon_router
from app.routers.triathlon_pages import router as triathlon_page_router

__all__ = [
    "auth_router",
    "plans_router",
    "nutrition_router",
    "readiness_router",
    "recipes_router",
    "recipes_page_router",
    "runs_router",
    "performance_router",
    "performance_page_router",
    "analytics_router",
    "analytics_page_router",
    "strava_router",
    "triathlon_router",
    "triathlon_page_router",
]
