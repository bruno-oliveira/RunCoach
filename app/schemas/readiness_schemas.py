"""Pydantic schemas for the daily readiness check-in."""

from __future__ import annotations

from datetime import date as date_cls
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils import sanitize_user_text

# The self-reported inputs that carry a readiness score. At least one must be
# present for a check-in to mean anything.
_SCORED_FIELDS = ("sleep_hours", "sleep_quality", "energy", "soreness", "stress")


class ReadinessCheckInCreate(BaseModel):
    """A morning check-in. Every field is optional (15-second capture), but at
    least one felt/sleep input is required."""

    sleep_hours: Optional[float] = Field(
        None, ge=0, le=24, description="Hours slept last night"
    )
    sleep_quality: Optional[int] = Field(
        None, ge=1, le=5, description="Sleep quality (1 awful – 5 great)"
    )
    energy: Optional[int] = Field(
        None, ge=1, le=5, description="Energy / mood (1 drained – 5 buzzing)"
    )
    soreness: Optional[int] = Field(
        None, ge=1, le=5, description="Muscle soreness (1 fresh – 5 wrecked)"
    )
    stress: Optional[int] = Field(
        None, ge=1, le=5, description="Life stress (1 calm – 5 frazzled)"
    )
    resting_hr: Optional[int] = Field(
        None, ge=25, le=150, description="Resting heart rate (bpm)"
    )
    hrv: Optional[float] = Field(
        None, ge=0, le=400, description="Heart-rate variability (ms)"
    )
    notes: Optional[str] = Field(None, max_length=500, description="Free-text note")
    date: Optional[date_cls] = Field(
        None, description="Calendar day (defaults to today)"
    )

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_user_text(v)

    @model_validator(mode="after")
    def _require_one_input(self) -> "ReadinessCheckInCreate":
        if all(getattr(self, f) is None for f in _SCORED_FIELDS):
            raise ValueError(
                "Provide at least one of: sleep hours, sleep quality, energy, "
                "soreness, or stress."
            )
        return self


class ReadinessCheckInResponse(BaseModel):
    """A stored check-in plus its derived score, band, and drivers."""

    id: str
    date: date_cls
    sleep_hours: Optional[float] = None
    sleep_quality: Optional[int] = None
    energy: Optional[int] = None
    soreness: Optional[int] = None
    stress: Optional[int] = None
    resting_hr: Optional[int] = None
    hrv: Optional[float] = None
    notes: Optional[str] = None
    score: Optional[float] = None
    band: str = "unknown"
    label: str = "No check-in"
    drivers: List[str] = Field(default_factory=list)
