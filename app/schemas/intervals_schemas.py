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


class IntervalsPushWeekRequest(BaseModel):
    """Identify one plan week to push in full."""

    plan_id: str
    week: int = Field(ge=1)


class IntervalsPushWeekResponse(BaseModel):
    ok: bool
    sent: int
    skipped: int
    message: str


class IntervalsStatusResponse(BaseModel):
    connected: bool
    athlete_id: Optional[str] = None
    last_synced_at: Optional[int] = None


class WatchSyncToggleRequest(BaseModel):
    """Turn the standing "keep my watch in sync" mirror on or off for a plan."""

    plan_id: str
    enabled: bool


class WatchPlanRequest(BaseModel):
    """Identify a plan for a watch action that needs no other input."""

    plan_id: str


class WatchStatusResponse(BaseModel):
    """What is actually on the runner's calendar, not what we once sent.

    ``events_on_calendar`` is read back from Intervals.icu and is ``None`` when
    that read failed — the UI must say "couldn't check" rather than invent a
    number, which is the whole point of this endpoint.
    """

    connected: bool
    sync_enabled: bool
    sessions_behind: int = 0
    events_on_calendar: Optional[int] = None
    last_synced_at: Optional[str] = None
    error: Optional[str] = None
    calendar_url: str = "https://intervals.icu/calendar"
