"""API routers for RunCoach application."""

from app.web.routers.admin import admin_router
from app.web.routers.analytics import analytics_router
from app.web.routers.analytics_pages import router as analytics_page_router
from app.web.routers.auth import auth_router
from app.web.routers.intervals import intervals_router
from app.web.routers.nutrition import router as nutrition_router
from app.web.routers.pages import router as pages_router
from app.web.routers.performance_pages import router as performance_page_router
from app.web.routers.plans import router as plans_router
from app.web.routers.readiness import readiness_router
from app.web.routers.recipes import router as recipes_router
from app.web.routers.recipes_pages import router as recipes_page_router
from app.web.routers.runs import runs_router
from app.web.routers.strava import strava_router

__all__ = [
    "admin_router",
    "auth_router",
    "intervals_router",
    "plans_router",
    "nutrition_router",
    "pages_router",
    "recipes_router",
    "recipes_page_router",
    "runs_router",
    "readiness_router",
    "performance_page_router",
    "analytics_router",
    "analytics_page_router",
    "strava_router",
]
