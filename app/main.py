"""RunCoach - Personalized Running Training Plan Generator.

FastAPI application entry point.
"""

import logging
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, setup_logging
from app.dependencies import engine, get_optional_user
from app.models import Base, User
from app.template_helpers import create_templates
from app.routers import (
    adaptive_router,
    analytics_page_router,
    analytics_router,
    auth_router,
    nutrition_router,
    performance_router,
    plans_router,
    recipes_router,
    runs_router,
    strava_router,
    triathlon_router,
)
from app.schemas import HealthResponse


class CachedStaticFiles(StaticFiles):
    """Static files with cache control headers."""
    def __init__(self, *args, cache_max_age: int = 86400, **kwargs):
        self.cache_max_age = cache_max_age
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response

# Setup logging
setup_logging(settings)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Personalized Running Plan Generator with Nutrition Guidance",
    version=settings.app_version,
    debug=settings.debug,
)


@app.middleware("http")
async def set_anonymous_user_id_cookie(request: Request, call_next):
    """Set anonymous_user_id cookie if not present and add it to request state."""
    anonymous_user_id = request.cookies.get("anonymous_user_id")
    generated_new_id = False
    
    if not anonymous_user_id:
        import uuid
        anonymous_user_id = str(uuid.uuid4())
        generated_new_id = True
    
    # Store the ID in request state so endpoints can access it
    request.state.anonymous_user_id = anonymous_user_id
    request.state.generated_new_anonymous_id = generated_new_id
    
    response = await call_next(request)
    
    # Only set cookie if we generated a new ID
    if generated_new_id:
        response.set_cookie(
            key="anonymous_user_id",
            value=anonymous_user_id,
            max_age=30 * 24 * 60 * 60,  # 30 days
            httponly=True,
            samesite="lax",
            secure=not settings.debug,
        )
    
    return response

# Create database tables
Base.metadata.create_all(bind=engine)

# Lightweight column migrations for existing databases
# ALTER TABLE ADD COLUMN is a no-op if the column already exists (handled by try/except)
from sqlalchemy import text as _sa_text


