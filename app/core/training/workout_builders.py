"""Individual workout generators.

Creates workout dictionaries for each workout type (rest, recovery, easy,
long, tempo, interval, hill) with appropriate descriptions and pace zones.
"""

import random
from typing import Any, Dict, List, Optional

from app.core.training.strength_plan import (
    generate_strength_session as _build_strength_session,
    get_phase_focus_rotation,
)
from app.core.coaching.training_tips import get_tips_for_week


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
    """
    if workout_type != 'easy':
        return None

    # Taper: only one session (the first easy run), reduced volume
    if phase == 'taper' and session_index > 0:
        return None

    rotation = get_phase_focus_rotation(phase)
    focus = rotation[session_index % len(rotation)]

    return _build_strength_session(focus, phase, experience_level, week_number)


def generate_long_run(day: int, distance: float, total_km: float,
                      pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate long run workout."""
    if pace_zones:
        e_pace = pace_zones["E"]["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        long_run_notes = [
            f'Long run at {e_pace} (E-pace). Focus on endurance and mental toughness.',
            f'Long run: first {round(distance*0.8, 1)}km at {e_pace}, final {round(distance*0.2, 1)}km at {m_pace} (M-pace).',
            f'Long run at {e_pace} (E-pace). Practice nutrition every 45-60 minutes.',
        ]
    else:
        long_run_notes = [
            f'Long run at conversational pace. Focus on endurance and mental toughness.',
            f'Long run with race pace finish: first {round(distance*0.8, 1)}km easy, final {round(distance*0.2, 1)}km at goal pace.',
            f'Long run on varied terrain if possible. Practice nutrition strategy every 45-60 minutes.'
        ]

    return {
        'day': day,
        'type': 'long',
        'distance': round(distance, 1),
        'intensity': 'medium',
        'description': long_run_notes[day % len(long_run_notes)]
    }


def generate_easy_run(day: int, distance: float, total_km: float,
                      pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate easy run workout."""
    if pace_zones:
        e_pace = pace_zones["E"]["pace_str"]
        easy_variations = [
            f'Easy recovery run at {e_pace} (E-pace). Should feel conversational.',
            f'Easy run at {e_pace} with strides: 6x100m accelerations at the end.',
            f'Conversational pace at {e_pace}. Focus on relaxed form.',
        ]
    else:
        easy_variations = [
            f'Easy recovery run. Should be conversational pace.',
            f'Easy run with strides: main run easy, finish with 6x100m accelerations.',
            f'Conversational pace run. Focus on relaxed form and breathing.'
        ]

    return {
        'day': day,
        'type': 'easy',
        'distance': distance,
        'intensity': 'low',
        'description': easy_variations[day % len(easy_variations)]
    }


def generate_tempo_run(day: int, distance: float, total_km: float,
                       pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
    """Generate tempo run workout, with specific paces if VDOT is available."""
    if pace_zones:
        t_pace = pace_zones["T"]["pace_str"]
        m_pace = pace_zones["M"]["pace_str"]
        tempo_variations = [
            f'Tempo run: 2km warmup, {round(distance-2, 1)}km at {t_pace} (T-pace), 2km cooldown.',
            f'Cruise intervals: 3x{round((distance-2)/3, 1)}km at {t_pace} (T-pace) with 3min recovery.',
            f'Tempo run with surges: main tempo at {t_pace} (T-pace) with 4x30sec faster surges.',
        ]
    else:
        tempo_variations = [
            f'Tempo run: 2km warmup, {round(distance-2, 1)}km at threshold pace, 2km cooldown.',
            f'Cruise intervals: 3x{round((distance-2)/3, 1)}km at tempo pace with 3min recovery.',
            f'Tempo run with surges: Main tempo with 4x30sec faster surges.',
        ]

    from app.core.training.vdot_calculator import VDOTCalculator
    description = VDOTCalculator.inject_paces_into_description(
        tempo_variations[day % len(tempo_variations)], pace_zones or {}, "tempo"
    )

    return {
        'day': day,
        'type': 'tempo',
        'distance': round(distance, 1),
        'intensity': 'medium',
        'description': description,
    }


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

    # Guardrail: gate long intervals behind sufficient base
    if total_km >= 40:
        # Full suite including 1000m+ intervals
        if i_pace:
            interval_workouts = [
                f'VO\u2082max intervals: 6x400m at {i_pace} (I-pace) with 400m recovery jog.',
                f'Pyramid: 400m-800m-1200m-800m-400m at {i_pace} (I-pace) with equal recovery.',
                f'Hill repeats: 8x45sec at {t_pace} (T-pace) effort with jog-down recovery.',
                f'Yasso 800s: {max(4, round(distance / 0.8))}x800m at {m_pace} (M-pace).',
                f'VO\u2082max intervals: 5x1000m at {i_pace} (I-pace) with 400m recovery jog.',
            ]
        else:
            interval_workouts = [
                f'VO\u2082max intervals: 6x400m at 5K pace with 400m recovery jog.',
                f'Pyramid intervals: 400m-800m-1200m-800m-400m with equal recovery.',
                f'Hill repeats: 8x45sec at threshold effort with jog-down recovery.',
                f'Yasso 800s: {max(4, round(distance / 0.8))}x800m at marathon goal pace.',
                f'VO\u2082max intervals: 5x1000m at 5K pace with 400m recovery jog.',
            ]
    else:
        # Conservative: 400m-800m only; 200m repeats for low-base runners
        if i_pace:
            interval_workouts = [
                f'Speed intervals: 10x400m at {i_pace} (I-pace) with 400m recovery jog.',
                f'Cruise intervals: 6x800m at {t_pace} (T-pace) with 90sec rest.',
                f'Speed work: 12x200m at {r_pace} (R-pace) with 200m recovery jog.',
                f'Hill repeats: 8x30sec at hard effort with walk-down recovery.',
            ]
        else:
            interval_workouts = [
                f'Speed intervals: 10x400m at 5K pace with 400m recovery jog.',
                f'Cruise intervals: 6x800m at 10K pace with 90sec rest.',
                f'Speed work: 12x200m at fast-but-controlled effort with 200m jog.',
                f'Hill repeats: 8x30sec at hard effort with walk-down recovery.',
            ]

    from app.core.training.vdot_calculator import VDOTCalculator
    description = VDOTCalculator.inject_paces_into_description(
        interval_workouts[day % len(interval_workouts)], pace_zones or {}, "interval"
    )

    return {
        'day': day,
        'type': 'interval',
        'distance': round(distance, 1),
        'intensity': 'high',
        'description': description,
    }


def generate_hill_workout(day: int, distance: float = 0) -> Dict[str, Any]:
    """Generate hill workout."""
    hill_workouts = [
        f'Hill repeats: 10x30sec steep hill repeats with walk down recovery.',
        f'Long hill climbs: 5x2min moderate grade hills at threshold effort.',
        f'Hill bounding: 8x20sec explosive uphill bounds with full recovery.'
    ]

    return {
        'day': day,
        'type': 'hill',
        'distance': round(distance, 1) if distance > 0 else 0,
        'intensity': 'high',
        'description': hill_workouts[day % len(hill_workouts)]
    }


def generate_training_tips(week_number: int, target_distance: float) -> List[str]:
    """Generate diverse and week-specific training tips."""
    return get_tips_for_week(week_number, target_distance)
