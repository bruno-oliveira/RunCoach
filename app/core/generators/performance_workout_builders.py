"""Workout builders for performance plans — tempo, VO2max, race pace, fartlek, long, easy."""

from typing import Any, Dict

from app.utils import format_pace as _shared_format_pace


def estimate_duration_min(segments: list) -> int:
    """Estimate total workout duration from segments."""
    total = 0
    for seg in segments:
        total += seg['distance_km'] * seg.get('pace_raw', 6.0)
    return round(total)


def _warmup_segment(warmup_km: float, pace: float) -> dict:
    return {
        'name': 'Warm-up',
        'distance_km': warmup_km,
        'pace_formatted': _shared_format_pace(pace),
        'pace_raw': pace,
        'zone': 'zone_1',
        'zone_label': 'Zone 1',
        'type': 'warmup',
    }


def _cooldown_segment(cooldown_km: float, pace: float) -> dict:
    return {
        'name': 'Cool-down',
        'distance_km': cooldown_km,
        'pace_formatted': _shared_format_pace(pace),
        'pace_raw': pace,
        'zone': 'zone_1',
        'zone_label': 'Zone 1',
        'type': 'cooldown',
    }


def generate_tempo_workout(zones: Dict, weekly_km: float, week: int, phase: str) -> Dict:
    """Generate a tempo workout scaled to weekly volume."""
    target_pace = zones['zone_3_tempo']['pace']

    if phase == 'base':
        tempo_km = min(6, weekly_km * 0.20)
    elif phase == 'build':
        tempo_km = min(10, weekly_km * 0.25)
    elif phase == 'peak':
        tempo_km = min(12, weekly_km * 0.30)
    else:
        tempo_km = min(5, weekly_km * 0.15)

    warmup_km = 2
    cooldown_km = 2
    total_km = warmup_km + tempo_km + cooldown_km
    warmup_pace = zones['zone_1_recovery']['pace']

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            'name': 'Tempo',
            'distance_km': round(tempo_km, 1),
            'pace_formatted': _shared_format_pace(target_pace),
            'pace_raw': target_pace,
            'zone': 'zone_3',
            'zone_label': 'Zone 3',
            'type': 'main',
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    return {
        'type': 'tempo',
        'intensity': 'medium',
        'zone': 'zone_3',
        'target_pace': target_pace,
        'target_pace_formatted': _shared_format_pace(target_pace),
        'description': f"{total_km:.0f}km tempo: {warmup_km}km warmup, {tempo_km:.0f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
        'distance': total_km,
        'quality': True,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }


