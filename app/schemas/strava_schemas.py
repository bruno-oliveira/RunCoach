"""Pydantic schemas for Strava integration."""

from typing import List, Optional

from pydantic import BaseModel


class StravaSyncResponse(BaseModel):
    """Response for Strava sync operation."""

    synced: int
    skipped: int
    errors: List[str] = []
    total: int = 0
    last_synced_at: Optional[int] = None
    adjustment_results: Optional[List[dict]] = None


class StravaStatusResponse(BaseModel):
    """Response for Strava connection status."""

    connected: bool
    athlete_id: Optional[str] = None
    last_synced_at: Optional[int] = None
