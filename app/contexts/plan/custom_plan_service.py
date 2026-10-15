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

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.custom_plan import (
    CUSTOM_PHASES,
    Problem,
    default_spec,
    eligible_options,
    slot_grid,
)
from app.core.training.profiles.trail_profile import classify_trail
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
) -> Dict[str, Any]:
    """The grid for this goal and frequency, each cell's options, and defaults."""
    trail_profile = _trail_profile(is_trail, target_distance, target_elevation_gain_m)
    terrain = training_terrain or (
        trail_profile.elevation_class if trail_profile is not None else None
    )
    runs = max(3, min(6, runs_per_week))
    grid = slot_grid(runs)
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
    )
    return {"runs_per_week": runs, "cells": cells, "defaults": defaults.to_json()}


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


def _day_summary(day: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "day": day.get("day"),
        "type": day.get("type"),
        "name": day.get("key_workout_name"),
        "distance": day.get("distance"),
        "structure": day.get("structure"),
        "strength": (day.get("strength_session") or {}).get("focus"),
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
