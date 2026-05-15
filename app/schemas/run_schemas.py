"""Pydantic schemas for run logging."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.constants import WORKOUT_TYPES
from app.utils import sanitize_user_text


class RunLogBase(BaseModel):
    distance_km: float = Field(..., gt=0, description="Distance in kilometers")
    duration_minutes: float = Field(..., gt=0, description="Duration in minutes")
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=220, description="Average heart rate")
    max_heart_rate: Optional[int] = Field(None, ge=40, le=220, description="Maximum heart rate")
    avg_cadence: Optional[int] = Field(None, ge=100, le=220, description="Average cadence (steps per minute)")
    elevation_gain_m: Optional[int] = Field(None, ge=0, description="Elevation gain in meters")
    notes: Optional[str] = Field(None, max_length=1000, description="Run notes")
    workout_type: Optional[str] = Field(None, description="Workout type: easy, tempo, interval, long, hill")
    perceived_effort: Optional[int] = Field(None, ge=1, le=10, description="Perceived effort (1-10)")

    @field_validator("workout_type")
    @classmethod
    def validate_workout_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if v not in WORKOUT_TYPES:
                raise ValueError(f"workout_type must be one of: {', '.join(WORKOUT_TYPES)}")
        return v

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_user_text(v)


class RunLogCreate(RunLogBase):
    date: Optional[datetime] = Field(None, description="Run date and time (defaults to now)")
    training_plan_id: Optional[str] = Field(None, description="Associated training plan ID")
    daily_workout_id: Optional[str] = Field(None, description="Associated daily workout ID")


class RunLogUpdate(BaseModel):
    distance_km: Optional[float] = Field(None, gt=0, le=1000)
    duration_minutes: Optional[float] = Field(None, gt=0, le=6000)
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    max_heart_rate: Optional[int] = Field(None, ge=40, le=220)
    avg_cadence: Optional[int] = Field(None, ge=100, le=220)
    elevation_gain_m: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=1000)
    workout_type: Optional[str] = Field(None)
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    date: Optional[datetime] = None

    @field_validator("workout_type")
    @classmethod
    def validate_workout_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if v not in WORKOUT_TYPES:
                raise ValueError(f"workout_type must be one of: {', '.join(WORKOUT_TYPES)}")
        return v

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_user_text(v)


class RunLogResponse(RunLogBase):
    id: str
    date: datetime
    avg_pace_min_km: Optional[float] = None
    strava_activity_id: Optional[str] = None
    effort_quality_score: Optional[float] = None
    quality_label: Optional[str] = None
    vdot: Optional[float] = None
    predicted_time_seconds: Optional[float] = None
    created_at: datetime
    predictions: Optional[Dict[str, Dict]] = None
    race_comparison: Optional[Dict[str, Any]] = None
    vdot_recalibration: Optional[Dict[str, Any]] = None
    auto_adjust: Optional[Dict[str, Any]] = None


class RunLogListResponse(BaseModel):
    runs: List[RunLogResponse]
    total: int
    page: int
    page_size: int
