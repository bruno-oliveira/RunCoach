"""Pydantic schemas for Intervals.icu integration."""

from typing import List, Optional

from pydantic import BaseModel, Field


class IntervalsSyncResponse(BaseModel):
    synced: int
    skipped: int
    errors: List[str] = []
    total: int = 0
    last_synced_at: Optional[int] = None
    adjustment_results: Optional[List[dict]] = None


class IntervalsPushRequest(BaseModel):
    """Identify one workout to push (mirrors the .fit download addressing)."""

    plan_id: str
    week: int = Field(ge=1)
    day: int = Field(ge=1, le=7)


class IntervalsPushResponse(BaseModel):
    ok: bool
    event_id: Optional[int] = None
    message: str


class IntervalsStatusResponse(BaseModel):
    connected: bool
    athlete_id: Optional[str] = None
    last_synced_at: Optional[int] = None
