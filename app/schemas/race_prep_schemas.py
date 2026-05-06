"""Pydantic schemas for the Race Prep feature."""

from typing import Any

from pydantic import BaseModel, Field


class FeasibilityInfo(BaseModel):
    """Feasibility assessment for a target race time."""

    label: str
    message: str
    color: str


class GPXAnalysisResponse(BaseModel):
    """Response after uploading and analyzing a GPX file."""

    distance_km: float
    total_elevation_gain: float
    max_elevation: float
    min_elevation: float
    flat_estimate_seconds: int
    elevation_adjusted_seconds: int
    elevation_penalty_seconds: int
    vdot_enhanced_seconds: int | None = None
    user_vdot: float
    vdot_run_count: int
    vdot_confidence: str
    feasibility: FeasibilityInfo
    elevation_profile: list[dict[str, Any]] = []
    trackpoints: list[dict[str, Any]] = []


class ElevationSegment(BaseModel):
    """Single elevation segment from GPX analysis."""

    start_km: float
    end_km: float
    avg_elevation: float
    grade_pct: float


class RacePrepRequest(BaseModel):
    """Request to generate a pacing blueprint."""

    target_time_seconds: int | None = None
    distance_km: float | None = None
    elevation_profile: list[ElevationSegment]


class RaceSegment(BaseModel):
    """Single segment in a race pacing blueprint."""

    segment_number: int
    start_km: float
    end_km: float
    elevation_m: float
    grade_pct: float
    target_pace_min_km: float
    target_pace_str: str
    target_time_seconds: int
    cumulative_time_seconds: int


class RaceBlueprint(BaseModel):
    """Complete race pacing blueprint."""

    segments: list[RaceSegment]
    total_distance_km: float
    target_time_seconds: int
    target_time_str: str
    estimated_time_seconds: int
    user_vdot: float
    feasibility: FeasibilityInfo
