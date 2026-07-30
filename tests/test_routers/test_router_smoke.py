"""Smoke tests: one authenticated success + one 401 per router.

Covers routers that previously had no test coverage:
runs, analytics, performance, adaptive, recipes.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.run_log import RunLog
from app.models.training_plan import TrainingPlan
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def smoke_user(test_db: Session) -> User:
    """Create a minimal authenticated user."""
    user = User(
        id="smoke-user-1",
        email="smoke@example.com",
        name="Smoke Test",
        google_id="google-smoke-1",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def _override_db(test_db: Session):
    """Override the DB dependency and clean up after the test."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _set_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


def _clear_user():
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Runs router  (/api/runs)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestRunsRouter:
    def test_get_runs_authenticated(self, smoke_user):
        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data

    def test_get_runs_unauthenticated(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/api/runs")
        assert resp.status_code == 401

    def test_create_run_authenticated(self, smoke_user):
        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.post(
                "/api/runs",
                json={
                    "distance_km": 5.0,
                    "duration_minutes": 30.0,
                },
            )
        assert resp.status_code == 201

    def test_create_run_unauthenticated(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.post(
                "/api/runs",
                json={
                    "distance_km": 5.0,
                    "duration_minutes": 30.0,
                },
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Analytics router  (/api/analytics)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestAnalyticsRouter:
    def test_get_analytics_runs_authenticated(self, smoke_user):
        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.get("/api/analytics/runs")
        assert resp.status_code == 200

    def test_analytics_runs_exposes_effective_type_and_inferred_flag(
        self, smoke_user, test_db
    ):
        # Imported run that arrived untagged (defaulted "easy") but inferred tempo.
        test_db.add(
            RunLog(
                user_id=smoke_user.id,
                source="intervals",
                distance_km=8.0,
                duration_minutes=36.0,
                avg_pace_min_km=4.5,
                workout_type="easy",
                inferred_workout_type="tempo",
                inferred_type_confidence=0.8,
            )
        )
        # Manually tagged run: the explicit choice stands, not flagged inferred.
        test_db.add(
            RunLog(
                user_id=smoke_user.id,
                distance_km=10.0,
                duration_minutes=55.0,
                avg_pace_min_km=5.5,
                workout_type="long",
            )
        )
        test_db.commit()

        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.get("/api/analytics/runs")

        assert resp.status_code == 200
        by_type = {r["workout_type"]: r for r in resp.json()["runs"]}
        assert by_type["tempo"]["inferred"] is True  # corrected from the "easy" default
        assert by_type["long"]["inferred"] is False  # explicit manual tag

    def test_get_analytics_runs_unauthenticated(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/api/analytics/runs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Performance router  (/performance-training, /api/performance)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestPerformanceRouter:
    def test_performance_page_renders(self):
        """Performance page uses get_optional_user — should render without auth."""
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/performance-training")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Recipes router  (/api/recipes, /recipes)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestRecipesRouter:
    def test_search_recipes_public(self):
        """Recipe search is public — no auth required."""
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/api/recipes")
        assert resp.status_code == 200
        data = resp.json()
        assert "recipes" in data

    def test_recipes_page_renders(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/recipes")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_favorites_unauthenticated_empty(self):
        """Favorites endpoint uses get_optional_user — returns empty for anon."""
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/api/recipes/favorites")
        assert resp.status_code == 200
        assert resp.json()["recipes"] == []


# ---------------------------------------------------------------------------
# Time-goal plan generation  (/generate-plan with plan_mode=time)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestTimeGoalPlan:
    def test_time_goal_plan_generates_successfully(self, smoke_user):
        """Time-goal plan should redirect to the new plan on success."""
        _set_user(smoke_user)
        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/generate-plan",
                    data={
                        "current_km": 30.0,
                        "target_distance": "10",
                        "weeks": 8,
                        "max_runs_per_week": 4,
                        "plan_mode": "time",
                        "goal_time_required": "50:00",
                        "current_time": "55:00",
                    },
                    follow_redirects=False,
                )
            assert resp.status_code == 303
            assert resp.headers["location"].startswith("/plan/")
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_time_goal_plan_requires_auth(self):
        """Time-goal plan without auth should return auth_required error."""
        _clear_user()
        app.dependency_overrides[get_optional_user] = lambda: None
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/generate-plan",
                    data={
                        "current_km": 30.0,
                        "target_distance": "10",
                        "weeks": 8,
                        "max_runs_per_week": 4,
                        "plan_mode": "time",
                        "goal_time_required": "50:00",
                    },
                )
            assert resp.status_code == 200
            assert "logged-in" in resp.text.lower() or "auth" in resp.text.lower()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# Home page  (/)  — auth-aware hero
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestHomeHero:
    def test_anonymous_home_shows_marketing_hero(self):
        """Anonymous visitors see the connect card, not a training-status hero."""
        app.dependency_overrides[get_optional_user] = lambda: None
        try:
            with TestClient(app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "hero--status" not in resp.text
            # Single action surface: the connect card is present.
            assert "connect-card" in resp.text
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_signed_in_with_plan_shows_status_hero(self, smoke_user, test_db):
        """A runner mid-plan gets the status hero + a link to their plan."""
        plan = TrainingPlan(
            id="home-hero-plan-1",
            user_id=smoke_user.id,
            current_weekly_km=30,
            target_distance="10",
            weeks_duration=8,
            start_date=local_today() - timedelta(weeks=3),
        )
        test_db.add(plan)
        test_db.commit()

        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "hero--status" in resp.text
            assert "Week 4 of 8" in resp.text
            assert "/plan/home-hero-plan-1" in resp.text
            # The first-time marketing loop should not render for them.
            assert "hero-loop" not in resp.text
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_signed_in_without_plan_shows_next_step(self, smoke_user):
        """A fresh signup with no plan gets a build/connect prompt, no plan card."""
        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "hero--status" in resp.text
            assert "back_noplan_title" in resp.text
            assert "status-pill" not in resp.text
        finally:
            app.dependency_overrides.pop(get_optional_user, None)
