"""Smoke tests: one authenticated success + one 401 per router.

Covers routers that previously had no test coverage:
runs, performance, adaptive, recipes.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
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

    @pytest.mark.parametrize(
        ("distance", "current_km", "current_time", "goal_time", "required_km"),
        [
            ("5", 10.0, "27:30", "25:00", 20),
            ("10", 10.0, "55:00", "50:00", 25),
            ("21.1", 20.0, "1:56:03", "1:45:30", 35),
            ("42.2", 30.0, "3:52:06", "3:31:00", 50),
        ],
    )
    def test_time_goal_plan_enforces_performance_base_in_live_route(
        self,
        smoke_user,
        test_db,
        distance,
        current_km,
        current_time,
        goal_time,
        required_km,
    ):
        """The unified form must not bypass PerformancePlanRequest."""
        _set_user(smoke_user)
        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        before = test_db.query(TrainingPlan).count()
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/generate-plan",
                    data={
                        "current_km": current_km,
                        "target_distance": distance,
                        "weeks": 8,
                        "max_runs_per_week": 4,
                        "plan_mode": "time",
                        "goal_time_required": goal_time,
                        "current_time": current_time,
                    },
                )
            assert resp.status_code == 200
            assert f"{required_km} km/week" in resp.text
            assert test_db.query(TrainingPlan).count() == before
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# Home page  (/)  — auth-aware hero
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestHomeHero:
    def test_anonymous_home_shows_marketing_hero(self):
        """Anonymous visitors can build before connecting and see a real sample week."""
        app.dependency_overrides[get_optional_user] = lambda: None
        try:
            with TestClient(app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "hero--status" not in resp.text
            # Single action surface: the connect card is present.
            assert "connect-card" in resp.text
            card = resp.text.split('id="home-connect-card"', 1)[1].split(
                "<!-- Prerequisites collapsed", 1
            )[0]
            assert card.index("scrollToBuild()") < card.index("connectWatch()")
            assert 'id="preview-title"' in resp.text
            assert 'id="plan-form"' in resp.text
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_public_sample_week_still_matches_generator(self):
        """The week labelled as real on the landing page must track the engine."""
        from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator

        week = TrainingPlanGenerator().generate_plan(25, 10, 12, 4)[3]
        assert [(day["type"], day["distance"]) for day in week["daily_workouts"]] == [
            ("easy", 6.7),
            ("rest", 0),
            ("easy", 6.7),
            ("easy", 6.7),
            ("rest", 0),
            ("long", 7.5),
            ("rest", 0),
        ]

    def test_public_adjustment_example_still_matches_engine(self, test_db):
        """Pin the before/after values used as product proof on the landing page."""
        from tests.test_services.test_adaptation_behaviour import _applied_scenario

        result = _applied_scenario(test_db, 0.9)
        before, after = result["before"][6], result["after"][6]
        assert (before["total_km"], after["total_km"]) == (43.6, 39.8)
        assert (
            before["daily_workouts"][0]["distance"],
            after["daily_workouts"][0]["distance"],
        ) == (5.4, 4.0)

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

    def test_signed_in_home_shows_today_week_and_applied_change(
        self, smoke_user, test_db
    ):
        from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator

        plan = TrainingPlan(
            id="home-daily-plan",
            user_id=smoke_user.id,
            current_weekly_km=25,
            target_distance="10",
            weeks_duration=12,
            start_date=local_today() - timedelta(weeks=3),
            plan_data=TrainingPlanGenerator().generate_plan(25, 10, 12, 4),
            last_change_plan={
                "did_change": True,
                "computed_at": local_today().isoformat(),
                "reason": "Recent training called for an easier week.",
                "weeks": [
                    {
                        "week": 4,
                        "workouts": [
                            {
                                "day": "Mon",
                                "type": "easy",
                                "status": "changed",
                                "old_distance_km": 8.0,
                                "new_distance_km": 6.7,
                                "reason": "Keep the build gradual.",
                            }
                        ],
                    }
                ],
            },
        )
        test_db.add(plan)
        test_db.commit()
        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.get("/")
            assert resp.status_code == 200
            assert "home-today" in resp.text
            assert 'id="readinessCheckinCard"' in resp.text
            assert "Runs not connected" in resp.text
            assert "home-week-preview" in resp.text
            assert "8 km" in resp.text and "6.7 km" in resp.text
            assert "Recent training called for an easier week." in resp.text
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# My Plans page  (/my-plans)
#
# The page splits plans into "active" and "completed" and renders each from its
# PlanStatus view model, so this exercises the mapping/plan-id wiring between the
# router and the template (templates are not type-checked).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestMyPlansPage:
    def test_splits_active_from_completed_plans(self, smoke_user, test_db):
        test_db.add_all(
            [
                TrainingPlan(
                    id="my-plans-active",
                    user_id=smoke_user.id,
                    current_weekly_km=30,
                    target_distance="10",
                    weeks_duration=8,
                    start_date=local_today() - timedelta(weeks=3),
                ),
                TrainingPlan(
                    id="my-plans-done",
                    user_id=smoke_user.id,
                    current_weekly_km=30,
                    target_distance="21.1",
                    weeks_duration=8,
                    start_date=local_today() - timedelta(weeks=20),
                ),
            ]
        )
        test_db.commit()

        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.get("/my-plans")
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

        assert resp.status_code == 200
        # The active card carries its status label and distance label…
        assert "Week 4 of 8" in resp.text
        assert "10K Training Plan" in resp.text
        # …and the completed one is filed under the completed section.
        assert "Half Marathon Training Plan" in resp.text
        assert "Completed Plans" in resp.text

    def test_renders_without_plans(self, smoke_user, test_db):
        app.dependency_overrides[get_optional_user] = lambda: smoke_user
        try:
            with TestClient(app) as c:
                resp = c.get("/my-plans")
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

        assert resp.status_code == 200
        assert "myplans.none_title" in resp.text


# ---------------------------------------------------------------------------
# Setup watch page  (/setup/watch)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_override_db")
class TestSetupWatchPage:
    def test_setup_watch_renders_for_authenticated_user(self, smoke_user):
        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.get("/setup/watch", follow_redirects=False)
        assert resp.status_code == 200
        assert "setup-card" in resp.text
        assert "Intervals.icu" in resp.text

    def test_setup_watch_requires_auth(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/setup/watch", follow_redirects=False)
        assert resp.status_code in (401, 403)

    def test_setup_watch_carries_return_to(self, smoke_user):
        _set_user(smoke_user)
        with TestClient(app) as c:
            resp = c.get("/setup/watch?return_to=/plan/abc")
        assert resp.status_code == 200
        assert "/plan/abc" in resp.text
