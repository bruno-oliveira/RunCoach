"""RunCoach - Personalized Running Training Plan Generator.

FastAPI application entry point.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, setup_logging
from app.dependencies import get_db, get_optional_user
from app.middleware import csrf_protection, request_size_limit, security_headers, set_anonymous_user_id_cookie
from app.models import Base, User
from app.template_helpers import create_templates
from app.routers import (
    analytics_page_router,
    analytics_router,
    auth_router,
    nutrition_router,
    performance_router,
    performance_page_router,
    plans_router,
    race_prep_router,
    readiness_router,
    recipes_router,
    recipes_page_router,
    runs_router,
    strava_router,
    triathlon_router,
    triathlon_page_router,
)
from app.schemas import HealthResponse
from app.migrations import run_alembic_migrations
from app.migrations.vdot_backfill import backfill_vdot
from app.services.cleanup_service import cleanup_inactive_accounts
from app.dependencies import engine, SessionLocal

setup_logging(settings)
logger = logging.getLogger(__name__)

_is_test_mode = "pytest" in __import__("sys").modules


class CachedStaticFiles(StaticFiles):
    """Static files with cache control headers."""
    def __init__(self, *args, cache_max_age: int = 86400, **kwargs):
        self.cache_max_age = cache_max_age
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response


def _validate_production_secrets() -> None:
    """Validate that required secrets are properly configured."""
    if not os.environ.get("SECRET_KEY"):
        logger.warning(
            "SECRET_KEY not set via environment variable — using random default. "
            "JWTs will be invalidated on every restart. "
            "Set SECRET_KEY as a persistent secret (e.g. `fly secrets set SECRET_KEY=...`)."
        )
    if not os.environ.get("ENCRYPTION_KEY"):
        logger.warning(
            "ENCRYPTION_KEY not set — falling back to SECRET_KEY for data encryption. "
            "Set a separate ENCRYPTION_KEY for defense-in-depth."
        )
    if not settings.debug:
        weak_patterns = ["dev-secret", "your-secret", "change-in-production", "placeholder"]
        key = settings.secret_key
        if len(key) < 32 or any(p in key.lower() for p in weak_patterns):
            raise RuntimeError(
                "SECRET_KEY is too weak for production. "
                "Set a random key of at least 32 characters."
            )


def _run_startup_migrations() -> None:
    """Apply database migrations, data backfills, and retention cleanup."""
    run_alembic_migrations(engine)

    session = SessionLocal()
    try:
        backfill_vdot(session)
    except Exception as e:
        session.rollback()
        logger.warning("VDOT backfill failed: %s", e)

    try:
        from app.services.fitness.effort_classifier import backfill_effort_classes

        updated = backfill_effort_classes(session)
        if updated:
            session.commit()
            logger.info("Effort-class backfill updated %d runs", updated)
    except Exception as e:
        session.rollback()
        logger.warning("Effort-class backfill failed: %s", e)

    try:
        cleanup_inactive_accounts(session)
    except Exception as e:
        session.rollback()
        logger.warning("Inactive account cleanup failed: %s", e)
    finally:
        session.close()


def create_app(skip_migrations: bool = False) -> FastAPI:
    """Application factory — creates and configures the FastAPI app."""

    effective_skip = skip_migrations or _is_test_mode

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logger.info("Starting %s v%s", settings.app_name, settings.app_version)
        logger.info("Debug mode: %s", settings.debug)

        if settings.is_google_client_id_configured:
            logger.info("Google Client ID is properly configured")
        else:
            logger.warning("Google Client ID is not configured — Google Sign-In will not work")

        if not effective_skip:
            _validate_production_secrets()
            _run_startup_migrations()

        yield

        logger.info("Shutting down %s", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        description="Personalized Running Plan Generator with Nutrition Guidance",
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.middleware("http")(set_anonymous_user_id_cookie)
    app.middleware("http")(csrf_protection)
    app.middleware("http")(request_size_limit)
    app.middleware("http")(security_headers)

    app.mount("/static", CachedStaticFiles(
        directory="app/static",
        cache_max_age=86400
    ), name="static")

    app.include_router(plans_router)
    app.include_router(nutrition_router)
    app.include_router(recipes_router)
    app.include_router(recipes_page_router)
    app.include_router(auth_router)
    app.include_router(runs_router)
    app.include_router(performance_router)
    app.include_router(performance_page_router)
    app.include_router(analytics_router)
    app.include_router(analytics_page_router)
    app.include_router(strava_router)
    app.include_router(triathlon_router)
    app.include_router(triathlon_page_router)
    app.include_router(readiness_router)
    app.include_router(race_prep_router)

    templates = create_templates()

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        return HealthResponse()

    @app.get("/", response_class=HTMLResponse, tags=["pages"])
    async def home(
        request: Request,
        current_user: Optional[User] = Depends(get_optional_user),
        db=Depends(get_db),
    ) -> HTMLResponse:
        has_profile = False
        if current_user:
            from datetime import datetime, timedelta, timezone
            from app.models.run_log import RunLog
            cutoff = (datetime.now(timezone.utc) - timedelta(weeks=12)).replace(tzinfo=None)
            run_count = (
                db.query(RunLog.id)
                .filter(RunLog.user_id == current_user.id, RunLog.date >= cutoff)
                .limit(3)
                .count()
            )
            has_profile = run_count >= 3

        return templates.TemplateResponse("index.html", {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "has_profile": has_profile,
        })

    @app.get("/privacy", response_class=HTMLResponse, tags=["pages"])
    async def privacy_policy(
        request: Request,
        current_user: Optional[User] = Depends(get_optional_user),
    ) -> HTMLResponse:
        return templates.TemplateResponse("privacy.html", {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
        })

    if settings.enable_debug_endpoints:
        @app.get("/debug/config", tags=["debug"])
        async def debug_config():
            return {
                "google_client_id_configured": settings.is_google_client_id_configured,
                "debug_mode": settings.debug,
                "environment": "development",
            }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
