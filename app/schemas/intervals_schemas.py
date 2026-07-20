"""Pydantic schemas for Intervals.icu integration."""

from typing import List, Optional

from pydantic import BaseModel


class IntervalsSyncResponse(BaseModel):
    synced: int
    skipped: int
    errors: List[str] = []
    total: int = 0
    last_synced_at: Optional[int] = None
    adjustment_results: Optional[List[dict]] = None


class IntervalsStatusResponse(BaseModel):
    connected: bool
    athlete_id: Optional[str] = None
    last_synced_at: Optional[int] = None
