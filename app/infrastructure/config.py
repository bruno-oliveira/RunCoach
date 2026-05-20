"""Centralized configuration for RunCoach application."""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    secret_key: str = Field(default_factory=lambda: __import__("secrets").token_urlsafe(32))
    # NOTE: In production, SECRET_KEY must be set as a persistent environment
    # variable (e.g. Fly.io secret) so JWTs survive cold starts.
    # The random default is for local development only.
    google_client_id: str = ""

    # Session settings
    session_timeout_minutes: int = 1440  # 24 hours — matches JWT cookie lifespan
    anonymous_cookie_max_age: int = 30 * 24 * 60 * 60

    # Strava OAuth
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/strava/callback"
    strava_initial_sync_days: int = 365

    # Security
    enable_debug_endpoints: bool = False
    encryption_key: str = ""
    force_secure_cookies: bool = True
    max_request_body_bytes: int = 1_048_576  # 1 MB

    # Feature Flags

    # Plan limits
    max_plans_per_user: int = 3

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
