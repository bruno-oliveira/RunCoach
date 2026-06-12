"""RunCoach — FastAPI application entry point (composition root)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.infrastructure.config import settings, setup_logging
from app.infrastructure.health import HealthResponse
from app.infrastructure.secrets import validate_production_secrets
from app.migrations.startup import run_startup_migrations
from app.web.exception_handlers import register_exception_handlers
from app.web.middleware import (
    csrf_protection,
    request_size_limit,
    request_timezone,
    security_headers,
    set_anonymous_user_id_cookie,
)
from app.web.routers import (
    analytics_page_router,
    analytics_router,
    auth_router,
    nutrition_router,
    pages_router,
    performance_page_router,
    performance_router,
    plans_router,
    race_prep_router,
    readiness_router,
    recipes_page_router,
    recipes_router,
    runs_router,
    strava_router,
)

setup_logging(settings)
logger = logging.getLogger(__name__)

_is_test_mode = "pytest" in __import__("sys").modules

_ROUTERS = (
    plans_router,
    nutrition_router,
    recipes_router,
    recipes_page_router,
    auth_router,
    runs_router,
    performance_router,
    performance_page_router,
    analytics_router,
    analytics_page_router,
    strava_router,
    readiness_router,
    race_prep_router,
    pages_router,
)


class CachedStaticFiles(StaticFiles):
    """Static files with cache-control headers."""

    def __init__(self, *args, cache_max_age: int = 86400, **kwargs):
        self.cache_max_age = cache_max_age
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response


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
            logger.warning(
                "Google Client ID is not configured — Google Sign-In will not work"
            )

        if not effective_skip:
            validate_production_secrets()
            run_startup_migrations()

        yield
        logger.info("Shutting down %s", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        description="Personalized Running Plan Generator with Nutrition Guidance",
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "X-Timezone",
        ],
    )
    app.middleware("http")(set_anonymous_user_id_cookie)
    app.middleware("http")(csrf_protection)
    app.middleware("http")(request_size_limit)
    app.middleware("http")(security_headers)
    app.middleware("http")(request_timezone)

    app.mount(
        "/static",
        CachedStaticFiles(directory="app/web/static", cache_max_age=86400),
        name="static",
    )

    for router in _ROUTERS:
        app.include_router(router)

    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
