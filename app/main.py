"""RunCoach — FastAPI application entry point (composition root)."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.infrastructure.config import settings, setup_logging
from app.infrastructure.health import (
    HealthProbe,
    HealthResponse,
    LivenessResponse,
    get_health_probe,
)
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
    admin_router,
    analytics_page_router,
    analytics_router,
    auth_router,
    intervals_router,
    notifications_router,
    nutrition_router,
    pages_router,
    performance_page_router,
    plans_router,
    push_router,
    readiness_router,
    recipes_page_router,
    recipes_router,
    runs_router,
    scheduled_router,
    single_runs_router,
)

setup_logging(settings)
logger = logging.getLogger(__name__)

_ROUTERS = (
    plans_router,
    nutrition_router,
    recipes_router,
    recipes_page_router,
    auth_router,
    runs_router,
    readiness_router,
    performance_page_router,
    analytics_router,
    analytics_page_router,
    intervals_router,
    admin_router,
    notifications_router,
    push_router,
    scheduled_router,
    single_runs_router,
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


def create_app(skip_migrations: Optional[bool] = None) -> FastAPI:
    """Application factory — creates and configures the FastAPI app.

    ``skip_migrations`` defaults to the inverse of ``RUN_STARTUP_MIGRATIONS``
    (on in production, pinned off for the whole test session in conftest). It is
    deliberately *not* inferred from ``"pytest" in sys.modules``: any process
    that happened to import pytest — a plugin, a profiler — would silently boot
    without migrations, and the old form also skipped
    ``validate_production_secrets``, so a production process could come up with
    a weak JWT key and no complaint.

    Production-secret validation is therefore unconditional: it is pure config
    checking with no I/O, and it is exactly the check that must never be
    skippable.
    """
    effective_skip = (
        not settings.run_startup_migrations
        if skip_migrations is None
        else skip_migrations
    )

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

        validate_production_secrets()
        if not effective_skip:
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

    def _readiness_verdict(response: Response, probe: HealthProbe) -> HealthResponse:
        """Run the dependency probe and turn its verdict into a status code.

        Shared by ``/health`` and ``/health/ready`` so the two cannot drift.
        """
        reason = probe()
        if reason is None:
            return HealthResponse(checks={"database": "ok"})

        logger.warning("Readiness check degraded: database probe failed: %s", reason)
        response.status_code = 503
        return HealthResponse(status="degraded", checks={"database": reason})

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
        tags=["health"],
    )
    async def health_check(
        response: Response,
        probe: HealthProbe = Depends(get_health_probe),
    ) -> HealthResponse:
        """Readiness, kept at this path for existing monitors.

        Reports whether this machine can actually serve a request, not merely
        that the process is up: 503 (not 200) when a dependency is down, so the
        proxy takes the machine out of rotation and the failure is visible to
        anything watching the endpoint rather than only to the users hitting
        500s. ``/health/ready`` is the same check under its canonical name.
        """
        return _readiness_verdict(response, probe)

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
        tags=["health"],
    )
    async def readiness_check(
        response: Response,
        probe: HealthProbe = Depends(get_health_probe),
    ) -> HealthResponse:
        """Can this machine serve a request? Consults every dependency.

        This is the check the Fly proxy reads, so a machine whose volume failed
        to mount is taken out of rotation instead of answering 500s.
        """
        return _readiness_verdict(response, probe)

    @app.get(
        "/health/live",
        response_model=LivenessResponse,
        tags=["health"],
    )
    async def liveness_check() -> LivenessResponse:
        """Is this process up? Deliberately does no I/O.

        Fly restarts a machine whose liveness check fails, which is the right
        response to a wedged process and the wrong one to a missing volume — so
        this endpoint must not consult the database, or a storage outage would
        cycle the fleet instead of draining it.
        """
        return LivenessResponse()

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
