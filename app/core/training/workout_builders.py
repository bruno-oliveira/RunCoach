"""Individual workout generators.

Creates workout dictionaries for each workout type (rest, recovery, easy,
long, tempo, interval, hill) with appropriate descriptions and pace zones.
"""

import random
from typing import Any, Dict, List, Optional

from app.core.training import workout_steps
from app.core.training.strength_plan import (
    generate_strength_session as _build_strength_session,
    get_phase_focus_rotation,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.coaching.training_tips import get_tips_for_week


_TIME_THRESHOLD = {'easy': 3.0, 'long': 3.0, 'tempo': 2.0, 'interval': 2.0, 'hill': 2.0}
_MIN_DURATION = {'easy': 20, 'long': 25, 'tempo': 25, 'interval': 25, 'hill': 25}


def _apply_time_based(workout: Dict[str, Any],
                      pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Add duration_min and rewrite description+steps when distance is too short to be meaningful."""
    wtype = workout.get('type', '')
    dist = workout.get('distance', 0)
    threshold = _TIME_THRESHOLD.get(wtype)
    if threshold is None or dist >= threshold:
        return workout
    dur = _MIN_DURATION[wtype]
    workout['duration_min'] = dur
    descs = {
        'easy': f'Easy run for {dur} minutes at conversational pace.',
        'long': f'Long run for {dur} minutes at easy pace. Focus on time on feet.',
        'tempo': f'Tempo session for {dur} minutes: 5min warmup, {dur - 10}min at comfortably hard effort, 5min cooldown.',
        'interval': f'Interval session for {dur} minutes: warmup, 6x1min hard / 1min easy, cooldown.',
        'hill': f'Hill session for {dur} minutes: warmup, 6x30sec uphill hard with jog-down recovery, cooldown.',
    }
    if wtype in descs:
        workout['description'] = descs[wtype]
    workout['steps'] = _time_based_steps(wtype, dur, pace_zones)
    workout['distance'] = round(workout_steps._compute_distance_from_steps(workout['steps']), 1)
    return workout


def _time_based_steps(wtype: str, dur: int,
                      pace_zones: Optional[Dict] = None) -> List[Dict[str, Any]]:
    _ps = workout_steps._pace_str
    wu = workout_steps._step("warmup", "5 min warm-up", duration_s=300, pace_zone="E", pace_str=_ps("E", pace_zones), effort="easy")
    cd = workout_steps._step("cooldown", "5 min cool-down", duration_s=300, pace_zone="E", pace_str=_ps("E", pace_zones), effort="easy")
    if wtype == 'tempo':
        main_s = (dur - 10) * 60
        return [wu, workout_steps._step("run", f"{dur - 10} min tempo", duration_s=main_s, pace_zone="T", pace_str=_ps("T", pace_zones), effort="comfortably hard"), cd]
    if wtype == 'interval':
        return [
            wu,
            workout_steps._step("run", "6 × 1 min hard", duration_s=60, repeat=6, pace_zone="I", pace_str=_ps("I", pace_zones), effort="hard"),
            workout_steps._step("recovery", "1 min easy jog", duration_s=60, repeat=6, pace_zone="E", pace_str=_ps("E", pace_zones), effort="jog"),
            cd,
        ]
    if wtype == 'hill':
        return [
            wu,
            workout_steps._step("run", "6 × 30 s uphill", duration_s=30, repeat=6, pace_zone="I", pace_str=_ps("I", pace_zones), effort="hard uphill"),
            workout_steps._step("recovery", "Jog-down recovery", duration_s=60, repeat=6, pace_zone="E", pace_str=_ps("E", pace_zones), effort="jog"),
            cd,
        ]
    if wtype == 'easy':
        return [workout_steps._step("run", f"{dur} min easy", duration_s=dur * 60, pace_zone="E", pace_str=_ps("E", pace_zones), effort="conversational")]
    if wtype == 'long':
        return [workout_steps._step("run", f"{dur} min easy", duration_s=dur * 60, pace_zone="E", pace_str=_ps("E", pace_zones), effort="conversational", note="Focus on time on feet")]
    return []


def generate_rest_day(day: int) -> Dict[str, Any]:
    """
    Generate regular rest day (NOT recovery day after long run).

    Note: Swimming/cross-training only on recovery days, not regular rest days.
    """
    rest_descriptions = [
        'Complete rest day for muscle repair and recovery',
        'Light stretching and mobility work (15-20 minutes)',
        'Active recovery with gentle walking (20-30 minutes)',
        'Rest day with foam rolling focus (15-20 minutes)'
    ]

    return {
        'day': day,
        'type': 'rest',
        'distance': 0,
        'intensity': 'rest',
        'description': rest_descriptions[day % len(rest_descriptions)]
    }


def generate_recovery_day(day: int, phase: str) -> Dict[str, Any]:
    """Generate active recovery day (swimming or walking)."""
    recovery_descriptions = [
        'Active recovery: 30-45min swimming OR easy walking',
        'Active recovery: Light swimming for cardio without impact',
        'Active recovery: Easy walking to promote blood flow'
    ]

    return {
        'day': day,
        'type': 'recovery',
        'distance': 0,
        'intensity': 'very_low',
        'description': recovery_descriptions[day % len(recovery_descriptions)]
    }


def generate_strength_session(
    day: int,
    week_number: int,
    phase: str,
    workout_type: str,
    session_index: int = 0,
    experience_level: str = "beginner",
    target_distance: float = 0.0,
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
    if workout_type != 'easy':
        return None

    # Taper: only one session (the first easy run), reduced volume
    if phase == 'taper' and session_index > 0:
        return None

    rotation = get_phase_focus_rotation(phase, target_distance)
    focus = rotation[session_index % len(rotation)]

    return _build_strength_session(focus, phase, experience_level, week_number)


def generate_long_run(day: int, distance: float, total_km: float,
                      pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate long run workout."""
    if pace_zones:
        e_zone = pace_zones["E"]
        lr_sub = e_zone.get("sub_zones", {}).get("long_run")
        lr_pace = lr_sub["pace_str"] if lr_sub else e_zone["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        long_run_notes = [
            f'Long run at {lr_pace} (long run pace). Focus on endurance and mental toughness.',
            f'Long run: first {round(distance*0.8, 1)}km at {lr_pace}, final {round(distance*0.2, 1)}km at {m_pace} (M-pace).',
            f'Long run at {lr_pace} (long run pace). Practice nutrition every 45-60 minutes.',
        ]
    else:
        long_run_notes = [
            f'Long run at conversational pace. Focus on endurance and mental toughness.',
            f'Long run with race pace finish: first {round(distance*0.8, 1)}km easy, final {round(distance*0.2, 1)}km at goal pace.',
            f'Long run on varied terrain if possible. Practice nutrition strategy every 45-60 minutes.'
        ]

    variant = 'mp_finish' if (day % 3 == 1) else 'easy'
    return _apply_time_based({
        'day': day,
        'type': 'long',
        'distance': round(distance, 1),
        'intensity': 'medium',
        'description': long_run_notes[day % len(long_run_notes)],
        'steps': workout_steps.build_long_steps(distance, pace_zones, variant=variant),
    }, pace_zones)


def generate_easy_run(day: int, distance: float, total_km: float,
                      pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate easy run workout."""
    variant_idx = day % 3
    if pace_zones:
        e_zone = pace_zones["E"]
        easy_sub = e_zone.get("sub_zones", {}).get("easy")
        rec_sub = e_zone.get("sub_zones", {}).get("recovery")
        easy_pace = easy_sub["pace_str"] if easy_sub else e_zone["pace_str"]
        rec_pace = rec_sub["pace_str"] if rec_sub else e_zone["pace_str"]
        easy_variations = [
            f'Recovery run at {rec_pace} (recovery pace). Should feel very easy.',
            f'Easy run at {easy_pace} with strides: 6x100m accelerations at the end.',
            f'Conversational pace at {easy_pace} (easy pace). Focus on relaxed form.',
        ]
    else:
        easy_variations = [
            f'Easy recovery run. Should be conversational pace.',
            f'Easy run with strides: main run easy, finish with 6x100m accelerations.',
            f'Conversational pace run. Focus on relaxed form and breathing.'
        ]

    return _apply_time_based({
        'day': day,
        'type': 'easy',
        'distance': distance,
        'intensity': 'low',
        'description': easy_variations[variant_idx],
        'steps': workout_steps.build_easy_steps(
            distance, pace_zones, with_strides=(variant_idx == 1)
        ),
    }, pace_zones)


def generate_tempo_run(day: int, distance: float, total_km: float,
                       pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate tempo run workout, with specific paces if VDOT is available."""
    warmup = min(2.0, max(0.5, round(distance * 0.25, 1)))
    cooldown = warmup
    main_km = round(distance - warmup - cooldown, 1)
    variant_idx = day % 3

    if pace_zones:
        t_pace = pace_zones["T"]["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        tempo_variations = [
            f'Tempo run: {warmup:g}km warmup, {main_km:g}km at {t_pace} (T-pace), {cooldown:g}km cooldown.',
            f'Cruise intervals: 3x{round(main_km/3, 1):g}km at {t_pace} (T-pace) with 3min recovery.',
            f'Tempo run with surges: {warmup:g}km warmup, {main_km:g}km at {t_pace} (T-pace) with 4x30sec faster surges, {cooldown:g}km cooldown.',
        ]
    else:
        tempo_variations = [
            f'Tempo run: {warmup:g}km warmup, {main_km:g}km at threshold pace, {cooldown:g}km cooldown.',
            f'Cruise intervals: 3x{round(main_km/3, 1):g}km at tempo pace with 3min recovery.',
            f'Tempo run with surges: {warmup:g}km warmup, {main_km:g}km at threshold effort with 4x30sec faster surges, {cooldown:g}km cooldown.',
        ]

    description = VDOTCalculator.inject_paces_into_description(
        tempo_variations[variant_idx], pace_zones or {}, "tempo"
    )

    return _apply_time_based({
        'day': day,
        'type': 'tempo',
        'distance': round(distance, 1),
        'intensity': 'medium',
        'description': description,
        'steps': workout_steps.build_tempo_steps(distance, pace_zones, variant=variant_idx),
    }, pace_zones)


def generate_interval_run(day: int, distance: float, total_km: float,
                          pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
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

    warmup = min(2.0, max(0.5, round(distance * 0.25, 1)))
    cooldown = warmup
    work_km = max(0.5, distance - warmup - cooldown)

    # 50 km/week threshold ensures ~5 weeks of base before 1000 m repeats are
    # prescribed. The previous 40 km gate was reachable too early (week 8 from a
    # 24 km base) without adequate cumulative readiness.
    if total_km >= 50:
        reps_400 = max(4, round(work_km / 0.8))
        reps_800 = max(4, round(work_km / 1.6))
        reps_1000 = max(3, round(work_km / 2.0))
        reps_200 = 0
        if i_pace:
            interval_workouts = [
                f'VO\u2082max intervals: {reps_400}x400m at {i_pace} (I-pace) with 400m recovery jog.',
                f'Pyramid: 400m-800m-1200m-800m-400m at {i_pace} (I-pace) with equal recovery.',
                f'Hill repeats: 8x45sec at {t_pace} (T-pace) effort with jog-down recovery.',
                f'Yasso 800s: {reps_800}x800m at {m_pace} (M-pace).',
                f'VO\u2082max intervals: {reps_1000}x1000m at {i_pace} (I-pace) with 400m recovery jog.',
            ]
        else:
            interval_workouts = [
                f'VO\u2082max intervals: {reps_400}x400m at 5K pace with 400m recovery jog.',
                f'Pyramid intervals: 400m-800m-1200m-800m-400m with equal recovery.',
                f'Hill repeats: 8x45sec at threshold effort with jog-down recovery.',
                f'Yasso 800s: {reps_800}x800m at marathon goal pace.',
                f'VO\u2082max intervals: {reps_1000}x1000m at 5K pace with 400m recovery jog.',
            ]
    else:
        reps_400 = max(4, round(work_km / 0.8))
        reps_800 = max(3, round(work_km / 1.6))
        reps_200 = max(6, round(work_km / 0.4))
        reps_1000 = 0
        if i_pace:
            interval_workouts = [
                f'Speed intervals: {reps_400}x400m at {i_pace} (I-pace) with 400m recovery jog.',
                f'Cruise intervals: {reps_800}x800m at {t_pace} (T-pace) with 90sec rest.',
                f'Speed work: {reps_200}x200m at {r_pace} (R-pace) with 200m recovery jog.',
                f'Hill repeats: 8x30sec at hard effort with walk-down recovery.',
            ]
        else:
            interval_workouts = [
                f'Speed intervals: {reps_400}x400m at 5K pace with 400m recovery jog.',
                f'Cruise intervals: {reps_800}x800m at 10K pace with 90sec rest.',
                f'Speed work: {reps_200}x200m at fast-but-controlled effort with 200m jog.',
                f'Hill repeats: 8x30sec at hard effort with walk-down recovery.',
            ]

    variant_idx = day % len(interval_workouts)
    description = VDOTCalculator.inject_paces_into_description(
        interval_workouts[variant_idx], pace_zones or {}, "interval"
    )

    return _apply_time_based({
        'day': day,
        'type': 'interval',
        'distance': round(distance, 1),
        'intensity': 'high',
        'description': description,
        'steps': workout_steps.build_interval_steps(
            distance, total_km, pace_zones, variant=variant_idx,
            reps_400=reps_400, reps_800=reps_800,
            reps_1000=reps_1000, reps_200=reps_200,
        ),
    }, pace_zones)


def generate_hill_workout(day: int, distance: float = 0) -> Dict[str, Any]:
    """Generate hill workout."""
    hill_workouts = [
        f'Hill repeats: 10x30sec steep hill repeats with walk down recovery.',
        f'Long hill climbs: 5x2min moderate grade hills at threshold effort.',
        f'Hill bounding: 8x20sec explosive uphill bounds with full recovery.'
    ]

    return _apply_time_based({
        'day': day,
        'type': 'hill',
        'distance': round(distance, 1) if distance > 0 else 0,
        'intensity': 'high',
        'description': hill_workouts[day % len(hill_workouts)],
        'steps': workout_steps.build_hill_steps(distance, None),
    })


def generate_training_tips(week_number: int, target_distance: float) -> List[str]:
    """Generate diverse and week-specific training tips."""
    return get_tips_for_week(week_number, target_distance)
