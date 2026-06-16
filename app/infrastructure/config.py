"""Centralized configuration for RunCoach application."""

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "RunCoach"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./runcoach.db"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Per-distance training constraints live in
    # ``app.core.training.training_config.DISTANCE_CONSTRAINTS``.

    # OAuth / Authentication
    secret_key: str = ""
    # NOTE: In production, SECRET_KEY must be set as a persistent environment
    # variable (e.g. Fly.io secret) so JWTs survive cold starts. When unset,
    # ``_require_secret_key`` raises in production and generates an ephemeral
    # development key only when DEBUG is enabled.
    # SECRET_KEY_PREVIOUS lets us rotate the JWT signing key without immediate
    # logout: new tokens are signed with secret_key; verification falls back
    # to secret_key_previous so existing sessions keep working through the
    # rollover window. Clear once all old tokens have expired (24h default).
    secret_key_previous: str = ""
    google_client_id: str = ""

    # Session settings
    session_timeout_minutes: int = 1440  # 24 hours — matches JWT cookie lifespan
    anonymous_cookie_max_age: int = 30 * 24 * 60 * 60

    # Strava OAuth
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/strava/callback"
    strava_initial_sync_days: int = 365

    # Coach AI — the LLM-voiced "Coach's Note". When the API key is unset the
    # feature degrades to a deterministic, rules-based note (no network).
    anthropic_api_key: str = ""
    coach_ai_model: str = "claude-haiku-4-5"

    # Security
    enable_debug_endpoints: bool = False
    encryption_key: str = ""
    # Previous ENCRYPTION_KEY used during a rotation window. Encryption is
    # always performed with ``encryption_key``; on decryption we fall back to
    # ``encryption_key_previous`` so rows encrypted with the old key keep
    # decoding. Clear once all rows have been re-encrypted under the new key.
    encryption_key_previous: str = ""
    force_secure_cookies: bool = True
    max_request_body_bytes: int = 1_048_576  # 1 MB
    # Number of trusted reverse-proxy hops in front of the app. The rate
    # limiter takes the IP at position -trusted_proxy_hops from the
    # X-Forwarded-For chain (the right-most trusted hop), so a client that
    # injects spoofed IPs upstream cannot grow its rate-limit budget.
    # 1 matches Fly.io (single edge proxy); set to 0 on deployments where
    # the app is reached directly, or higher behind additional proxies.
    trusted_proxy_hops: int = 1
    # CORS allowed origins. Comma-separated env var, e.g.
    # ``ALLOWED_ORIGINS=https://runcoach.fly.dev,https://example.com``.
    # Defaults to localhost for development; production must override.
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000"]
    )

    # JWT lifetimes
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # Feature Flags — environment-driven boolean toggles. Look up via
    # ``settings.is_enabled("flag_name")``. Unknown flags default False.
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    # Plan limits
    max_plans_per_user: int = 3

    @model_validator(mode="after")
    def _require_secret_key(self) -> "Settings":
        """Fail fast in production when no persistent SECRET_KEY is configured.

        Mirrors the ``encryption_key`` guard: an unset signing key would
        silently rotate on every cold start (logging everyone out) and differ
        between workers. In development we tolerate an ephemeral random key.
        """
        if not self.secret_key:
            if self.debug:
                self.secret_key = secrets.token_urlsafe(32)
            else:
                raise ValueError(
                    "SECRET_KEY must be set in production (DEBUG=False). "
                    "Configure it as a persistent secret so JWTs survive "
                    "restarts and are consistent across workers."
                )
        return self

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v):
        """Allow comma-separated env-var input for allowed_origins."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("feature_flags", mode="before")
    @classmethod
    def _parse_feature_flags(cls, v):
        """Allow comma-separated env-var input like ``FEATURE_FLAGS=a=true,b=false``."""
        if isinstance(v, str):
            parsed: dict[str, bool] = {}
            for item in v.split(","):
                if "=" in item:
                    k, val = item.split("=", 1)
                    parsed[k.strip()] = val.strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )
            return parsed
        return v

    def is_enabled(self, flag: str) -> bool:
        """Return True if the named feature flag is enabled."""
        return self.feature_flags.get(flag, False)

    @property
    def is_coach_ai_enabled(self) -> bool:
        """True when an Anthropic API key is configured for the Coach's Note."""
        return bool(self.anthropic_api_key.strip())

    @property
    def is_google_client_id_configured(self) -> bool:
        """Check whether the Google Client ID looks valid (not empty/placeholder)."""
        cid = self.google_client_id
        if not cid or cid == "null" or len(cid) < 20:
            return False
        if any(p in cid.lower() for p in ("your-google", "placeholder")):
            return False
        return True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def setup_logging(settings: Settings) -> None:
    """Configure application logging."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=log_format,
        handlers=[logging.StreamHandler()],
    )


# Convenience access to settings
settings = get_settings()
