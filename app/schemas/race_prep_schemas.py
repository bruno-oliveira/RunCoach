"""Pydantic schemas for the Race Prep feature."""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.core.training.environment import EnvironmentalConditions


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
    net_grade_pct: float = 0.0
    elevation_gain: float = 0.0
    elevation_loss: float = 0.0


class RacePrepRequest(BaseModel):
    """Request to generate a pacing blueprint."""

    target_time_seconds: int | None = None
    distance_km: float | None = None
    elevation_profile: list[ElevationSegment]
    # Optional race-day conditions for heat/altitude-aware pacing.
    race_temp_c: float | None = None
    race_humidity_pct: float | None = None
    race_altitude_m: float | None = None

    def race_conditions(self) -> "EnvironmentalConditions | None":
        """Build conditions from the optional inputs, or ``None`` if empty."""
        from app.core.training.environment import EnvironmentalConditions

        return EnvironmentalConditions.from_inputs(
            temp_c=self.race_temp_c,
            humidity_pct=self.race_humidity_pct,
            altitude_m=self.race_altitude_m,
        )


class RaceSegment(BaseModel):
    """Single segment in a race pacing blueprint."""

    segment_number: int
    start_km: float
    end_km: float
    elevation_m: float
    grade_pct: float
    net_grade_pct: float = 0.0
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
    # Heat-driven slowdown folded into ``estimated_time_seconds`` (0 when no
    # race-day conditions were supplied).
    heat_penalty_seconds: int = 0
    # Runner-facing explanation of the heat/altitude adjustment, if any.
    conditions_note: str | None = None
