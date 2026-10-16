"""What the custom-plan builder page reads: the grid, the options, a preview.

The builder asks two things of the server before the runner commits: which
sessions each cell may hold for *this* goal and frequency, and what the plan
would look like with the current choices. Both are answered by the same core
code generation uses (``app.core.training.custom_plan``), so the page can
never offer a session the generator would refuse, and the preview is the plan
— generated, not persisted.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.engine_floors import enforce_engine_floors
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.custom_plan import (
    CUSTOM_PHASES,
    MAX_SESSIONS_PER_CELL,
    Problem,
    cell_limits,
    default_spec,
    eligible_options,
    plan_shape,
    slot_grid,
)
from app.core.training.frequency import viable_run_frequency
from app.core.training.periodization.phase_calculator import MIN_WEEKS_FOR_PHASES
from app.core.training.profiles.trail_profile import classify_trail
from app.exceptions import RunCoachException
from app.schemas import PlanRequest

PHASE_LABELS = {"base": "Base", "build": "Build", "peak": "Peak", "taper": "Taper"}
SLOT_LABELS = {
    "long": "Long run",
    "quality": "Quality session",
    "speed": "Speed session",
    "threshold": "Threshold or climb session",
}


def _trail_profile(is_trail: bool, target_distance: float, gain_m: Optional[float]):
    if not is_trail:
        return None
    return classify_trail(target_distance, gain_m or 0.0)


def builder_options(
    *,
    target_distance: float,
    runs_per_week: int,
    is_trail: bool = False,
    target_elevation_gain_m: Optional[float] = None,
    training_terrain: Optional[str] = None,
    weeks: Optional[int] = None,
    current_km: Optional[float] = None,
) -> Dict[str, Any]:
    """The grid for this goal and frequency, each cell's options, and defaults.

    With ``weeks``, each cell also says how many choices it may hold
    (``limit``): one per week its phase fills, so none is chosen in vain, and
    ``shape`` lays out the phases those limits come from. With ``current_km``,
    the grid is the one for the frequency the generator will actually run
    (a small base sheds running days), and ``blocker`` carries the reason no
    plan can be built from these basics, so the page can say so before the
    runner spends time choosing.
    """
    trail_profile = _trail_profile(is_trail, target_distance, target_elevation_gain_m)
    terrain = training_terrain or (
        trail_profile.elevation_class if trail_profile is not None else None
    )
    requested = max(3, min(6, runs_per_week))
    runs = viable_run_frequency(current_km, requested) if current_km else requested
    grid = slot_grid(runs)
    limits = cell_limits(
        weeks, target_distance=target_distance, trail_profile=trail_profile
    )
    spans = (
        plan_shape(weeks, target_distance=target_distance, trail_profile=trail_profile)
        if weeks is not None and weeks >= MIN_WEEKS_FOR_PHASES
        else []
    )
    training_weeks = {span.phase: span.training_weeks for span in spans}
    cells: List[Dict[str, Any]] = []
    for phase in CUSTOM_PHASES:
        for slot in grid[phase]:
            options = eligible_options(
                phase,
                slot,
                target_distance=target_distance,
                trail_profile=trail_profile,
                terrain=terrain,
            )
            cells.append(
                {
                    "phase": phase,
                    "phase_label": PHASE_LABELS[phase],
                    "slot": slot.value,
                    "slot_label": SLOT_LABELS[slot.value],
                    "limit": limits[phase],
                    "training_weeks": training_weeks.get(phase),
                    "options": [
                        {
                            "id": o.id,
                            "name": o.name,
                            "structure": o.structure,
                            "rationale": o.rationale,
                            "intensity": o.intensity,
                            "type": o.workout_type,
                        }
                        for o in options
                    ],
                }
            )
    defaults = default_spec(
        runs,
        target_distance=target_distance,
        trail_profile=trail_profile,
        terrain=terrain,
        weeks=weeks,
    )
    return {
        "runs_per_week": runs,
        "requested_runs_per_week": requested,
        "max_per_cell": MAX_SESSIONS_PER_CELL,
        "cells": cells,
        "shape": [
            {
                "phase": span.phase,
                "phase_label": PHASE_LABELS[span.phase],
                "first_week": span.first_week,
                "last_week": span.last_week,
                "weeks": span.weeks,
                "training_weeks": span.training_weeks,
                "recovery_weeks": list(span.recovery_weeks),
            }
            for span in spans
        ],
        "blocker": _blocker(
            current_km, target_distance, weeks, trail_profile=trail_profile
        ),
        "defaults": defaults.to_json(),
    }


def _blocker(
    current_km: Optional[float],
    target_distance: float,
    weeks: Optional[int],
    *,
    trail_profile,
) -> Optional[Dict[str, Optional[str]]]:
    """Why no plan can be built from these basics, worded as creation words it."""
    if not current_km or weeks is None:
        return None
    try:
        enforce_engine_floors(current_km, target_distance, weeks, trail_profile, None)
    except RunCoachException as e:
        return {
            "message": e.user_message,
            "suggestion": getattr(e, "suggestion", None),
        }
    return None


def problems_json(problems: List[Problem]) -> List[Dict[str, Any]]:
    """Keyed problems for the page, which words them itself."""
    return [
        {
            "key": p.key,
            "phase": p.phase,
            "slot": p.slot,
            "workout_id": p.workout_id,
            "limit": p.limit,
        }
        for p in problems
    ]


def _strength_label(day: Dict[str, Any]) -> Optional[str]:
    """ "Climb", "Lower Body"… — the name the plan page gives the session."""
    session = day.get("strength_session") or {}
    focus = session.get("focus") or session.get("type")
    return str(focus).replace("_", " ").title() if focus else None


def _day_summary(day: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "day": day.get("day"),
        "type": day.get("type"),
        "name": day.get("key_workout_name"),
        "distance": day.get("distance"),
        "structure": day.get("structure"),
        "strength": _strength_label(day),
        "deferral_code": day.get("custom_deferral_code"),
    }


def preview(
    plan_request: PlanRequest, plan_generator: TrainingPlanGenerator
) -> Dict[str, Any]:
    """The plan these choices make, summarised: the phase arc and every week.

    Generated exactly as creation would generate it (same request, same
    generator), so what the runner previews is what they get.
    """
    plan = plan_generator.generate_plan(
        plan_request.current_km,
        plan_request.target_distance,
        plan_request.weeks,
        plan_request.max_runs_per_week,
        vdot=plan_request.pacing_vdot,
        terrain=plan_request.resolved_training_terrain(),
        trail_profile=_trail_profile(
            plan_request.is_trail,
            plan_request.target_distance,
            plan_request.target_elevation_gain_m,
        ),
        goal_pace_min_km=plan_request.goal_pace_min_km,
        custom_spec=plan_request.custom_plan_spec(),
    )
    weeks = [
        {
            "week": w.get("week"),
            "phase": w.get("phase"),
            "phase_label": PHASE_LABELS.get(str(w.get("phase")), w.get("phase")),
            "is_recovery": bool(w.get("is_recovery")),
            "total_km": w.get("total_km"),
            "days": [
                _day_summary(d)
                for d in w.get("daily_workouts", [])
                if d.get("type") not in ("rest", "recovery")
            ],
        }
        for w in plan
    ]
    return {
        "weeks": weeks,
        "peak_km": max((w["total_km"] or 0 for w in weeks), default=0),
    }
