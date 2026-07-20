"""Endpoint tests for the Intervals.icu integration."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def intervals_user(test_db: Session) -> User:
    user = User(
        id="intervals-router-user",
        email="intervals-router@example.com",
        intervals_athlete_id="i456",
        intervals_access_token="access-token",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def plain_user(test_db: Session) -> User:
    user = User(id="intervals-plain-user", email="intervals-plain@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def intervals_client(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _set_user(user: User) -> None:
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


def _make_state(user_id: str, nonce: str) -> str:
    return AuthService().create_access_token(
        {"sub": user_id, "purpose": "intervals_oauth", "nonce": nonce},
        expires_delta=timedelta(minutes=5),
    )


def test_connect_returns_oauth_url(intervals_client, plain_user):
    _set_user(plain_user)
    with (
        patch("app.web.routers.intervals.settings.intervals_client_id", "client-1"),
        patch("app.web.routers.intervals.settings.intervals_client_secret", "secret-1"),
    ):
        response = intervals_client.get("/api/intervals/connect")

    assert response.status_code == 200
    assert response.json()["authorize_url"].startswith(
        "https://intervals.icu/oauth/authorize?"
    )
    assert intervals_client.cookies.get("intervals_oauth_state")


def test_sync_connected_user(intervals_client, intervals_user):
    _set_user(intervals_user)
    with patch(
        "app.infrastructure.integrations.intervals_service.IntervalsService.sync_activities",
        new_callable=AsyncMock,
        return_value={
            "synced": 2,
            "skipped": 1,
            "errors": [],
            "total": 3,
            "last_synced_at": 123,
        },
    ):
        response = intervals_client.post("/api/intervals/sync?force_days=7")

    assert response.status_code == 200
    assert response.json()["synced"] == 2


def test_sync_requires_connection(intervals_client, plain_user):
    _set_user(plain_user)
    response = intervals_client.post("/api/intervals/sync")
    assert response.status_code == 400


def test_callback_stores_persistent_token(intervals_client, plain_user, test_db):
    state = _make_state(plain_user.id, "nonce-1")
    intervals_client.cookies.set("intervals_oauth_state", "nonce-1")

    with (
        patch(
            "app.infrastructure.integrations.intervals_service.IntervalsService.exchange_code_for_token",
            new_callable=AsyncMock,
            return_value={
                "access_token": "persistent-token",
                "scope": "ACTIVITY:READ",
                "athlete": {"id": "i999", "name": "Runner"},
            },
        ),
        patch(
            "app.web.routers.intervals.initial_intervals_sync",
            new_callable=AsyncMock,
        ),
    ):
        response = intervals_client.get(
            "/api/intervals/callback",
            params={"code": "code-1", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    test_db.refresh(plain_user)
    assert plain_user.intervals_athlete_id == "i999"
    assert plain_user.intervals_access_token == "persistent-token"
