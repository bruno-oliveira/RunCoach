"""The health endpoint must report a broken dependency, not just a live process.

A static ``{"status": "healthy"}`` is green on a machine whose SQLite volume has
failed to mount — every page 500s while Fly's checks stay happy and the machine
is never cycled. These tests pin the contract: 200 naming each healthy check,
503 carrying the reason when a dependency is down, and a probe that returns
rather than raises so the endpoint reports the *dependency* failure instead of
its own.
"""

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from app.infrastructure.health import get_health_probe, probe_database
from app.main import app as production_app


@pytest.fixture
def health_client():
    """The production app, with the DB probe substituted (no real DB touched)."""
    return TestClient(production_app)


@pytest.fixture
def override_probe():
    """Install a temporary probe; always restore the real one afterwards."""

    def _install(probe):
        production_app.dependency_overrides[get_health_probe] = lambda: probe

    yield _install
    production_app.dependency_overrides.pop(get_health_probe, None)


def test_health_reports_ok_for_each_dependency(health_client, override_probe):
    override_probe(lambda: None)

    response = health_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"] == {"database": "ok"}
    assert "version" in body


def test_health_is_503_and_names_the_dependency_when_the_db_is_down(
    health_client, override_probe
):
    reason = "OperationalError: unable to open database file"
    override_probe(lambda: reason)

    response = health_client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    # Named, so ops does not have to guess which dependency failed.
    assert body["checks"]["database"] == reason


def test_a_probe_that_raises_does_not_read_as_healthy(health_client, override_probe):
    """A bug in a probe must fail loudly rather than yield a false 200."""

    def _broken():
        raise RuntimeError("probe is broken")

    override_probe(_broken)

    with pytest.raises(RuntimeError):
        health_client.get("/health")


class TestProbeDatabase:
    """``probe_database`` itself: it must always return a verdict."""

    def test_returns_none_when_the_database_answers(self):
        assert probe_database() is None

    def test_returns_a_reason_instead_of_raising(self, monkeypatch):
        class _UnopenableEngine:
            def connect(self):
                raise sqlalchemy.exc.OperationalError(
                    "SELECT 1", {}, Exception("unable to open database file")
                )

        # The probe looks the engine up at call time, so replacing the module
        # attribute is enough to simulate a volume that failed to mount.
        monkeypatch.setattr(
            "app.infrastructure.database.engine", _UnopenableEngine(), raising=False
        )

        reason = probe_database()

        assert reason is not None
        assert "OperationalError" in reason
        assert "unable to open database file" in reason


# ---------------------------------------------------------------------------
# Liveness vs readiness
#
# Fly restarts a machine whose liveness check fails and drops one whose
# readiness check fails. Those are different remedies, so the endpoints must be
# different too: liveness asserts only that the process is up (no I/O), and
# readiness is the one that consults the database.
# ---------------------------------------------------------------------------


def test_liveness_is_200_even_when_the_database_is_down(health_client, override_probe):
    override_probe(lambda: "OperationalError: unable to open database file")

    response = health_client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    # No dependency verdicts: liveness asserts nothing about the database, or a
    # storage outage would restart the fleet instead of draining it.
    assert "checks" not in body


def test_liveness_never_calls_the_dependency_probe(health_client, override_probe):
    def _explode():
        raise AssertionError("liveness must not run a dependency probe")

    override_probe(_explode)

    assert health_client.get("/health/live").status_code == 200


def test_readiness_is_503_when_the_database_is_down(health_client, override_probe):
    reason = "OperationalError: unable to open database file"
    override_probe(lambda: reason)

    response = health_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == reason


def test_readiness_answers_like_health(health_client, override_probe):
    """``/health`` stays a readiness check, so existing monitors keep working."""
    override_probe(lambda: None)

    assert (
        health_client.get("/health/ready").json() == health_client.get("/health").json()
    )
