"""Workout distribution logic.

Determines how many of each workout type per week and selects
quality workout types based on race distance and training phase.
Day scheduling is handled by week_scheduler; ratio validation by
distribution_validator.
"""

from typing import Dict, Optional

from app.core.training.distribution_validator import (
    validate_polarized_ratio as _validate_polarized_ratio,
)
from app.core.training.road_profile import classify_road
from app.core.training.trail_profile import TrailProfile, is_trail_target
from app.core.training.tuning import SECOND_QUALITY_MIN_WEEK_KM
from app.core.training.week_scheduler import schedule_workout_types  # noqa: F401


def get_workout_distribution(
    total_km: float,
    max_runs: int,
    phase: str = "build",
    is_recovery_week: bool = False,
    week_number: int = 1,
    phases: Optional[Dict[str, int]] = None,
    target_distance: float = 10.0,
    terrain: Optional[str] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, int]:
    """Calculate how many of each workout type per week."""
    is_backward_compatible_call = (
        phase == "build"
        and not is_recovery_week
        and week_number == 1
        and phases is None
        and target_distance == 10.0
    )

    if is_backward_compatible_call:
        return get_workout_distribution_simple(total_km, max_runs)

    long_runs = 1

    quality_workouts = _phase_quality_count(
        phase, max_runs, total_km, week_number, phases, is_recovery_week
    )

    # Recovery is an additional non-running day, does NOT count towards max_runs
    actual_run_slots = max_runs
    running_days = actual_run_slots - long_runs - quality_workouts
    easy_runs = max(0, running_days)
    max_runs = min(max_runs, 6)
    rest_days = 7 - (max_runs + 1)

    distribution = _build_quality_distribution(
        target_distance,
        terrain,
        quality_workouts,
        phase,
        easy_runs,
        long_runs,
        rest_days,
        week_number,
        trail_profile=trail_profile,
    )

    if not is_recovery_week and max_runs > 2:
        in_build_on_ramp = False
        if phase == "build":
            wib = week_number - phases["base"] if phases else week_number
            in_build_on_ramp = wib <= 2
        too_small_for_second = total_km < SECOND_QUALITY_MIN_WEEK_KM
        distribution = _validate_polarized_ratio(
            distribution,
            phase,
            target_distance,
            trail_profile=trail_profile,
            terrain=terrain,
            suppress_increase=in_build_on_ramp or too_small_for_second,
        )

    return distribution


def _phase_quality_count(
    phase: str,
    max_runs: int,
    total_km: float,
    week_number: int,
    phases: Optional[Dict[str, int]],
    is_recovery_week: bool,
) -> int:
    """Number of quality sessions for the week, before profile tuning.

    Encodes the phase/frequency policy: none on recovery weeks; at 2 runs/week
    (1 long + 1 easy) quality only in build/peak; base stays mostly aerobic; a
    second quality slot appears only in late build / peak for high-frequency,
    sufficient-volume weeks; and the taper keeps one short sharpener.
    """
    if is_recovery_week:
        return 0
    # At 2 runs/week (minimum effective dose for busy schedules), the week is
    # always 1 long + 1 easy — quality workouts need a third running day to
    # keep the weekly 80/20 easy/hard balance intact.
    if max_runs <= 2:
        return 1 if phase in ("build", "peak") else 0
    if phase == "base":
        base_quality_km = total_km * 0.05
        return 1 if (max_runs >= 4 and base_quality_km >= 1.0) else 0
    if phase == "build":
        week_in_build = week_number - phases["base"] if phases else week_number
        if week_in_build <= 2:
            return 1 if max_runs >= 3 else 0
        return 2 if (max_runs >= 5 and total_km >= SECOND_QUALITY_MIN_WEEK_KM) else 1
    if phase == "peak":
        return 2 if (max_runs >= 5 and total_km >= SECOND_QUALITY_MIN_WEEK_KM) else 1
    if phase == "taper":
        # Retain a single short race-pace sharpener through the taper (the
        # PHASE_DISTRIBUTIONS taper rows budget ~10-12% tempo for exactly this).
        # Volume drops but intensity is kept — dropping all quality detrains
        # the runner right before race day (audit G2). max_runs <= 2 already
        # returned 0 above, so there is room for the sharpener here.
        return 1
    return 0


# Re-export kept for backward compatibility — see week_scheduler.py


