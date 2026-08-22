"""Individual workout generators.

Creates workout dictionaries for each workout type (rest, recovery, easy,
long, tempo, interval, hill, race) with appropriate descriptions and pace
zones.
"""

from typing import Any, Dict, List, Optional

from app.core.coaching.training_tips import get_tips_for_week
from app.core.training import workout_steps
from app.core.training.strength_plan import (
    generate_strength_session as _build_strength_session,
)
from app.core.training.strength_plan import (
    get_phase_focus_rotation,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_km


def generate_rest_day(day: int) -> Dict[str, Any]:
    """
    Generate regular rest day (NOT recovery day after long run).

    Note: Swimming/cross-training only on recovery days, not regular rest days.
    """
    rest_descriptions = [
        "Complete rest day for muscle repair and recovery",
        "Light stretching and mobility work (15-20 minutes)",
        "Active recovery with gentle walking (20-30 minutes)",
        "Rest day with foam rolling focus (15-20 minutes)",
    ]

    return {
        "day": day,
        "type": "rest",
        "distance": 0,
        "intensity": "rest",
        "description": rest_descriptions[day % len(rest_descriptions)],
    }


def generate_recovery_day(day: int, phase: str) -> Dict[str, Any]:
    """Generate active recovery day (swimming or walking)."""
    recovery_descriptions = [
        "Active recovery: 30-45min swimming OR easy walking",
        "Active recovery: Light swimming for cardio without impact",
        "Active recovery: Easy walking to promote blood flow",
    ]

    return {
        "day": day,
        "type": "recovery",
        "distance": 0,
        "intensity": "very_low",
        "description": recovery_descriptions[day % len(recovery_descriptions)],
    }


def generate_strength_session(
    day: int,
    week_number: int,
    phase: str,
    workout_type: str,
    session_index: int = 0,
    experience_level: str = "beginner",
    target_distance: float = 0.0,
    trail_profile=None,
) -> Optional[Dict[str, Any]]:
    """Generate a periodized strength session to attach to an easy run.

    Args:
        day: Day number (1-7)
        week_number: Week number in plan
        phase: Training phase (base, build, peak, taper)
        workout_type: Must be 'easy' -- other types return None
        session_index: 0-based counter of easy runs in this week,
                       used to cycle through the phase focus rotation
        experience_level: beginner / intermediate / advanced
        target_distance: Race distance in km (trail gets stability work)
    """
    if workout_type != "easy":
        return None

    # Taper: only one session (the first easy run), reduced volume
    if phase == "taper" and session_index > 0:
        return None

    rotation = get_phase_focus_rotation(
        phase, target_distance, trail_profile=trail_profile
    )
    focus = rotation[session_index % len(rotation)]

    return _build_strength_session(focus, phase, experience_level, week_number)


def attach_strength_sessions(
    workouts: List[Dict[str, Any]],
    week_number: int,
    phase: str,
    *,
    experience_level: str = "beginner",
    target_distance: float = 0.0,
    trail_profile=None,
    attach_types: tuple = ("easy",),
    max_sessions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Attach periodized strength sessions to a week's run days.

    Shared by every generator (road / performance / fitness / beginner) so
    they all get the same phase/experience/trail-aware strength engine
    instead of only the road plan attaching it (audit G8).

    Strength is hung on the runner's *easy* days by default — the engine
    treats them as the recovery slot — but ``attach_types`` lets generators
    with differently-named easy slots (e.g. beginner ``run_walk``) opt those
    in too. ``max_sessions`` caps how many strength sessions a week gets
    (beginners get one); taper weeks already self-limit to one.

    Mutates each chosen workout in place (sets ``strength_session``) and
    returns the list of attached sessions for the week-level
    ``strength_training`` summary.
    """
    attached: List[Dict[str, Any]] = []
    session_index = 0
    for workout in workouts:
        if max_sessions is not None and len(attached) >= max_sessions:
            break
        if workout.get("type") not in attach_types:
            continue
        session = generate_strength_session(
            workout.get("day", 0),
            week_number,
            phase,
            "easy",
            session_index=session_index,
            experience_level=experience_level,
            target_distance=target_distance,
            trail_profile=trail_profile,
        )
        if session:
            workout["strength_session"] = session
            attached.append(session)
            session_index += 1
    return attached


def generate_long_run(
    day: int, distance: float, total_km: float, pace_zones: Optional[Dict] = None
) -> Dict[str, Any]:
    """Generate long run workout."""
    if pace_zones:
        e_zone = pace_zones["E"]
        lr_sub = e_zone.get("sub_zones", {}).get("long_run")
        lr_pace = lr_sub["pace_str"] if lr_sub else e_zone["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        long_run_notes = [
            f"Long run at {lr_pace} (long run pace). Focus on endurance and mental toughness.",
            f"Long run: first {format_km(distance * 0.8)}km at {lr_pace}, final {format_km(distance * 0.2)}km at {m_pace} (M-pace).",
            f"Long run at {lr_pace} (long run pace). Practice nutrition every 45-60 minutes.",
        ]
    else:
        long_run_notes = [
            "Long run at conversational pace. Focus on endurance and mental toughness.",
            f"Long run with race pace finish: first {format_km(distance * 0.8)}km easy, final {format_km(distance * 0.2)}km at goal pace.",
            "Long run on varied terrain if possible. Practice nutrition strategy every 45-60 minutes.",
        ]

    variant = "mp_finish" if (day % 3 == 1) else "easy"
    return {
        "day": day,
        "type": "long",
        "distance": round(distance, 1),
        "intensity": "medium",
        "description": long_run_notes[day % len(long_run_notes)],
        "steps": workout_steps.build_long_steps(distance, pace_zones, variant=variant),
    }


def generate_easy_run(
    day: int, distance: float, total_km: float, pace_zones: Optional[Dict] = None
) -> Dict[str, Any]:
    """Generate easy run workout."""
    variant_idx = day % 3
    if pace_zones:
        e_zone = pace_zones["E"]
        easy_sub = e_zone.get("sub_zones", {}).get("easy")
        rec_sub = e_zone.get("sub_zones", {}).get("recovery")
        easy_pace = easy_sub["pace_str"] if easy_sub else e_zone["pace_str"]
        rec_pace = rec_sub["pace_str"] if rec_sub else e_zone["pace_str"]
        easy_variations = [
            f"Recovery run at {rec_pace} (recovery pace). Should feel very easy.",
            f"Easy run at {easy_pace} with strides: 6x100m accelerations at the end.",
            f"Conversational pace at {easy_pace} (easy pace). Focus on relaxed form.",
        ]
    else:
        easy_variations = [
            "Easy recovery run. Should be conversational pace.",
            "Easy run with strides: main run easy, finish with 6x100m accelerations.",
            "Conversational pace run. Focus on relaxed form and breathing.",
        ]

    # Strides add 6 × 100 m = 0.6 km of executable mileage. To keep the
    # workout's total distance equal to the planner's budget (so weekly
    # mileage stays at the planned figure and step total matches the
    # ``distance`` field exactly), we shorten the easy block on strides
    # days so easy + strides == budget.
    with_strides = variant_idx == 1
    strides_km = 0.6 if with_strides else 0.0
    main_km = (
        max(0.5, round(distance - strides_km, 1))
        if with_strides
        else round(distance, 1)
    )
    steps = workout_steps.build_easy_steps(
        main_km, pace_zones, with_strides=with_strides
    )
    actual_km = round(workout_steps.total_distance_m(steps) / 1000.0, 1)
    return {
        "day": day,
        "type": "easy",
        "distance": actual_km if actual_km > 0 else round(distance, 1),
        "intensity": "low",
        "description": easy_variations[variant_idx],
        "steps": steps,
    }


def generate_tempo_run(
    day: int, distance: float, total_km: float, pace_zones: Optional[Dict] = None
) -> Dict[str, Any]:
    """Generate tempo run workout, with specific paces if VDOT is available."""
    # Derive warm-up / main from the same _wucd_m the step builder uses so the
    # description's "{warmup}km warmup, {main_km}km" text matches the executable
    # steps exactly (both snap to whole 100 m). Computing warm-up independently
    # here (round(distance*0.25, 1)) drifted from the snapped step distance and
    # made the card claim a different main-set length than the steps prescribed.
    total_m = int(round(distance * 1000))
    wu_m = workout_steps._wucd_m(total_m, hard=False)
    warmup = wu_m / 1000.0
    cooldown = warmup
    main_km = round((total_m - 2 * wu_m) / 1000.0, 1)
    variant_idx = day % 3

    # Cruise intervals (variant 1): rep distance and jog recovery come from the
    # same tempo_cruise_plan the step builder uses, so the description cites
    # the exact distances the steps execute (including the strides-sharpener
    # fallback when the slot is too small for honest cruise reps).
    cruise = workout_steps.tempo_cruise_plan(distance)
    rec_m_cruise = cruise["rec_m"]
    rep_km_cruise = format_km(cruise["rep_m"] / 1000.0)

    if pace_zones:
        t_pace = pace_zones["T"]["pace_str"]
        tempo_variations = [
            f"Tempo run: {format_km(warmup)}km warmup, {format_km(main_km)}km at {t_pace} (T-pace), {format_km(cooldown)}km cooldown.",
            f"Cruise intervals: 3x{rep_km_cruise}km at {t_pace} (T-pace) with {rec_m_cruise}m jog recovery.",
            f"Tempo run with surges: {format_km(warmup)}km warmup, {format_km(main_km)}km at {t_pace} (T-pace) with 4x30sec faster surges, {format_km(cooldown)}km cooldown.",
        ]
    else:
        tempo_variations = [
            f"Tempo run: {format_km(warmup)}km warmup, {format_km(main_km)}km at threshold pace, {format_km(cooldown)}km cooldown.",
            f"Cruise intervals: 3x{rep_km_cruise}km at tempo pace with {rec_m_cruise}m jog recovery.",
            f"Tempo run with surges: {format_km(warmup)}km warmup, {format_km(main_km)}km at threshold effort with 4x30sec faster surges, {format_km(cooldown)}km cooldown.",
        ]

    if variant_idx == 1 and cruise["sharpener"]:
        # Mirrors build_tempo_steps: below the 800 m rep floor the cruise
        # variant becomes a strides sharpener (standard taper practice).
        tempo_variations[1] = (
            "Sharpener: run easy, then finish with 4x100m relaxed strides "
            "with full walk/jog recovery between each."
        )

    description = VDOTCalculator.inject_paces_into_description(
        tempo_variations[variant_idx], pace_zones or {}, "tempo"
    )

    steps = workout_steps.build_tempo_steps(distance, pace_zones, variant=variant_idx)
    # Cruise intervals (variant 1) add jog recoveries on top of the distance
    # budget, so reconcile the displayed total from the executable steps —
    # same policy as generate_interval_run: the card shows what the runner
    # actually covers.
    steps_km, fully_priced = workout_steps.compute_distance_from_steps_checked(steps)
    if fully_priced and steps_km > 0:
        actual_km = round(steps_km, 1)
    else:
        actual_km = round(max(distance, steps_km), 1)
    return {
        "day": day,
        "type": "tempo",
        "distance": actual_km if actual_km > 0 else round(distance, 1),
        "intensity": "medium",
        "description": description,
        "steps": steps,
    }


def generate_interval_run(
    day: int, distance: float, total_km: float, pace_zones: Optional[Dict] = None
) -> Dict[str, Any]:
    """Generate interval run workout.

    Guardrail: 1000m+ intervals are gated behind 40km/week base.
    200m repeats are offered for 5K-focused runners with <30km base.
    VDOT pace zones are injected when available.
    """
    if pace_zones:
        i_pace = pace_zones["I"]["pace_str"]
        t_pace = pace_zones["T"]["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        r_pace = pace_zones["R"]["pace_str"]
    else:
        i_pace = t_pace = m_pace = r_pace = None

    # Rep counts, jog recoveries, and the warm-up all come from the same
    # interval_session_plan the step builder uses, so the description and the
    # executable steps cite identical numbers (including the budget-filling
    # recovery distances).
    plan = workout_steps.interval_session_plan(distance, total_km)
    reps_400, rec_400 = plan["reps_400"], plan["rec_400"]
    reps_800 = plan["reps_800"]
    reps_1000, rec_1000 = plan["reps_1000"], plan["rec_1000"]
    reps_200, rec_200 = plan["reps_200"], plan["rec_200"]

    # 50 km/week threshold ensures ~5 weeks of base before 1000 m repeats are
    # prescribed. The previous 40 km gate was reachable too early (week 8 from a
    # 24 km base) without adequate cumulative readiness.
    if total_km >= 50:
        if i_pace:
            interval_workouts = [
                f"VO\u2082max intervals: {reps_400}x400m at {i_pace} (I-pace) with {rec_400}m recovery jog.",
                f"Pyramid: 400m-800m-1200m-800m-400m at {i_pace} (I-pace) with equal recovery.",
                f"Hill repeats: 8x45sec at {t_pace} (T-pace) effort with jog-down recovery.",
                f"Yasso 800s: {reps_800}x800m at {m_pace} (M-pace).",
                f"VO\u2082max intervals: {reps_1000}x1000m at {i_pace} (I-pace) with {rec_1000}m recovery jog.",
            ]
        else:
            interval_workouts = [
                f"VO\u2082max intervals: {reps_400}x400m at 5K pace with {rec_400}m recovery jog.",
                "Pyramid intervals: 400m-800m-1200m-800m-400m with equal recovery.",
                "Hill repeats: 8x45sec at threshold effort with jog-down recovery.",
                f"Yasso 800s: {reps_800}x800m at marathon goal pace.",
                f"VO\u2082max intervals: {reps_1000}x1000m at 5K pace with {rec_1000}m recovery jog.",
            ]
    else:
        if i_pace:
            interval_workouts = [
                f"Speed intervals: {reps_400}x400m at {i_pace} (I-pace) with {rec_400}m recovery jog.",
                f"Cruise intervals: {reps_800}x800m at {t_pace} (T-pace) with 90sec rest.",
                f"Speed work: {reps_200}x200m at {r_pace} (R-pace) with {rec_200}m recovery jog.",
                "Hill repeats: 8x30sec at hard effort with walk-down recovery.",
            ]
        else:
            interval_workouts = [
                f"Speed intervals: {reps_400}x400m at 5K pace with {rec_400}m recovery jog.",
                f"Cruise intervals: {reps_800}x800m at 10K pace with 90sec rest.",
                f"Speed work: {reps_200}x200m at fast-but-controlled effort with {rec_200}m jog.",
                "Hill repeats: 8x30sec at hard effort with walk-down recovery.",
            ]

    variant_idx = day % len(interval_workouts)
    description = VDOTCalculator.inject_paces_into_description(
        interval_workouts[variant_idx], pace_zones or {}, "interval"
    )

    steps = workout_steps.build_interval_steps(
        distance,
        total_km,
        pace_zones,
        variant=variant_idx,
    )
    steps_km, fully_priced = workout_steps.compute_distance_from_steps_checked(steps)
    if fully_priced:
        actual_km = round(steps_km, 1)
    else:
        # Unpriced duration reps make the steps total a lower bound - keep
        # at least the budgeted distance rather than collapsing the session.
        actual_km = round(max(distance, steps_km), 1)
    return {
        "day": day,
        "type": "interval",
        "distance": actual_km if actual_km > 0 else round(distance, 1),
        "intensity": "high",
        "description": description,
        "steps": steps,
    }


def generate_hill_workout(day: int, distance: float = 0) -> Dict[str, Any]:
    """Generate hill workout.

    The hill structure (10 × 30 s reps with walk-down recovery) is a fixed
    dose: it doesn't stretch to fill an arbitrary km budget. We report
    ``distance`` as what the steps actually deliver so weekly mileage and
    the workout card stay in lockstep.
    """
    hill_workouts = [
        "Hill repeats: 10x30sec steep hill repeats with walk down recovery.",
        "Long hill climbs: 5x2min moderate grade hills at threshold effort.",
        "Hill bounding: 8x20sec explosive uphill bounds with full recovery.",
    ]
    steps = workout_steps.build_hill_steps(distance, None)
    steps_km, fully_priced = workout_steps.compute_distance_from_steps_checked(steps)
    if fully_priced:
        actual_km = round(steps_km, 1)
    else:
        actual_km = round(max(distance, steps_km), 1)
    return {
        "day": day,
        "type": "hill",
        "distance": actual_km
        if actual_km > 0
        else (round(distance, 1) if distance > 0 else 0),
        "intensity": "high",
        "description": hill_workouts[day % len(hill_workouts)],
        "steps": steps,
    }


# Race-distance labels used in the race-day card title. Anything else is
# named by its distance ("28 km Race"), so a non-standard target still reads
# as a race rather than falling back to a generic label.
_RACE_LABELS = {5.0: "5K", 10.0: "10K", 21.1: "Half Marathon", 42.2: "Marathon"}


def race_day_name(target_distance: float, is_trail: bool = False) -> str:
    """Human-readable name for the goal race."""
    for km, label in _RACE_LABELS.items():
        if abs(target_distance - km) < 0.5:
            return f"{label} Race Day"
    suffix = "Trail Race Day" if is_trail else "Race Day"
    return f"{format_km(target_distance)} km {suffix}"


def generate_race_day(
    day: int,
    target_distance: float,
    pace_zones: Optional[Dict] = None,
    is_trail: bool = False,
) -> Dict[str, Any]:
    """Generate the goal race as a workout on the plan's final day.

    Every plan is built backwards from a race, but until now the plan stopped
    at the last taper long run and the runner was left to infer the finish.
    The race is the one session whose distance is fixed by the event rather
    than derived from a budget, so it is installed after all scaling passes
    and never rescaled (``is_prescriptive`` covers it via its type).
    """
    steps = workout_steps.build_race_steps(
        target_distance,
        pace_zones,
        target_distance_km=target_distance,
        is_trail=is_trail,
    )
    zone = workout_steps.race_pace_zone_key(target_distance, pace_zones)
    pace_str = (pace_zones or {}).get(zone, {}).get("pace_str")

    if is_trail:
        description = (
            f"Race day — {format_km(target_distance)} km. Start easier than "
            "feels right, hike the steep climbs from the gun, and eat and "
            "drink on a schedule rather than on demand. Your race is decided "
            "in the last quarter, not the first."
        )
    else:
        goal = f" Goal pace {pace_str}." if pace_str else ""
        description = (
            f"Race day — {format_km(target_distance)} km.{goal} Warm up "
            f"{'15-20 min easy with a few strides' if target_distance <= 10.0 else '10 min easy'} "
            "beforehand, then run the first third controlled, hold goal pace "
            "through the middle, and empty the tank over the last third."
        )

    return {
        "day": day,
        "type": "race",
        "distance": round(target_distance, 1),
        "intensity": "high",
        "is_race": True,
        # Every display surface (plan cards, day detail, the PDF sheet, the
        # Intervals.icu workout name) already reads ``key_workout_name`` as
        # "the name of this session", falling back to the raw type otherwise.
        # Without it the biggest day of the plan would render as "Race".
        # No ``key_workout_id`` is set, so nothing treats it as a library
        # session — only the label is borrowed.
        "key_workout_name": race_day_name(target_distance, is_trail),
        "description": description,
        "steps": steps,
    }


def generate_training_tips(
    week_number: int,
    target_distance: float,
    trail_profile=None,
    training_terrain: Optional[str] = None,
) -> List[str]:
    """Generate diverse and week-specific training tips."""
    return get_tips_for_week(
        week_number,
        target_distance,
        trail_profile=trail_profile,
        training_terrain=training_terrain,
    )
