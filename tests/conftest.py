"""Pytest fixtures for RunCoach tests."""

import os

# Hermetic test config — must be set BEFORE any app module imports the
# settings singleton. Tests run in debug mode: no separate ENCRYPTION_KEY is
# required (it falls back to SECRET_KEY) and cookies are not Secure-flagged,
# so the http TestClient round-trips the anonymous-user / CSRF cookies.
# `setdefault` lets an explicit environment (e.g. CI) still override.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only-not-production")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")

import tempfile  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.contexts.nutrition.nutrition_engine import NutritionEngine  # noqa: E402
from app.contexts.plan.generators.plan_generator import (  # noqa: E402
    TrainingPlanGenerator,
)
from app.dependencies import get_db  # noqa: E402
from app.models import Base  # noqa: E402


def _run_alembic_migrations(engine) -> None:
    """Run Alembic migrations against the given engine."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Reset in-memory rate limiter state between tests.

    The limiters live at module scope so per-IP counts persist across
    tests in the same process; without this, tightly-capped limiters
    (e.g. plan_generation_limiter at 5/min) cause cascading failures.
    """
    from app import rate_limit

    for name in dir(rate_limit):
        obj = getattr(rate_limit, name)
        if isinstance(obj, rate_limit.RateLimiter):
            obj._hits.clear()
    yield


@pytest.fixture(scope="function")
def test_db() -> Session:
    """Create a test database session using a temporary file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"

    engine = create_engine(db_url)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    _run_alembic_migrations(engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """Create a test client with overridden database dependency."""
    from app.main import create_app

    test_app = create_app(skip_migrations=True)

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()


@pytest.fixture
def plan_generator() -> TrainingPlanGenerator:
    """Create a TrainingPlanGenerator instance."""
    return TrainingPlanGenerator()


@pytest.fixture
def nutrition_engine() -> NutritionEngine:
    """Create a NutritionEngine instance."""
    return NutritionEngine()


@pytest.fixture
def nutrition_engine_seeded() -> NutritionEngine:
    """Create a NutritionEngine instance with fixed seed for reproducibility."""
    return NutritionEngine(random_seed=42)


@pytest.fixture
def sample_5k_params() -> dict:
    """Sample parameters for 5K training plan."""
    return {
        "current_km": 20.0,
        "target_distance": 5,
        "weeks": 8,
    }


@pytest.fixture
def sample_marathon_params() -> dict:
    """Sample parameters for marathon training plan."""
    return {
        "current_km": 40.0,
        "target_distance": 42.2,
        "weeks": 16,
    }


@pytest.fixture
def sample_trail_params() -> dict:
    """Sample parameters for trail running training plan (30km = Trail Running)."""
    return {
        "current_km": 25.0,
        "target_distance": 30.0,
        "weeks": 10,
    }
