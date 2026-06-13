"""Polarized training ratio validation.

Validates and adjusts the 80/20 polarized training distribution **by
volume**, not by session count.

The previous implementation divided quality-session count by total run
count: two quality days out of five runs read as "40% hard" and the second
slot was stripped — for every runner below ~7 runs/week, at any volume.
But polarized training is defined over training volume (time/km): an 8 km
tempo plus 5 km of intervals inside an 85 km week is ~15% hard, textbook
80/20. The km share each quality type receives is exactly its phase-
distribution percentage (times granted slots — multi-slot types draw the
budget per session, see ``calculate_quality_distances`` and the
orchestrator's per-day lookup), so that is what we validate against.
"""

from typing import Dict, Optional

from app.core.training.long_run_calculator import get_phase_distribution
from app.core.training.trail_profile import is_trail_target
from app.core.training.tuning import (
    HARD_TARGETS_ROAD,
    HARD_TARGETS_TRAIL,
    POLARIZED_DEFICIT_THRESHOLD,
    POLARIZED_EXCESS_THRESHOLD,
)

_QUALITY_TYPES = ("interval", "tempo", "hill")


def hard_volume_share(
    distribution: Dict[str, int],
    phase: str,
    target_distance: float,
    trail_profile=None,
    terrain: Optional[str] = None,
) -> float:
    """Estimated fraction of weekly km run at quality intensity.

    Each granted quality slot draws its type's phase-budget percentage of
    the week (the budgeting path hands every session of a type the full
    type percentage), so the planned hard-volume share is the sum of
    pct[type] * slots[type] over granted types.
    """
    phase_dist = get_phase_distribution(
        phase,
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )
    return sum(
        phase_dist.get(qtype, 0.0) * distribution.get(qtype, 0)
        for qtype in _QUALITY_TYPES
        if distribution.get(qtype, 0) > 0
    )


def validate_polarized_ratio(
    distribution: Dict[str, int],
    phase: str,
    target_distance: float,
    trail_profile=None,
    terrain: Optional[str] = None,
    suppress_increase: bool = False,
) -> Dict[str, int]:
    """Validate the polarized volume split and adjust slots if needed.

    Trail gets slightly easier targets (85/15 build, 80/20 peak) because
    terrain naturally provides intensity through elevation. Flat-trail plans
    keep the road target since they aren't getting hill-driven intensity.
    """
    is_trail = is_trail_target(target_distance, trail_profile)
    if terrain == "flat":
        # Training on flat terrain has no climb-driven intensity.
        is_trail = False
    if trail_profile is not None and trail_profile.elevation_class == "flat":
        # Flat trail: no terrain-driven intensity -> use the road polarized target.
        is_trail = False
    hard_targets = HARD_TARGETS_TRAIL if is_trail else HARD_TARGETS_ROAD

    hard_count = sum(distribution.get(t, 0) for t in _QUALITY_TYPES)
    total_runs = hard_count + distribution.get("easy", 0) + distribution.get("long", 0)
    if total_runs == 0:
        return distribution

    hard_pct = hard_volume_share(
        distribution,
        phase,
        target_distance,
        trail_profile=trail_profile,
        terrain=terrain,
    )
    target = hard_targets.get(phase, 0.20)

    # Too much hard volume: shed one quality slot, largest contributor first,
    # but never below one quality in build/peak/taper (the single build/peak
    # session and the taper sharpener are deliberate — audit G2).
    if hard_pct > target + POLARIZED_EXCESS_THRESHOLD and hard_count > 1:
        phase_dist = get_phase_distribution(
            phase, target_distance, terrain=terrain, trail_profile=trail_profile
        )
        biggest = max(
            (t for t in _QUALITY_TYPES if distribution.get(t, 0) > 0),
            key=lambda t: phase_dist.get(t, 0.0),
            default=None,
        )
        if biggest:
            distribution[biggest] -= 1
            distribution["easy"] = distribution.get("easy", 0) + 1
    # Too little hard volume in build/peak: convert one easy run to intervals.
    # Two guards: the build on-ramp (first two build weeks deliberately run
    # one light quality slot — suppress_increase) and a landing check so the
    # added slot cannot itself blow past the polarized ceiling.
    # The frequency guard (easy >= 2 after the add) keeps 4-run weeks at the
    # classic long + quality + 2 easy shape: converting their second easy run
    # makes every other run hard, and with one easy run absorbing the budget
    # the nominal phase percentages understate the slot's real km share
    # (observed 30-32% hard at 4 runs/week vs the 25% ceiling).
    elif (
        phase in ("build", "peak")
        and not suppress_increase
        and hard_pct < target - POLARIZED_DEFICIT_THRESHOLD
        and distribution.get("easy", 0) >= 3
        and total_runs >= 3
    ):
        phase_dist = get_phase_distribution(
            phase, target_distance, terrain=terrain, trail_profile=trail_profile
        )
        landing = hard_pct + phase_dist.get("interval", 0.0)
        if landing <= target + POLARIZED_EXCESS_THRESHOLD:
            distribution["easy"] -= 1
            distribution["interval"] = distribution.get("interval", 0) + 1

    return distribution
