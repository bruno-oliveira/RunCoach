"""Endpoint tests for the daily readiness check-in (/api/readiness)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import ReadinessLog, User


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="rc-owner", email="rc-owner@example.com", name="Owner")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def _override_db(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _set_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


@pytest.mark.usefixtures("_override_db")
class TestReadinessEndpoint:
    def test_requires_auth(self):
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            resp = client.post("/api/readiness", json={"energy": 3})
        assert resp.status_code == 401

    def test_record_returns_score_and_band(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                "/api/readiness",
                json={"sleep_hours": 8, "sleep_quality": 5, "energy": 5, "soreness": 1},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["score"] == 100.0
        assert body["band"] == "primed"
        assert body["id"]

    def test_low_morning_returns_drivers(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post(
                "/api/readiness",
                json={"sleep_hours": 5, "soreness": 4, "energy": 2},
            )
        body = resp.json()
        assert body["band"] in ("run_down", "depleted")
        assert "your legs are heavy" in body["drivers"]

    def test_empty_payload_is_rejected(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            resp = client.post("/api/readiness", json={"notes": "just a note"})
        assert resp.status_code == 422

    def test_second_post_upserts_same_day(self, owner, test_db):
        _set_user(owner)
        with TestClient(app) as client:
            client.post("/api/readiness", json={"energy": 2, "soreness": 5})
            client.post("/api/readiness", json={"energy": 5, "soreness": 1})
        assert test_db.query(ReadinessLog).filter_by(user_id=owner.id).count() == 1

    def test_get_today_reflects_logged_state(self, owner):
        _set_user(owner)
        with TestClient(app) as client:
            before = client.get("/api/readiness/today").json()
            assert before == {"logged": False, "checkin": None}

            client.post("/api/readiness", json={"energy": 4})
            after = client.get("/api/readiness/today").json()
        assert after["logged"] is True
        assert after["checkin"]["energy"] == 4
