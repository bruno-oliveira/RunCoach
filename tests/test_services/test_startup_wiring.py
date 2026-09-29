"""Startup wiring must not be inferrable from the interpreter's contents.

The app factory used to skip migrations *and* `validate_production_secrets` when
``"pytest" in sys.modules``. That is a silent-failure shape: any process that
imported pytest — a plugin, a profiler, an entrypoint that imported a test
helper — would boot without migrations and with a forgeable JWT key, and say
nothing about either.

These tests pin the replacement contract: migrations follow explicit
configuration, and the production-secret check is never skippable.
"""

import sys

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.main import create_app


class TestNoInterpreterSniffing:
    def test_the_factory_no_longer_carries_a_test_mode_flag(self):
        import app.main as main_module

        assert not hasattr(main_module, "_is_test_mode")

    def test_pytest_in_sys_modules_does_not_force_a_skip(self, monkeypatch):
        """The regression guard: the old gate keyed on exactly this condition."""
        assert "pytest" in sys.modules

        called: list[str] = []
        monkeypatch.setattr(settings, "run_startup_migrations", True)
        monkeypatch.setattr(
            "app.main.run_startup_migrations", lambda: called.append("migrated")
        )

        # No explicit argument: the decision must come from configuration only.
        with TestClient(create_app()):
            pass

        assert called == ["migrated"]


class TestMigrationFlag:
    def test_defaults_to_running_migrations(self):
        """The shipped default must apply migrations — production depends on it."""
        assert settings.__class__.model_fields["run_startup_migrations"].default is True

    def test_the_test_session_pins_migrations_off(self):
        assert settings.run_startup_migrations is False

    def test_an_explicit_argument_overrides_the_setting(self, monkeypatch):
        """Explicit callers (conftest, scripts) still win over configuration."""
        calls: list[str] = []
        monkeypatch.setattr(
            "app.main.run_startup_migrations", lambda: calls.append("migrated")
        )

        with TestClient(create_app(skip_migrations=True)):
            pass
        assert calls == []


class TestSecretValidationIsNotSkippable:
    def test_runs_even_when_migrations_are_skipped(self, monkeypatch):
        """The two concerns are independent: skipping DDL must not skip a
        JWT-key sanity check."""
        called: list[str] = []
        monkeypatch.setattr(
            "app.main.validate_production_secrets",
            lambda: called.append("validated"),
        )

        with TestClient(create_app(skip_migrations=True)):
            pass

        assert called == ["validated"]

    def test_runs_when_migrations_run(self, monkeypatch):
        called: list[str] = []
        monkeypatch.setattr(
            "app.main.validate_production_secrets",
            lambda: called.append("validated"),
        )
        monkeypatch.setattr("app.main.run_startup_migrations", lambda: None)

        with TestClient(create_app(skip_migrations=False)):
            pass

        assert called == ["validated"]

    def test_debug_mode_tolerates_a_missing_encryption_key(self):
        """The check must not make a debug boot impossible — it warns there."""
        from app.infrastructure.secrets import validate_production_secrets

        assert settings.debug is True
        validate_production_secrets()  # must not raise in DEBUG


class TestProductionSecretGuard:
    """The rules themselves, exercised directly rather than through a boot."""

    @pytest.fixture
    def prod_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "debug", False)
        monkeypatch.setattr(settings, "secret_key", "x" * 48)
        monkeypatch.setattr(settings, "encryption_key", "y" * 48)
        return settings

    def test_rejects_a_weak_secret_key(self, prod_settings, monkeypatch):
        monkeypatch.setattr(prod_settings, "secret_key", "short")
        from app.infrastructure.secrets import validate_production_secrets

        with pytest.raises(RuntimeError, match="SECRET_KEY is too weak"):
            validate_production_secrets()

    def test_rejects_a_placeholder_secret_key(self, prod_settings, monkeypatch):
        monkeypatch.setattr(
            prod_settings, "secret_key", "change-in-production-but-long-enough"
        )
        from app.infrastructure.secrets import validate_production_secrets

        with pytest.raises(RuntimeError, match="too weak"):
            validate_production_secrets()

    def test_requires_an_encryption_key(self, prod_settings, monkeypatch):
        monkeypatch.setattr(prod_settings, "encryption_key", "")
        from app.infrastructure.secrets import validate_production_secrets

        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY is required"):
            validate_production_secrets()

    def test_rejects_an_encryption_key_equal_to_the_secret(self, prod_settings):
        from app.infrastructure.secrets import validate_production_secrets

        prod_settings.encryption_key = prod_settings.secret_key
        with pytest.raises(RuntimeError, match="must differ"):
            validate_production_secrets()

    def test_accepts_a_well_configured_production(self, prod_settings):
        from app.infrastructure.secrets import validate_production_secrets

        validate_production_secrets()  # no raise
