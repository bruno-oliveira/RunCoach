"""Centralized configuration for RunCoach application."""

import logging
from functools import lru_cache
from typing import Literal

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

    # Training plan constraints
    min_weeks_5k: int = 4
    min_weeks_10k: int = 6
    min_weeks_half: int = 8
    min_weeks_30k: int = 6  # Trail running (30km)
    min_weeks_marathon: int = 12

    max_weeks_5k: int = 16
    max_weeks_10k: int = 16
    max_weeks_half: int = 20
    max_weeks_30k: int = 20  # Trail running (30km)
    max_weeks_marathon: int = 24

    # Mileage constraints
    min_mileage_5k: float = 5.0
    min_mileage_10k: float = 10.0
    min_mileage_half: float = 15.0
    min_mileage_30k: float = 8.0
    min_mileage_marathon: float = 25.0

    # OAuth / Authentication
    secret_key: str = "your-secret-key-change-in-production"
    google_client_id: str = ""

    # Session settings
    session_timeout_minutes: int = 30
    anonymous_cookie_max_age: int = 30 * 24 * 60 * 60

    # Feature Flags


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