def generate_vo2max_workout(zones: Dict, weekly_km: float, week: int, phase: str) -> Dict:
    """Generate a VO2 max interval workout scaled to weekly volume."""
    target_pace = zones['zone_4_vo2max']['pace']

    pct_map = {'base': 0.15, 'build': 0.20, 'peak': 0.18, 'taper': 0.12}
    target_interval_km = weekly_km * pct_map.get(phase, 0.15)

    if target_interval_km <= 3:
        interval_m = 400
    elif target_interval_km <= 5:
        interval_m = 600
    elif target_interval_km <= 8:
        interval_m = 800
    else:
        interval_m = 1000

    interval_km = interval_m / 1000
    reps = max(3, min(8, round(target_interval_km / interval_km)))

    recovery_time = int(interval_km * 2)
    total_interval_km = interval_km * reps
    warmup_km = 2
    cooldown_km = 2
    total_km = warmup_km + total_interval_km + cooldown_km
    warmup_pace = zones['zone_1_recovery']['pace']

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            'name': 'Intervals',
            'distance_km': round(total_interval_km, 1),
            'pace_formatted': _shared_format_pace(target_pace),
            'pace_raw': target_pace,
            'zone': 'zone_4',
            'zone_label': 'Zone 4',
            'type': 'main',
            'intervals': {
                'reps': reps,
                'interval_m': interval_m,
                'recovery_min': recovery_time,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    return {
        'type': 'vo2max',
        'intensity': 'high',
        'zone': 'zone_4',
        'target_pace': target_pace,
        'target_pace_formatted': _shared_format_pace(target_pace),
        'description': f"{total_km:.0f}km intervals: {warmup_km}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_time}min recovery), {cooldown_km}km cooldown",
        'distance': total_km,
        'quality': True,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }


def generate_race_pace_workout(zones: Dict, weekly_km: float, week: int, phase: str) -> Dict:
    """Generate a race pace workout scaled to weekly volume."""
    target_pace = zones['zone_5_race']['pace']

    if phase == 'base':
        race_km = min(4, weekly_km * 0.15)
    elif phase == 'build':
        race_km = min(8, weekly_km * 0.20)
    elif phase == 'peak':
        race_km = min(12, weekly_km * 0.25)
    else:
        race_km = min(3, weekly_km * 0.10)

    warmup_km = 2
    cooldown_km = 2
    total_km = warmup_km + race_km + cooldown_km
    warmup_pace = zones['zone_1_recovery']['pace']

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            'name': 'Race Pace',
            'distance_km': round(race_km, 1),
            'pace_formatted': _shared_format_pace(target_pace),
            'pace_raw': target_pace,
            'zone': 'zone_5',
            'zone_label': 'Zone 5',
            'type': 'main',
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    return {
        'type': 'race_pace',
        'intensity': 'high',
        'zone': 'zone_5',
        'target_pace': target_pace,
        'target_pace_formatted': _shared_format_pace(target_pace),
        'description': f"{total_km:.0f}km race pace: {warmup_km}km warmup, {race_km:.0f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
        'distance': total_km,
        'quality': True,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }


def generate_fartlek_workout(zones: Dict, weekly_km: float, week: int, phase: str) -> Dict:
    """Generate a fartlek (speed play) workout scaled to weekly volume."""
    tempo_pace = zones['zone_3_tempo']['pace']
    hard_pace = zones['zone_4_vo2max']['pace']

    pct_map = {'base': 0.20, 'build': 0.25, 'peak': 0.28, 'taper': 0.15}
    total_km = round(weekly_km * pct_map.get(phase, 0.20), 1)
    total_km = max(5, min(14, total_km))

    surges_per_km = 1.5
    surges = max(4, min(10, round((total_km - 4) * surges_per_km)))

    warmup_km = 2
    cooldown_km = 2
    main_km = max(1, total_km - warmup_km - cooldown_km)
    warmup_pace = zones['zone_1_recovery']['pace']
    fartlek_avg_pace = (tempo_pace + hard_pace) / 2

    segments = [
        _warmup_segment(warmup_km, warmup_pace),
        {
            'name': 'Fartlek',
            'distance_km': round(main_km, 1),
            'pace_formatted': f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
            'pace_raw': fartlek_avg_pace,
            'zone': 'mixed',
            'zone_label': 'Mixed Zones',
            'type': 'main',
            'intervals': {
                'reps': surges,
                'interval_m': '1-3min surges',
                'recovery_min': None,
            },
        },
        _cooldown_segment(cooldown_km, warmup_pace),
    ]

    return {
        'type': 'fartlek',
        'intensity': 'medium',
        'zone': 'mixed',
        'target_pace': tempo_pace,
        'target_pace_formatted': f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
        'description': f"{total_km}km fartlek: {surges} surges of 1-3min at {_shared_format_pace(hard_pace)}, easy running between",
        'distance': total_km,
        'quality': True,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }


def generate_long_run(zones: Dict, weekly_km: float, week: int, phase: str, distance_km: float) -> Dict:
    """Generate a long run with optional race pace finish."""
    easy_pace = zones['zone_1_recovery']['pace']
    race_pace = zones['zone_5_race']['pace']

    long_run_km = weekly_km * 0.30

    if distance_km <= 10:
        long_run_km = min(long_run_km, 15)
    elif distance_km <= 21.1:
        long_run_km = min(long_run_km, 22)
    else:
        long_run_km = min(long_run_km, 32)

    if phase in ['build', 'peak'] and long_run_km >= 12:
        race_pace_km = min(4, distance_km * 0.3)
        easy_km = long_run_km - race_pace_km
        description = f"{long_run_km:.0f}km long run: {easy_km:.0f}km easy at {_shared_format_pace(easy_pace)}, last {race_pace_km:.0f}km at {_shared_format_pace(race_pace)}"
        segments = [
            {
                'name': 'Easy',
                'distance_km': round(easy_km, 1),
                'pace_formatted': _shared_format_pace(easy_pace),
                'pace_raw': easy_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'main',
            },
            {
                'name': 'Race Pace Finish',
                'distance_km': round(race_pace_km, 1),
                'pace_formatted': _shared_format_pace(race_pace),
                'pace_raw': race_pace,
                'zone': 'zone_5',
                'zone_label': 'Zone 5',
                'type': 'main',
            },
        ]
    else:
        description = f"{long_run_km:.0f}km long run at {_shared_format_pace(easy_pace)}"
        segments = [
            {
                'name': 'Easy Long Run',
                'distance_km': round(long_run_km, 1),
                'pace_formatted': _shared_format_pace(easy_pace),
                'pace_raw': easy_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'main',
            },
        ]

    return {
        'type': 'long',
        'intensity': 'medium',
        'zone': 'zone_1',
        'target_pace': easy_pace,
        'target_pace_formatted': _shared_format_pace(easy_pace),
        'description': description,
        'distance': long_run_km,
        'quality': False,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }


def generate_easy_run(zones: Dict, distance_km: float) -> Dict:
    """Generate an easy recovery run."""
    easy_pace = zones['zone_1_recovery']['pace']

    segments = [
        {
            'name': 'Easy Run',
            'distance_km': round(distance_km, 1),
            'pace_formatted': _shared_format_pace(easy_pace),
            'pace_raw': easy_pace,
            'zone': 'zone_1',
            'zone_label': 'Zone 1',
            'type': 'main',
        },
    ]

    return {
        'type': 'easy',
        'intensity': 'low',
        'zone': 'zone_1',
        'target_pace': easy_pace,
        'target_pace_formatted': _shared_format_pace(easy_pace),
        'description': f"{distance_km:.0f}km easy at {_shared_format_pace(easy_pace)}",
        'distance': distance_km,
        'quality': False,
        'segments': segments,
        'total_duration_est_min': estimate_duration_min(segments),
    }