def _profile_for(
    target_distance: float,
    terrain: Optional[str],
    trail_profile: Optional[TrailProfile] = None,
) -> str:
    """Map (distance, terrain, trail_profile) to a quality-distribution profile name.

    Trail dispatch:
      * ``trail_profile`` wins when present and uses race elevation_class.
      * ``terrain`` models training constraints and is applied later as workout
        substitution (e.g., hills -> flat climb-simulation sessions).
      * The legacy 30 km sentinel is handled via ``is_trail_target``.
    Road distances delegate their band to ``classify_road``.
    """
    if trail_profile is not None:
        return (
            "trail_flat" if trail_profile.elevation_class == "flat" else "trail_hilly"
        )
    if is_trail_target(target_distance, trail_profile):
        return "trail_flat" if terrain == "flat" else "trail_hilly"
    return f"road_{classify_road(target_distance)}"


# Base-phase quality: every profile gets exactly one light quality session,
# but the type depends on the race it's preparing for.
_BASE_PHASE_QUALITY = {
    "trail_hilly": {"hill": 1},
    "trail_flat": {"tempo": 1},
    "road_5k": {"interval": 1},  # strides
    "road_10k": {"interval": 1},  # strides
    "road_half": {"tempo": 1},  # short threshold
    "road_marathon": {"tempo": 1},  # short threshold
}


