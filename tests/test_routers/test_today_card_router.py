"""Tests for the Today card at the head of the plan.

Two promises are under test. The card is *server-rendered*, so today's session
and the coaching line under it have to be right on first paint and survive a
reload — the reason the check-in was moved out of the Coach hub in the first
place. And the advisory has one implementation: the endpoint the page re-reads
after a check-in returns the same words the template rendered, so the two can't
drift apart.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
from app.models import ReadinessLog, TrainingPlan, User


def _plan_data(today_type: str = "tempo") -> list[dict]:
    """One week where every day carries the same workout.

    Filling all seven days keeps the fixture independent of which weekday the
    suite happens to run on.
    """
    return [
        {
            "week": 1,
            "phase": "build",
            "daily_workouts": [
                {
                    "day": d,
                    "type": today_type,
                    "distance": 8.0,
                    "duration_min": 45,
                    "description": "Steady at threshold.",
                    "hr_zone_target": 4,
                    "hr_zone_label": "Threshold",
                }
                for d in range(1, 8)
            ],
        }
    ]


@pytest.fixture
def runner(test_db: Session) -> User:
    user = User(id="today-user", email="today@example.com", name="Sam")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plan(test_db: Session, runner: User) -> TrainingPlan:
    tp = TrainingPlan(
        id="today-plan",
        user_id=runner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=1,
        vdot=45.0,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=_plan_data(),
    )
    test_db.add(tp)
    test_db.commit()
    return tp


@pytest.fixture
def client(test_db: Session, runner: User):
    def override_get_db():
        yield test_db

    async def override_user():
        return runner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_optional_user] = override_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _check_in(db: Session, user: User, *, rough: bool) -> None:
    """Log this morning's check-in.

    ``rough`` lands in the run-down band; otherwise in "good" — deliberately
    not "primed", which has its own advisory. "Good" is the ordinary morning
    the card is supposed to stay silent on.
    """
    db.add(
        ReadinessLog(
            user_id=user.id,
            date=date.today(),
            sleep_hours=4.0 if rough else 6.0,
            sleep_quality=1 if rough else 4,
            energy=1 if rough else 4,
            soreness=5 if rough else 3,
            stress=5 if rough else 3,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# The card renders server-side
# ---------------------------------------------------------------------------


def test_the_card_leads_the_plan_with_todays_session(client, plan):
    page = client.get(f"/plan/{plan.id}").text

    assert 'id="today-card"' in page
    assert "Tempo" in page
    assert "8.0 km" in page
    assert "Steady at threshold." in page


def test_the_check_in_and_watch_status_are_folded_into_the_same_card(client, plan):
    """The point of L1: one moment, not three surfaces."""
    page = client.get(f"/plan/{plan.id}").text
    card = page.split('id="today-card"', 1)[1].split("</section>", 1)[0]

    assert 'id="readinessCheckinCard"' in card
    assert 'id="watch-mirror"' in card


def test_the_old_detour_to_the_coach_hub_check_in_is_gone(client, plan):
    page = client.get(f"/plan/{plan.id}").text
    assert "tab=today" not in page


def test_a_rough_check_in_puts_a_line_under_a_hard_session(
    client, test_db, runner, plan
):
    _check_in(test_db, runner, rough=True)

    page = client.get(f"/plan/{plan.id}").text

    assert "Adjust my plan" in page
    assert 'data-band="run_down"' in page or 'data-band="depleted"' in page


def test_an_ordinary_morning_leaves_the_line_empty(client, test_db, runner, plan):
    """Silence is the default — a line on every ordinary day is noise."""
    _check_in(test_db, runner, rough=False)

    page = client.get(f"/plan/{plan.id}").text
    advisory = page.split('id="today-session-advisory"', 1)[1].split(">", 1)[0]

    assert "hidden" in advisory


def test_no_check_in_at_all_leaves_the_line_empty(client, plan):
    page = client.get(f"/plan/{plan.id}").text
    advisory = page.split('id="today-session-advisory"', 1)[1].split(">", 1)[0]

    assert "hidden" in advisory


def test_a_plan_with_no_start_date_still_shows_watch_status(client, test_db, plan):
    """The mirror falls back to its standalone strip rather than disappearing
    with the card."""
    plan.start_date = None
    test_db.commit()

    page = client.get(f"/plan/{plan.id}").text

    assert 'id="today-card"' not in page
    assert 'id="watch-mirror"' in page


# ---------------------------------------------------------------------------
# The re-read endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_returns_the_same_advisory_the_page_rendered(
    client, test_db, runner, plan
):
    """One implementation, so a check-in can't leave the page saying one thing
    and the server another."""
    _check_in(test_db, runner, rough=True)

    page = client.get(f"/plan/{plan.id}").text
    advisory = client.get(f"/api/plan/{plan.id}/today-card").json()["advisory"]

    assert advisory
    # The template escapes the apostrophe in "You checked in…"; compare on a
    # stretch of copy that survives both paths intact.
    assert "Adjust my plan" in advisory
    assert "Adjust my plan" in page


def test_the_endpoint_reports_the_band_for_the_cards_styling(
    client, test_db, runner, plan
):
    _check_in(test_db, runner, rough=True)

    body = client.get(f"/api/plan/{plan.id}/today-card").json()

    assert body["available"] is True
    assert body["readiness_band"] in ("run_down", "depleted")
    assert body["readiness_score"] is not None


def test_the_endpoint_is_silent_without_a_check_in(client, plan):
    body = client.get(f"/api/plan/{plan.id}/today-card").json()

    assert body["available"] is True
    assert body["advisory"] is None
    assert body["readiness_band"] is None


def test_the_endpoint_reports_unavailable_for_a_plan_with_no_today(
    client, test_db, plan
):
    plan.start_date = None
    test_db.commit()

    assert client.get(f"/api/plan/{plan.id}/today-card").json() == {"available": False}


def test_the_endpoint_will_not_read_someone_elses_plan(client, test_db):
    stranger = User(id="today-stranger", email="stranger@example.com")
    test_db.add(stranger)
    test_db.commit()
    others = TrainingPlan(
        id="stranger-plan",
        user_id=stranger.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=1,
        start_date=datetime.combine(date.today(), datetime.min.time()),
        plan_data=_plan_data(),
    )
    test_db.add(others)
    test_db.commit()

    assert client.get(f"/api/plan/{others.id}/today-card").status_code == 403


def test_a_completed_plan_has_no_today_card(client, test_db, plan):
    plan.start_date = datetime.combine(
        date.today() - timedelta(weeks=6), datetime.min.time()
    )
    test_db.commit()

    page = client.get(f"/plan/{plan.id}").text

    assert 'id="today-card"' not in page
