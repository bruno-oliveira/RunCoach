"""Goal-aware, progressive pace model.

Bridges a runner's CURRENT fitness and their GOAL race time so that every
training pace is grounded in the goal rather than only the dedicated race-pace
session. Two ideas drive it:

1. **Progressive blend (Runna-style).** A goal VDOT is derived from the goal
   time at the target distance. Each week trains off a *blended* VDOT that
   ramps from current fitness (early weeks) toward the goal VDOT (race weeks),
   so easy / threshold / interval paces sharpen across the block instead of
   sitting at a single static value. Race-pace rehearsal is always prescribed
   at the *exact* goal pace regardless of week.

2. **Distance-aware race pace.** Race pace is not a fixed "hardest" rung. It is
   the predicted race pace at the target distance for the active VDOT, which
   naturally lands where it physiologically belongs: a 5K goal pace sits near
   threshold/VO2max, a marathon goal pace near marathon/tempo. Because every
   band (E/M/T/I/R) and the race pace come from the same VDOT, the intensity
   ladder is monotonic by construction — fixing the old inverted display where
   "zone 5 race" could be slower than "zone 4 VO2max".

Pure logic: no I/O, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from app.core.training.race_predictor import predict_time_for_distance
from app.core.training.vdot_calculator import VDOTCalculator

# Daniels zone closest to race pace for each road race distance. Used only to
# *describe* where the goal pace falls in the runner's training zones; the pace
# value itself is always the exact goal pace (or the predicted race pace).
# 5K ~ between threshold and VO2max, 10K ~ threshold, half ~ marathon/threshold,
# marathon ~ marathon pace.
RACE_PACE_ZONE_BY_DISTANCE = [
    (7.5, "I"),  # <= 7.5 km (5K and shorter): near VO2max / fast threshold
    (15.0, "T"),  # 10K-ish: threshold
    (30.0, "M"),  # half marathon: marathon-to-threshold
    (float("inf"), "M"),  # marathon and ultra: marathon pace
]


@dataclass(frozen=True)
class GoalPaceContext:
    """Resolved fitness anchors for a goal-oriented plan.

    Attributes:
        current_vdot: VDOT implied by the runner's current pace/fitness.
        goal_vdot: VDOT implied by the goal time at the target distance.
        goal_pace_min_km: The exact goal pace (min/km) the runner is chasing.
        target_distance_km: Race distance the plan targets.
    """

    current_vdot: Optional[float]
    goal_vdot: Optional[float]
    goal_pace_min_km: Optional[float]
    target_distance_km: float


def goal_vdot_from_time(
    target_distance_km: float, goal_seconds: Optional[int]
) -> Optional[float]:
    """VDOT implied by a goal finish time at the target distance."""
    if not goal_seconds or goal_seconds <= 0 or target_distance_km <= 0:
        return None
    return VDOTCalculator.calculate_vdot(target_distance_km, goal_seconds)


def blend_fraction(week: int, total_weeks: int) -> float:
    """Fraction of the current->goal VDOT gap closed by a given week.

    Week 1 sits at the current end (~0.0); the final week reaches the goal
    end (1.0). A single-week plan trains fully at goal fitness.
    """
    if total_weeks <= 1:
        return 1.0
    return max(0.0, min(1.0, (week - 1) / (total_weeks - 1)))


def blended_vdot(
    current_vdot: Optional[float],
    goal_vdot: Optional[float],
    week: int,
    total_weeks: int,
) -> Optional[float]:
    """VDOT to train at in *week* — ramped from current toward goal fitness.

    Falls back to whichever anchor is available when one is missing.
    """
    if current_vdot is None:
        return goal_vdot
    if goal_vdot is None:
        return current_vdot
    fraction = blend_fraction(week, total_weeks)
    return round(current_vdot + (goal_vdot - current_vdot) * fraction, 1)


def race_pace_min_km(vdot: float, target_distance_km: float) -> Optional[float]:
    """Predicted race pace (min/km) for *vdot* at the target distance."""
    seconds = predict_time_for_distance(vdot, target_distance_km)
    if not seconds:
        return None
    return (seconds / 60.0) / target_distance_km


def race_pace_zone_label(target_distance_km: float) -> str:
    """Daniels zone key whose pace the race pace sits closest to."""
    for ceiling, zone in RACE_PACE_ZONE_BY_DISTANCE:
        if target_distance_km <= ceiling:
            return zone
    return "M"


def progressive_pace_zones(
    ctx: GoalPaceContext,
    week: int,
    total_weeks: int,
) -> Dict[str, Dict]:
    """Daniels pace zones for *week*, blended toward the goal and race-pinned.

    Returns the same shape as ``VDOTCalculator.get_pace_zones`` (keys
    ``E``/``M``/``T``/``I``/``R`` plus race entries) computed from the blended
    VDOT, with a ``race`` entry pinned to the exact goal pace so race-pace
    rehearsals are always at the goal regardless of week.
    """
    vdot = blended_vdot(ctx.current_vdot, ctx.goal_vdot, week, total_weeks)
    if vdot is None:
        # No fitness anchors at all — caller must fall back to its own defaults.
        return {}

    zones = VDOTCalculator.get_pace_zones(vdot, ctx.target_distance_km)

    if ctx.goal_pace_min_km:
        goal_entry = {
            "pace_min_km": round(ctx.goal_pace_min_km, 2),
            "pace_str": VDOTCalculator.format_pace(ctx.goal_pace_min_km),
            "description": "Goal race pace",
            "zone_label": race_pace_zone_label(ctx.target_distance_km),
        }
        zones["race"] = goal_entry
        # Pin the target distance's race-pace label to the *exact* goal pace so
        # goal-pace REHEARSAL sessions (e.g. "10K goal pace segments") render
        # the runner's literal target every week, not the blended-VDOT predicted
        # race pace which only converges to the goal in the final week. Other
        # distance labels (a 10K plan's "5K" reference) stay predicted.
        label = _target_distance_label(ctx.target_distance_km)
        if label and label in zones:
            zones[label] = {**zones[label], **goal_entry}
    return zones


def _target_distance_label(target_distance_km: float) -> Optional[str]:
    """Race-pace dict key that names the plan's target distance, if standard."""
    if abs(target_distance_km - 5.0) < 0.5:
        return "5K"
    if abs(target_distance_km - 10.0) < 0.5:
        return "10K"
    # Non-5K/10K targets are keyed "race" by VDOTCalculator.get_pace_zones.
    return "race"
