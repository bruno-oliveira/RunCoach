"""Weekly plan builder.

Handles distance budgeting, scaling, fill-up, and ceiling enforcement
for a single week of training.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_validator import validate_week_plan
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_ratio_cap as _enforce_long_run_ratio_cap,
)
from app.contexts.plan.generators.workout_scaler import (
    fill_shortfall as _fill_shortfall,
)
from app.contexts.plan.generators.workout_scaler import (
    scale_down as _scale_down,
)
from app.contexts.plan.generators.workout_scaler import (
    set_distance as _set_distance,
)
from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training import long_run_calculator, phase_calculator, workout_builders
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training.key_workout_library import (
    overlay_key_workout,
)
from app.core.training.quality_caps import (
    MAX_EASY_VS_LONG_RUN,
    MAX_QUALITY_VS_LONG_RUN,
)
from app.core.training.quality_caps import (
    get_quality_caps as _get_quality_caps,
)
from app.core.training.training_constants import (
    calculate_week_in_phase,
)
from app.core.training.vertical_simulation import attach_treadmill_prescriptions
from app.core.training.workout_steps import _parse_pace_str_to_min_per_km

# Quality slots with capped distance below this floor are demoted to easy
# rather than scheduled as a thin-stimulus workout. Set just below the
# smallest budget that still leaves room for a meaningful main set after
# warm-up and cool-down.
_QUALITY_DEMOTE_THRESHOLD_KM = 1.5

# Workouts shorter than this get an "≈ X min" UX hint alongside the km value.
_DURATION_HINT_THRESHOLD_KM = 3.0

# Intensive Training Weekend (ITW) shaping: the Saturday trail-quality budget is
# a fraction of the displaced long run, capped; Thu/Fri easy days are trimmed so
# the weekend lands on fresher legs.
_ITW_QUALITY_BUDGET_FRACTION = 0.5
_ITW_QUALITY_BUDGET_CAP_KM = 12.0
_ITW_LEADIN_TRIM_FACTOR = 0.8

_PACE_ZONE_FOR_TYPE = {
    "easy": "E",
    "long": "E",
    "tempo": "T",
    "interval": "I",
    "hill": "I",
}
_DEFAULT_PACE_MIN_PER_KM = {
    "easy": 7.0,
    "long": 7.0,
    "tempo": 5.5,
    "interval": 4.8,
    "hill": 5.0,
}


def _vertical_simulation_targets(
    week_total_km: float,
    phase: str,
    is_recovery_week: bool,
    distribution: Dict[str, int],
    training_terrain: Optional[str],
    trail_profile,
) -> Optional[Dict[str, Any]]:
    """Build weekly mountain-load simulation targets for flat-only training.

    Race profile remains the source of mountain demands. When terrain access is
    flat, we surface executable proxies (uphill-effort minutes, eccentric load,
    and hike/run transitions) so athletes can prepare specifically.
    """
    if trail_profile is None or training_terrain != "flat":
        return None
    if trail_profile.elevation_class == "flat":
        return None

    phase_factor = {
        "base": 0.55,
        "build": 0.80,
        "peak": 1.00,
        "taper": 0.45,
    }.get(phase, 0.80)
    if is_recovery_week:
        phase_factor *= 0.75

    race_m_per_km = max(0.0, trail_profile.m_per_km)
    simulated_uphill_m = round(week_total_km * race_m_per_km * phase_factor)

    # Convert simulated vertical to uphill-effort minutes using a conservative
    # vertical ascent rate proxy for sustained trail climbing effort.
    vertical_rate_m_per_min = 12.0
    uphill_minutes = int(round(simulated_uphill_m / vertical_rate_m_per_min))
    downhill_minutes = int(round(uphill_minutes * 0.60))

    quality_sessions = sum(
        distribution.get(k, 0) for k in ("tempo", "interval", "hill")
    )
    transitions = max(2, quality_sessions * 2)
    if phase == "peak":
        transitions += 2

    return {
        "enabled": True,
        "race_elevation_class": trail_profile.elevation_class,
        "race_m_per_km": round(race_m_per_km, 1),
        "simulated_uphill_m": simulated_uphill_m,
        "uphill_effort_min": max(15, uphill_minutes),
        "downhill_eccentric_min": max(10, downhill_minutes),
        "hike_run_transition_reps": transitions,
        "guidance": (
            "Use incline treadmill, stairs, brisk power-hike blocks, and "
            "eccentric quad work to simulate mountain load on flat terrain."
        ),
    }


def demote_low_budget_quality(
    distribution: Dict[str, int], quality_distances: Dict[str, float]
) -> None:
    """Demote quality slots whose budget is below the stimulus floor to easy.

    A 1.5 km tempo is a poor experience: the segment math fits but the
    physiological dose is too thin to be worth a quality slot. Convert it
    to an easy run instead — the slot's allocated km flows back into the
    easy budget automatically when ``quality_distances`` shrinks.

    Mutates both inputs in place.
    """
    for qtype in ("tempo", "interval", "hill"):
        budget = quality_distances.get(qtype, 0)
        if 0 < budget < _QUALITY_DEMOTE_THRESHOLD_KM and distribution.get(qtype, 0) > 0:
            distribution[qtype] -= 1
            distribution["easy"] = distribution.get("easy", 0) + 1
            quality_distances.pop(qtype, None)


def attach_duration_hints(
    workouts: List[Dict[str, Any]], pace_zones: Optional[Dict] = None
) -> None:
    """Attach a duration_min UX hint to short workouts.

    Pure display annotation: does not modify ``distance`` or ``steps``.
    Only fires for workouts shorter than the hint threshold so cards
    aren't cluttered with redundant minute estimates.
    """
    for w in workouts:
        wtype = w.get("type")
        if wtype not in _PACE_ZONE_FOR_TYPE:
            continue
        dist = w.get("distance", 0) or 0
        if dist <= 0 or dist >= _DURATION_HINT_THRESHOLD_KM:
            continue
        pace_min_km = _pace_for_type(wtype, pace_zones)
        w["duration_min"] = max(1, int(round(dist * pace_min_km)))


def _pace_for_type(wtype: str, pace_zones: Optional[Dict]) -> float:
    """Pace (min/km) for a workout type, preferring VDOT zones when present."""
    if pace_zones:
        zone = _PACE_ZONE_FOR_TYPE.get(wtype)
        if zone and zone in pace_zones:
            parsed = _parse_pace_str_to_min_per_km(
                pace_zones[zone].get("pace_str"),
                zone,
            )
            if parsed:
                return parsed
    return _DEFAULT_PACE_MIN_PER_KM.get(wtype, 7.0)


def apply_quality_caps(
    quality_distances: Dict[str, float],
    long_run_distance: float,
    target_distance: float,
    phase: str,
) -> Dict[str, float]:
    """Cap each quality workout by the smaller of:
    MAX_QUALITY_VS_LONG_RUN * long_run or the distance-scaled
    physiological cap for that workout type.
    """
    ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
    phys_caps = _get_quality_caps(target_distance, phase)
    capped = dict(quality_distances)
    for key in capped:
        cap = min(ceiling, phys_caps.get(key, ceiling))
        if capped[key] > cap:
            capped[key] = round(cap, 1)
    return capped


def allocate_easy_distances(
    remaining_km: float, quality_total: float, long_run_distance: float, easy_runs: int
) -> List[float]:
    """Distribute the easy-run budget evenly across easy days."""
    if easy_runs <= 0:
        return []
    easy_budget = remaining_km - quality_total
    max_easy = long_run_distance * MAX_EASY_VS_LONG_RUN
    per_run = easy_budget / easy_runs
    return [round(min(per_run, max_easy), 1) for _ in range(easy_runs)]


def build_workout_for_type(
    workout_type: str,
    day_number: int,
    distance: float,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict],
) -> Dict[str, Any]:
    """Dispatch workout creation to the registered builder."""
    from app.core.training.workout_registry import build_workout

    return build_workout(
        workout_type,
        day=day_number,
        distance=distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
    )


def generate_daily_workouts(
    week_number: int,
    total_km: float,
    distribution: Dict[str, int],
    target_distance: float,
    weeks: int,
    phase: str,
    is_recovery_week: bool,
    vdot: Optional[float] = None,
    pace_zones: Optional[Dict] = None,
    experience_level: str = "beginner",
    week_in_phase: int = 0,
    terrain: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    trail_profile=None,
) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week."""
    long_run_distance = long_run_calculator.calculate_long_run_distance(
        total_km,
        target_distance,
        weeks,
        week_number,
        phase,
        is_recovery_week,
        experience_level,
        profile=profile,
        trail_profile=trail_profile,
        training_terrain=terrain,
    )
    quality_distances = long_run_calculator.calculate_quality_distances(
        total_km,
        phase,
        distribution,
        is_recovery_week,
        long_run_distance,
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )
    quality_distances = apply_quality_caps(
        quality_distances,
        long_run_distance,
        target_distance,
        phase,
    )

    demote_low_budget_quality(distribution, quality_distances)

    workout_types = workout_dist_mod.schedule_workout_types(
        distribution.copy(),
        phase,
        week_number,
        is_recovery_week,
    )

    remaining_km = total_km - long_run_distance
    quality_total = sum(quality_distances.values())
    easy_runs = sum(1 for wt in workout_types if wt == "easy")
    easy_distances = allocate_easy_distances(
        remaining_km,
        quality_total,
        long_run_distance,
        easy_runs,
    )

    easy_run_idx = 0
    strength_session_idx = 0
    workouts: List[Dict[str, Any]] = []

    for day in range(7):
        workout_type = workout_types[day]
        if workout_type is None:
            continue
        day_number = day + 1

        if workout_type == "easy":
            distance = (
                easy_distances[easy_run_idx]
                if easy_run_idx < len(easy_distances)
                else easy_distances[0]
            )
            easy_run_idx += 1
        elif workout_type == "long":
            distance = long_run_distance
        elif workout_type in ("tempo", "interval", "hill"):
            distance = quality_distances.get(workout_type, 0)
        else:
            distance = 0

        workout = build_workout_for_type(
            workout_type,
            day_number,
            distance,
            total_km,
            phase,
            pace_zones,
        )

        overlay_key_workout(
            workout,
            workout_type,
            phase,
            target_distance,
            week_in_phase,
            terrain,
            pace_zones,
            trail_profile=trail_profile,
        )

        if workout_type == "easy":
            strength_session = workout_builders.generate_strength_session(
                day_number,
                week_number,
                phase,
                workout_type,
                session_index=strength_session_idx,
                experience_level=experience_level,
                target_distance=target_distance,
                trail_profile=trail_profile,
            )
            if strength_session:
                workout["strength_session"] = strength_session
                strength_session_idx += 1

        workout["coaching_rationale"] = generate_coaching_note(
            workout_type,
            phase,
            week_number,
            target_distance,
            is_recovery_week,
        )
        workouts.append(workout)

    return workouts


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


