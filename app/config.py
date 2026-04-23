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
    min_mileage_30k: float = 15.0
    min_mileage_marathon: float = 25.0

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

    # Security
    enable_debug_endpoints: bool = False
    encryption_key: str = ""

    # Feature Flags

    # Plan limits
    max_plans_per_user: int = 3

    # Mileage max thresholds and warnings
    max_mileage_5k: int = 40
    max_mileage_10k: int = 50
    max_mileage_half: int = 70
    max_mileage_30k: int = 60
    max_mileage_marathon: int = 100

    low_mileage_msg_5k: str = (
        "Your current mileage is quite low for 5K training. "
        "Consider building a base with 2-3 weeks of easy running first."
    )
    high_mileage_msg_5k: str = (
        "You're already running high mileage for 5K. "
        "Consider focusing on speed work rather than volume."
    )
    low_mileage_msg_10k: str = (
        "Your current mileage may be insufficient for 10K training. "
        "Build to at least 10km/week for 2-3 weeks first."
    )
    high_mileage_msg_10k: str = (
        "High mileage for 10K. "
        "You might benefit from focusing on quality over quantity."
    )
    low_mileage_msg_half: str = (
        "Half marathon training requires a stronger base. "
        "Build to 15km/week for 3-4 weeks before starting."
    )
    high_mileage_msg_half: str = (
        "Very high mileage for half marathon. "
        "Ensure adequate recovery and consider periodization."
    )
    low_mileage_msg_30k: str = (
        "Trail running requires a solid base. "
        "Build to 15km/week with some trail experience first."
    )
    high_mileage_msg_30k: str = (
        "High mileage for trail running. "
        "Focus on time on feet rather than distance."
    )
    low_mileage_msg_marathon: str = (
        "Marathon training requires significant base fitness. "
        "Build to 25km/week for 4-6 weeks before beginning."
    )
    high_mileage_msg_marathon: str = (
        "Extremely high mileage. "
        "Be cautious about injury risk and ensure proper recovery."
    )

    # Performance training minimum mileage requirements
    perf_min_mileage_5k: int = 20
    perf_min_mileage_10k: int = 25
    perf_min_mileage_half: int = 35
    perf_min_mileage_marathon: int = 50

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
