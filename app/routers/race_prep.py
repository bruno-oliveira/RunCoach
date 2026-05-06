"""Race Prep feature - API endpoints and page rendering."""

import logging
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_optional_user
from app.models import RunLog, User
from app.schemas.race_prep_schemas import GPXAnalysisResponse, RaceBlueprint, RacePrepRequest
from app.services.integrations.gpx_service import GPXService
from app.services.fitness.race_pacing_service import RacePacingService
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["race-prep"])
templates = create_templates()

_blueprint_store: dict[str, dict[str, Any]] = {}


def _count_user_trail_runs(user_id: str, db: Session) -> int:
    """Count the user's prior runs that average >=20 m of climb per km."""
    runs = (
        db.query(RunLog.distance_km, RunLog.elevation_gain_m)
        .filter(
            RunLog.user_id == user_id,
            RunLog.distance_km > 0,
            RunLog.elevation_gain_m.isnot(None),
        )
        .all()
    )
    return sum(
        1
        for distance_km, gain in runs
        if distance_km and gain and gain / distance_km >= 20.0
    )


@router.get("/race-prep", response_class=HTMLResponse)
async def race_prep_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the Race Prep upload page."""
    vdot_info = {"vdot": 0.0, "run_count": 0, "confidence": "low"}

    if current_user:
        vdot_info = RacePacingService.get_user_vdot(current_user.id, db)

    return templates.TemplateResponse("race_prep.html", {
        "request": request,
        "user": current_user,
        "current_vdot": vdot_info["vdot"],
        "vdot_run_count": vdot_info["run_count"],
        "vdot_confidence": vdot_info["confidence"],
    })


@router.post("/api/race-prep/analyze")
async def analyze_gpx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> GPXAnalysisResponse:
    """Upload a GPX file and receive route analysis with auto-estimated finish time."""
    if not file.filename or not file.filename.lower().endswith(".gpx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a valid .gpx file",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GPX file too large (max 10MB)",
        )

    try:
        parsed = GPXService.parse_gpx(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    elevation_profile = GPXService.build_elevation_profile(parsed["trackpoints"])

    vdot_info = {"vdot": 0.0, "run_count": 0, "confidence": "low"}
    if current_user:
        vdot_info = RacePacingService.get_user_vdot(current_user.id, db)

    user_vdot = vdot_info["vdot"]
    distance_km = parsed["distance_km"]

    if user_vdot > 0:
        trail_runs_count = (
            _count_user_trail_runs(current_user.id, db) if current_user else None
        )
        time_data = RacePacingService.predict_elevation_adjusted_time(
            user_vdot, distance_km, elevation_profile, trail_runs_count=trail_runs_count
        )
        flat_time = time_data["flat_time"]
        elevation_adjusted = time_data["elevation_adjusted"]
        elevation_penalty = time_data["elevation_penalty"]
    else:
        flat_time = 0
        elevation_adjusted = 0
        elevation_penalty = 0

    feasibility = RacePacingService.validate_feasibility(
        elevation_adjusted if elevation_adjusted > 0 else flat_time,
        flat_time,
        elevation_adjusted,
    )

    return GPXAnalysisResponse(
        distance_km=parsed["distance_km"],
        total_elevation_gain=parsed["elevation_gain"],
        max_elevation=parsed["max_elevation"],
        min_elevation=parsed["min_elevation"],
        flat_estimate_seconds=flat_time,
        elevation_adjusted_seconds=elevation_adjusted,
        elevation_penalty_seconds=elevation_penalty,
        user_vdot=user_vdot,
        vdot_run_count=vdot_info["run_count"],
        vdot_confidence=vdot_info["confidence"],
        feasibility=feasibility,
        elevation_profile=[
            {
                "start_km": s["start_km"],
                "end_km": s["end_km"],
                "avg_elevation": s["avg_elevation"],
                "grade_pct": s["grade_pct"],
                "net_grade_pct": s.get("net_grade_pct", 0.0),
                "elevation_gain": s.get("elevation_gain", 0.0),
                "elevation_loss": s.get("elevation_loss", 0.0),
            }
            for s in elevation_profile
        ],
        trackpoints=parsed["trackpoints"],
    )


@router.post("/api/race-prep/blueprint")
async def generate_blueprint(
    request: RacePrepRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> dict:
    """Generate a segment-by-segment pacing blueprint."""
    elevation_profile = [s.model_dump() for s in request.elevation_profile]

    for idx, seg in enumerate(elevation_profile):
        seg["segment_number"] = idx + 1

    if not elevation_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Elevation profile is required",
        )

    vdot_info = {"vdot": 0.0, "run_count": 0, "confidence": "low"}
    if current_user:
        vdot_info = RacePacingService.get_user_vdot(current_user.id, db)

    user_vdot = vdot_info["vdot"]
    if user_vdot <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No VDOT data available. Log some runs first to get race predictions.",
        )

    distance_km = request.distance_km or elevation_profile[-1]["end_km"]
    target_time = request.target_time_seconds
    trail_runs_count = _count_user_trail_runs(current_user.id, db)

    if target_time is None or target_time <= 0:
        target_time = RacePacingService.predict_elevation_adjusted_time(
            user_vdot, distance_km, elevation_profile,
            trail_runs_count=trail_runs_count,
        )["elevation_adjusted"]

    blueprint = RacePacingService.generate_pace_blueprint(
        elevation_profile=elevation_profile,
        target_time_seconds=target_time,
        user_vdot=user_vdot,
        distance_km=distance_km,
        trail_runs_count=trail_runs_count,
    )

    session_id = str(uuid.uuid4())
    _blueprint_store[session_id] = {
        "blueprint": blueprint.model_dump(),
        "created_at": time.time(),
    }

    while len(_blueprint_store) > 100:
        oldest_key = min(_blueprint_store, key=lambda k: _blueprint_store[k]["created_at"])
        del _blueprint_store[oldest_key]

    blueprint_dict = blueprint.model_dump()
    blueprint_dict["session_id"] = session_id
    return blueprint_dict