def build_weekly_plan(
    week_number: int,
    total_km: float,
    target_distance: float,
    max_runs_per_week: int,
    weeks: int,
    vdot: Optional[float] = None,
    pace_zones: Optional[Dict] = None,
    experience_level: str = "beginner",
    terrain: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    trail_profile=None,
    intensive_weekend_enabled: bool = False,
) -> Dict[str, Any]:
    """Generate a single week's training plan.

    ``intensive_weekend_enabled`` opts the plan into a trail Intensive
    Training Weekend on the final peak week (off by default — it's a
    distinctive, demanding block the runner chooses to activate).
    """
    phases = phase_calculator.calculate_phases(
        weeks,
        target_distance,
        trail_profile=trail_profile,
    )
    phase = phase_calculator.get_phase(week_number, phases)
    is_recovery = phase_calculator.is_recovery_week(week_number, phase, phases)

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)

    distribution = workout_dist_mod.get_workout_distribution(
        total_km,
        max_runs_per_week,
        phase,
        is_recovery,
        week_number,
        phases,
        target_distance,
        terrain=terrain,
        profile=profile,
        trail_profile=trail_profile,
    )

    workouts = generate_daily_workouts(
        week_number,
        total_km,
        distribution,
        target_distance,
        weeks,
        phase,
        is_recovery,
        vdot=vdot,
        pace_zones=pace_zones,
        experience_level=experience_level,
        week_in_phase=week_in_phase,
        terrain=terrain,
        profile=profile,
        trail_profile=trail_profile,
    )

    intensive_weekend = None
    if intensive_weekend_enabled:
        intensive_weekend = apply_intensive_weekend(
            workouts,
            phase,
            week_number,
            phases,
            week_in_phase,
            total_km,
            target_distance,
            pace_zones,
            trail_profile,
            terrain,
        )

    actual_total_km = _scale_down(workouts, total_km, pace_zones=pace_zones)
    actual_total_km = _fill_shortfall(
        workouts,
        total_km,
        actual_total_km,
        target_distance,
        pace_zones=pace_zones,
        trail_profile=trail_profile,
    )
    actual_total_km = _enforce_long_run_ratio_cap(
        workouts,
        phase,
        training_terrain=terrain,
        trail_profile=trail_profile,
        pace_zones=pace_zones,
    )

    attach_duration_hints(workouts, pace_zones)

    is_valid, validation_message = validate_week_plan(
        workouts, actual_total_km, total_km, phase
    )

    training_tips = workout_builders.generate_training_tips(
        week_number,
        target_distance,
        trail_profile=trail_profile,
        training_terrain=terrain,
    )
    vertical_simulation = _vertical_simulation_targets(
        actual_total_km,
        phase,
        is_recovery,
        distribution,
        training_terrain=terrain,
        trail_profile=trail_profile,
    )
    attach_treadmill_prescriptions(
        workouts,
        vertical_simulation,
        trail_profile,
        terrain,
    )

    return {
        "week": week_number,
        "phase": phase,
        "is_recovery": is_recovery,
        "total_km": actual_total_km,
        "daily_workouts": workouts,
        "training_tips": training_tips,
        "vertical_simulation": vertical_simulation,
        "intensive_weekend": intensive_weekend,
        "validation": {"valid": is_valid, "message": validation_message},
        "strength_training": [
            w["strength_session"] for w in workouts if w.get("strength_session")
        ],
    }
