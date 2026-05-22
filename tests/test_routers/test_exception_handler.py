"""Tests for the global RunCoachException handler (M4)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions import (
    DatabaseException,
    RunCoachException,
    UnrealisticGoalException,
    ValidationException,
)
from app.web.exception_handlers import register_exception_handlers


def _app_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_validation_exception_maps_to_400():
    client = _app_raising(ValidationException("bad input", "Please fix your input"))
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "Please fix your input"
    assert body["error_type"] == "ValidationException"
    assert "suggestion" not in body


def test_suggestion_is_included_when_present():
    client = _app_raising(
        UnrealisticGoalException("too fast", suggestion="Allow more weeks")
    )
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["suggestion"] == "Allow more weeks"


def test_database_exception_maps_to_500():
    client = _app_raising(DatabaseException("db down", "Try again later"))
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Try again later"


def test_base_exception_defaults_to_400():
    client = _app_raising(RunCoachException("generic", "Something went wrong"))
    resp = client.get("/boom")
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "RunCoachException"
