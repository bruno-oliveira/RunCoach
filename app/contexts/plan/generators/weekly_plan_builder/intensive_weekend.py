"""Trail Intensive Training Weekend (ITW) reshaping for a peak week."""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.weekly_plan_builder.budget import (
    build_workout_for_type,
)
from app.contexts.plan.generators.workout_scaler import (
    set_distance as _set_distance,
)
from app.core.training import phase_calculator
from app.core.training.key_workout_library import overlay_key_workout

# Intensive Training Weekend (ITW) shaping: the Saturday trail-quality budget is
# a fraction of the displaced long run, capped; Thu/Fri easy days are trimmed so
# the weekend lands on fresher legs.
_ITW_QUALITY_BUDGET_FRACTION = 0.5
_ITW_QUALITY_BUDGET_CAP_KM = 12.0
_ITW_LEADIN_TRIM_FACTOR = 0.8


def apply_intensive_weekend(
    workouts: List[Dict[str, Any]],
    phase: str,
    week_number: int,
    phases: Dict[str, int],
    week_in_phase: int,
    total_km: float,
    target_distance: float,
    pace_zones: Optional[Dict],
    trail_profile,
    terrain: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Reshape one peak week into a trail Intensive Training Weekend (ITW).

    Swaps the Saturday long for a trail-quality session (pyramid/ladder on
    flat/rolling, elevation repeats on hilly/mountainous) and moves the long
    run onto Sunday as a hike-run (ultra) or back-to-back fatigued long. The
    Thu/Fri lead-in easy days are trimmed so the weekend lands on fresher legs.

    Both weekend days carry a ``key_workout_id`` so the downstream scaling
    passes treat them as prescriptive and leave their distances intact. Runs
    before ``scale_down`` in :func:`build_weekly_plan`. Returns a week-level
    summary dict when an ITW was applied, else ``None``.
    """
    if not phase_calculator.is_intensive_weekend(
        week_number, phase, phases, trail_profile
    ):
        return None

    sat = next((w for w in workouts if w.get("day") == 6), None)
    if sat is None or sat.get("type") != "long":
        return None
    long_distance = sat.get("distance", 0) or 0
    if long_distance <= 0:
        return None

    elev = trail_profile.elevation_class

    # Saturday → trail-quality session.
    if elev in ("flat", "rolling"):
        quality_id = (
            "trail_ladder_intervals" if week_in_phase % 2 else "trail_pyramid_intervals"
        )
        quality_type = "interval"
    else:
        quality_id = "trail_elevation_repeats"
        quality_type = "hill"
    quality_budget = round(
        min(long_distance * _ITW_QUALITY_BUDGET_FRACTION, _ITW_QUALITY_BUDGET_CAP_KM),
        1,
    )
    new_sat = build_workout_for_type(
        quality_type, 6, quality_budget, total_km, phase, pace_zones
    )
    overlay_key_workout(
        new_sat,
        quality_type,
        phase,
        target_distance,
        week_in_phase,
        terrain,
        pace_zones,
        trail_profile=trail_profile,
        force_id=quality_id,
    )
    new_sat["intensive_weekend"] = True
    new_sat["itw_role"] = "quality"
    new_sat["coaching_rationale"] = (
        "Intensive weekend — day 1. A focused trail-quality session that "
        "pre-fatigues the legs for tomorrow's long run."
    )

    # Sunday → long run on fatigued legs.
    if trail_profile.bracket in ("ultra", "long_ultra") and elev != "flat":
        long_id = "trail_hike_run_long"
    else:
        long_id = "trail_b2b_day2"
    new_sun = build_workout_for_type(
        "long", 7, long_distance, total_km, phase, pace_zones
    )
    overlay_key_workout(
        new_sun,
        "long",
        phase,
        target_distance,
        week_in_phase,
        terrain,
        pace_zones,
        trail_profile=trail_profile,
        force_id=long_id,
    )
    new_sun["intensive_weekend"] = True
    new_sun["itw_role"] = "long2"
    new_sun["coaching_rationale"] = (
        "Intensive weekend — day 2. The big endurance day on legs already "
        "tired from yesterday — this back-to-back load is what drives the "
        "overcompensation."
    )

    workouts[workouts.index(sat)] = new_sat
    sun = next((w for w in workouts if w.get("day") == 7), None)
    if sun is not None:
        workouts[workouts.index(sun)] = new_sun
    else:
        workouts.append(new_sun)
        workouts.sort(key=lambda w: w.get("day", 0))

    # Soften the Thu/Fri lead-in so the weekend lands on fresher legs.
    for w in workouts:
        if (
            w.get("day") in (4, 5)
            and w.get("type") == "easy"
            and not w.get("key_workout_id")
        ):
            dist = w.get("distance", 0) or 0
            if dist > 0:
                _set_distance(w, round(dist * _ITW_LEADIN_TRIM_FACTOR, 1), pace_zones)
            w["coaching_rationale"] = (
                "Ease back today — you're loading for the intensive weekend ahead."
            )

    return {
        "applied": True,
        "quality_id": quality_id,
        "quality_name": new_sat.get("key_workout_name"),
        "long_id": long_id,
        "long_name": new_sun.get("key_workout_name"),
    }
