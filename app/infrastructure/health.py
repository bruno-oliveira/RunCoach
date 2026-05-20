"""Health-check response schema, kept in the infrastructure layer.

Lives here rather than in app/schemas so the pure schema layer no longer
depends on app.infrastructure.config (settings) — closing the upstream
dependency leak.
"""

from pydantic import BaseModel, Field

from app.infrastructure.config import settings


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "healthy"
    version: str = Field(default_factory=lambda: settings.app_version)