def _run_migrations(eng) -> None:
    """Apply ADD COLUMN migrations; silently skip columns that already exist."""
    stmts = [
        "ALTER TABLE users ADD COLUMN strava_last_synced_at INTEGER",
        # VDOT / pace zone fields
        "ALTER TABLE training_plans ADD COLUMN body_weight_kg FLOAT",
        "ALTER TABLE training_plans ADD COLUMN recent_race_distance_km FLOAT",
        "ALTER TABLE training_plans ADD COLUMN recent_race_time_seconds INTEGER",
        "ALTER TABLE training_plans ADD COLUMN vdot FLOAT",
        "ALTER TABLE training_plans ADD COLUMN nutrition_phases_data TEXT",
        "ALTER TABLE training_plans ADD COLUMN race_protocol_data TEXT",
        # Coaching notes
        "ALTER TABLE daily_workouts ADD COLUMN coaching_rationale TEXT",
        # Effort quality scoring
        "ALTER TABLE run_logs ADD COLUMN effort_quality_score FLOAT",
        "ALTER TABLE run_logs ADD COLUMN quality_label VARCHAR(20)",
        "ALTER TABLE run_logs ADD COLUMN planned_pace_min_km FLOAT",
        # Baseline distances for non-compounding adaptations
        "ALTER TABLE daily_workouts ADD COLUMN baseline_distance_km FLOAT",
        "ALTER TABLE training_plans ADD COLUMN recalibration_multiplier FLOAT",
        # Unified adaptation multiplier (Phase 1 of simplified adaptation)
        "ALTER TABLE training_plans ADD COLUMN adjustment_multiplier FLOAT",
        # HR zones (Feature: Heart Rate Zone Training)
        "ALTER TABLE training_plans ADD COLUMN hr_zones_data TEXT",
        "ALTER TABLE daily_workouts ADD COLUMN hr_zone_target INTEGER",
        # Key workout library (Feature: Race-Specific Key Workouts)
        "ALTER TABLE daily_workouts ADD COLUMN key_workout_id VARCHAR",
        # VDOT for race runs
        "ALTER TABLE run_logs ADD COLUMN vdot FLOAT",
        # Predicted time snapshot when a race is logged
        "ALTER TABLE run_logs ADD COLUMN predicted_time_seconds FLOAT",
        # Shareable link token
        "ALTER TABLE training_plans ADD COLUMN share_token VARCHAR",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_training_plan_share_token ON training_plans(share_token)",
    ]
    with eng.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(_sa_text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists


_run_migrations(engine)


def _backfill_vdot(eng) -> None:
    """Backfill VDOT for all runs that have sufficient distance but no VDOT yet."""
    from app.core.vdot_calculator import VDOTCalculator
    from app.models.run_log import RunLog
    from sqlalchemy.orm import Session as _Session

    session = _Session(bind=eng)
    try:
        runs = (
            session.query(RunLog)
            .filter(
                RunLog.vdot.is_(None),
                RunLog.distance_km >= 2.0,
                RunLog.duration_minutes > 0,
            )
            .all()
        )
        if not runs:
            return
        updated = 0
        for run in runs:
            vdot = VDOTCalculator.calculate_vdot(
                run.distance_km, int(run.duration_minutes * 60)
            )
            if vdot:
                run.vdot = vdot
                updated += 1
        session.commit()
        logger.info(f"VDOT backfill: updated {updated}/{len(runs)} runs")
    except Exception as e:
        session.rollback()
        logger.warning(f"VDOT backfill failed: {e}")
    finally:
        session.close()


_backfill_vdot(engine)

# Templates
templates = create_templates()

# Static files with caching
app.mount("/static", CachedStaticFiles(
    directory="app/static",
    cache_max_age=86400
), name="static")

# Include routers


app.include_router(plans_router)
app.include_router(nutrition_router)
app.include_router(recipes_router)
app.include_router(auth_router)
app.include_router(runs_router)
app.include_router(adaptive_router)
app.include_router(performance_router)
app.include_router(analytics_router)
app.include_router(analytics_page_router)
app.include_router(strava_router)
app.include_router(triathlon_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Health check endpoint for monitoring and load balancers."""
    return HealthResponse()


if settings.debug:
    @app.get("/debug/config", tags=["debug"])
    async def debug_config():
        """Debug endpoint to check configuration (development only)."""
        client_id = settings.google_client_id
        return {
            "google_client_id_configured": settings.is_google_client_id_configured,
            "google_client_id_preview": client_id[:20] + "..." if len(client_id) > 20 else client_id,
            "google_client_id_is_placeholder": not settings.is_google_client_id_configured,
            "google_client_id_length": len(client_id) if client_id else 0,
            "secret_key_configured": bool(settings.secret_key),
            "secret_key_is_default": "dev-secret" in settings.secret_key.lower() or "your-secret" in settings.secret_key.lower(),
            "secret_key_length": len(settings.secret_key),
            "debug_mode": settings.debug,
            "environment": "development",
        }

    @app.get("/debug/test-auth", tags=["debug"])
    async def test_auth():
        """Test endpoint to verify auth service is working."""
        from app.auth_service import AuthService

        auth = AuthService()

        # Test JWT creation/verification
        test_payload = {"sub": "test-user-id", "email": "test@example.com"}
        token = auth.create_access_token(test_payload)
        verified = auth.verify_token(token)

        return {
            "jwt_creation": "success" if token else "failed",
            "jwt_verification": "success" if verified else "failed",
            "token_preview": token[:50] + "..." if token else None,
            "verified_payload": verified if verified else None,
        }


@app.get("/", response_class=HTMLResponse, tags=["pages"])
async def home(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    """Render home page."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user,
        "google_client_id": settings.google_client_id or ""
    })


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup tasks."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")

    if settings.is_google_client_id_configured:
        logger.info("Google Client ID is properly configured")
    else:
        logger.warning("Google Client ID is not properly configured - Google Sign-In will not work")

    # Validate secret key in production
    if not settings.debug:
        weak_patterns = ["dev-secret", "your-secret", "change-in-production", "placeholder"]
        key = settings.secret_key
        if len(key) < 32 or any(p in key.lower() for p in weak_patterns):
            raise RuntimeError(
                "SECRET_KEY is too weak for production. "
                "Set a random key of at least 32 characters."
            )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown tasks."""
    logger.info(f"Shutting down {settings.app_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