def _quality_for_trail_hilly(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """Trail (hilly): hills are the dominant stimulus, tempo/interval rotate."""
    if quality_workouts >= 2:
        # Hills every week + rotating second quality session.
        # Week-of-month cycle: weeks 1-2 → intervals, weeks 3-4 → tempo.
        rotating = "interval" if week_number % 4 in (1, 2) else "tempo"
        return {"hill": 1, rotating: 1}
    # Single-quality: hills in 2/3 of weeks, interval on the off week.
    # 3-week cycle: weeks divisible by 3 and 3k+1 → hill, 3k+2 → interval.
    if week_number % 3 in (0, 1):
        return {"hill": 1}
    return {"interval": 1}


def _quality_for_trail_flat(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """Flat trail: replace missing climbs with tempo + interval progression."""
    if phase == "base":
        return {"tempo": 1}

    if quality_workouts >= 2:
        cycle = week_number % 4
        if cycle in (1, 2):
            return {"tempo": 1, "interval": 1}
        if cycle == 3:
            return {"tempo": 2}
        return {"interval": 2}

    # Single-quality weeks rotate threshold and aerobic-power stimulus.
    return {"interval": 1} if week_number % 3 == 0 else {"tempo": 1}


def _quality_for_road_5k(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """5K: VO2max emphasis — intervals dominate."""
    return {"interval": 2 if quality_workouts >= 2 else 1}


def _quality_for_road_10k(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """10K: balanced — 1 interval + optional tempo."""
    result: Dict[str, int] = {"interval": 1}
    if quality_workouts >= 2:
        result["tempo"] = 1
    return result


def _quality_for_road_half(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """Half: balanced — interval and tempo rotate when only 1 quality slot."""
    if quality_workouts >= 2:
        return {"interval": 1, "tempo": 1}
    if week_number % 2 == 1:
        return {"interval": 1}
    return {"tempo": 1}


def _quality_for_road_marathon(
    quality_workouts: int, week_number: int, phase: str
) -> Dict[str, int]:
    """Marathon: tempo/MP emphasis; peak phase drops intervals entirely."""
    if quality_workouts < 2:
        return {"tempo": 1}
    if phase == "peak":
        return {"tempo": 2}
    return {"tempo": 1, "interval": 1}


_PROFILE_BUILDERS = {
    "trail_hilly": _quality_for_trail_hilly,
    "trail_flat": _quality_for_trail_flat,
    "road_5k": _quality_for_road_5k,
    "road_10k": _quality_for_road_10k,
    "road_half": _quality_for_road_half,
    "road_marathon": _quality_for_road_marathon,
}


def _substitute_hills_for_flat_training(
    quality_distribution: Dict[str, int],
    phase: str,
    week_number: int,
    terrain: Optional[str],
    trail_profile: Optional[TrailProfile],
) -> None:
    """Convert hill slots to flat-executable quality sessions.

    This supports mountain race prep when the runner only has flat terrain.
    Race profile still drives how much quality load we prescribe; training
    terrain only decides executable session type.
    """
    if terrain != "flat" or trail_profile is None:
        return
    if trail_profile.elevation_class == "flat":
        return

    hill_slots = quality_distribution.get("hill", 0)
    if hill_slots <= 0:
        return

    quality_distribution["hill"] = 0

    if phase == "base":
        quality_distribution["tempo"] = (
            quality_distribution.get("tempo", 0) + hill_slots
        )
        return

    if phase in ("build", "peak"):
        if trail_profile.elevation_class == "mountainous":
            interval_slots = max(1, round(hill_slots * 0.67))
        else:
            interval_slots = hill_slots // 2
        interval_slots = min(hill_slots, interval_slots)
        tempo_slots = hill_slots - interval_slots
        if week_number % 2 == 0 and tempo_slots > 0:
            interval_slots, tempo_slots = tempo_slots, interval_slots
        quality_distribution["interval"] = (
            quality_distribution.get("interval", 0) + interval_slots
        )
        quality_distribution["tempo"] = (
            quality_distribution.get("tempo", 0) + tempo_slots
        )
        return

    quality_distribution["tempo"] = quality_distribution.get("tempo", 0) + hill_slots


def _build_quality_distribution(
    target_distance: float,
    terrain: Optional[str],
    quality_workouts: int,
    phase: str,
    easy_runs: int,
    long_runs: int,
    rest_days: int,
    week_number: int,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, int]:
    """Assign quality workout types based on race distance, terrain, and phase.

    Dispatches to a per-profile builder keyed by (distance, terrain).
    Base phase always returns a single light quality session;
    build/peak use the profile's full quality pattern.
    """
    distribution = {
        "easy": easy_runs,
        "long": long_runs,
        "interval": 0,
        "tempo": 0,
        "hill": 0,
        "rest": rest_days,
    }

    if quality_workouts == 0:
        return distribution

    profile_name = _profile_for(target_distance, terrain, trail_profile=trail_profile)

    if phase == "base":
        base_quality = dict(_BASE_PHASE_QUALITY[profile_name])
        # Half/marathon base used to pin the slot to tempo every week, and the
        # base catalog has exactly one base tempo session (relaxed cruise) —
        # so identical sessions repeated for the whole base phase. Alternate
        # the slot type so even weeks draw from the strides/fartlek interval
        # pool instead (the selection-side no-repeat window then rotates
        # within each pool).
        if profile_name in ("road_half", "road_marathon") and week_number % 2 == 0:
            base_quality = {"interval": 1}
        distribution.update(base_quality)
        _substitute_hills_for_flat_training(
            distribution,
            phase,
            week_number,
            terrain,
            trail_profile,
        )
        return distribution

    if phase == "taper":
        # The single taper sharpener is a short tempo: the taper budget keeps
        # only tempo (interval/hill are 0%, so any other type would floor to a
        # token 1 km). A brief race-pace cruise keeps the legs sharp while
        # volume tapers (audit G2).
        distribution.update({"tempo": 1})
        return distribution

    distribution.update(
        _PROFILE_BUILDERS[profile_name](quality_workouts, week_number, phase)
    )
    _substitute_hills_for_flat_training(
        distribution,
        phase,
        week_number,
        terrain,
        trail_profile,
    )
    return distribution


def get_workout_distribution_simple(total_km: float, max_runs: int) -> Dict[str, int]:
    """Simplified version of workout distribution for backward compatibility with tests."""
    long_runs = 1
    running_days = max_runs - long_runs

    if max_runs == 3:
        easy_runs = 1
        rest_days = 3
        quality_workouts = 1
    elif max_runs == 4:
        easy_runs = 2
        rest_days = 2
        quality_workouts = 1
    elif max_runs == 5:
        easy_runs = 2
        rest_days = 1
        quality_workouts = 2
    elif max_runs == 6:
        easy_runs = 3
        rest_days = 0
        quality_workouts = 2
    else:
        quality_workouts = max(1, running_days - 1)
        easy_runs = max(0, running_days - quality_workouts)
        rest_days = max(0, max_runs - long_runs - quality_workouts - easy_runs)

    return {
        "easy": easy_runs,
        "long": long_runs,
        "interval": quality_workouts
        if quality_workouts == 1 or (quality_workouts == 2 and max_runs == 4)
        else (1 if quality_workouts >= 1 else 0),
        "tempo": 1 if quality_workouts >= 2 and max_runs > 4 else 0,
        "hill": 0,
        "rest": rest_days,
    }
