"""Pydantic schemas for one-off single runs."""

from datetime import date as date_cls
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

SingleRunType = Literal["easy", "tempo", "interval", "long"]


class SingleRunCreate(BaseModel):
    """Ask for one workout, sized by distance *or* by time."""

    run_type: SingleRunType
    distance_km: Optional[float] = Field(None, gt=0, le=100)
    duration_minutes: Optional[float] = Field(None, gt=0, le=600)
    # The runner's local day; defaults to their today on the server.
    date: Optional[date_cls] = None
    send_to_watch: bool = False

    @model_validator(mode="after")
    def _exactly_one_size(self) -> "SingleRunCreate":
        if (self.distance_km is None) == (self.duration_minutes is None):
            raise ValueError("Give either distance_km or duration_minutes, not both")
        return self


class SingleRunCompletedRun(BaseModel):
    """The logged activity that completed a single run."""

    id: str
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    avg_pace_min_km: Optional[float] = None


class SingleRunResponse(BaseModel):
    id: str
    date: date_cls
    run_type: str
    name: str
    distance_km: float
    description: str
    steps: list[dict[str, Any]]
    # None when the session is prescribed by effort (no fitness on record).
    vdot: Optional[float] = None
    estimated_minutes: Optional[int] = None
    on_watch: bool
    completed_run: Optional[SingleRunCompletedRun] = None
    # Set only on a response to a send: why the watch push did not happen
    # ("not_connected" | "auth" | "provider"). The workout itself was saved.
    watch_error: Optional[str] = None


class SingleRunListResponse(BaseModel):
    single_runs: list[SingleRunResponse]
