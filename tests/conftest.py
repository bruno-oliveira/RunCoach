"""Pytest fixtures for RunCoach tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.models import Base
from app.core.nutrition_engine import NutritionEngine
from app.core.plan_generator import TrainingPlanGenerator


@pytest.fixture(scope="function")
def test_db() -> Session:
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Match production SQLite pragmas (dependencies.py)
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create tables
    Base.metadata.create_all(bind=engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """Create a test client with overridden database dependency."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


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


# Test data fixtures
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
