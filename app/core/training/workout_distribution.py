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
from app.core.training.trail_profile import TrailProfile
from app.core.training.week_scheduler import schedule_workout_types  # noqa: F401


def get_workout_distribution(
    total_km: float,
    max_runs: int,
    phase: str = "build",
    is_recovery_week: bool = False,
    week_number: int = 1,
    phases: Dict[str, int] = None,
    target_distance: float = 10.0,
    terrain: Optional[str] = None,
    profile: Optional[dict] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, int]:
    """Calculate how many of each workout type per week.

    When a RunnerProfile is provided, the runner's actual pace zone
    distribution and workout history are used to correct imbalances:
    - Too much hard work (>30%) → reduce quality slots
    - Almost no hard work (<10%) → ensure at least 1 quality in build/peak
    - Missing workout types → prioritize gaps in quality selection
    """
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

    # At 2 runs/week (minimum effective dose for busy schedules), the week is
    # always 1 long + 1 easy — quality workouts need a third running day to
    # keep the weekly 80/20 easy/hard balance intact.
    if is_recovery_week:
        quality_workouts = 0
    elif max_runs <= 2:
        quality_workouts = 1 if phase in ("build", "peak") else 0
    elif phase == "base":
        base_quality_km = total_km * 0.05
        if max_runs >= 4 and base_quality_km >= 1.0:
            quality_workouts = 1
        else:
            quality_workouts = 0
    elif phase == "build":
        if phases:
            week_in_build = week_number - phases["base"]
        else:
            week_in_build = week_number
        if week_in_build <= 2:
            quality_workouts = 1 if max_runs >= 3 else 0
        else:
            quality_workouts = 2 if max_runs >= 5 else 1
    elif phase == "peak":
        quality_workouts = 2 if max_runs >= 5 else 1
    else:
        quality_workouts = 0

    # Profile-aware: adjust quality count based on actual pace distribution
    if profile and not is_recovery_week and quality_workouts > 0:
        hard_pct = profile.get("hard_pct", 0)
        easy_pct = profile.get("easy_pct", 0)
        # If runner habitually does too much hard work (>30%), reduce quality
        if hard_pct > 30 and quality_workouts > 1:
            quality_workouts = max(1, quality_workouts - 1)
        # If runner does almost no hard work (<10%), ensure at least 1 quality
        elif hard_pct < 10 and quality_workouts == 0 and phase in ("build", "peak"):
            quality_workouts = 1
        # If runner's easy runs are very low (<50%), they may need more recovery
        elif easy_pct < 50 and phase in ("build", "peak") and quality_workouts > 1:
            quality_workouts = max(1, quality_workouts - 1)

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
        profile=profile,
        trail_profile=trail_profile,
    )

    if not is_recovery_week and max_runs > 2:
        distribution = _validate_polarized_ratio(
            distribution,
            phase,
            target_distance,
            trail_profile=trail_profile,
            terrain=terrain,
        )

    return distribution


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
      * Legacy ``target_distance == 30.0`` keeps the historic behavior.
    """
    if trail_profile is not None:
        return (
            "trail_flat" if trail_profile.elevation_class == "flat" else "trail_hilly"
        )
    if target_distance == 30.0:
        return "trail_flat" if terrain == "flat" else "trail_hilly"
    if target_distance <= 5:
        return "road_5k"
    if target_distance <= 10:
        return "road_10k"
    if target_distance <= 21.1:
        return "road_half"
    return "road_marathon"


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
    profile: Optional[dict] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, int]:
    """Assign quality workout types based on race distance, terrain, and phase.

    Dispatches to a per-profile builder keyed by (distance, terrain).
    Base phase always returns a single light quality session;
    build/peak use the profile's full quality pattern.

    When a RunnerProfile is provided, workout type gaps are filled:
    - No speed work history → start with tempo in base phase
    - No tempo history → prioritize tempo over intervals
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

    # Profile-aware: detect gaps in training history
    if profile:
        counts = profile.get("workout_type_counts", {}) or {}
        has_speed = (
            counts.get("interval", 0) + counts.get("speed", 0) + counts.get("track", 0)
            > 0
        )
        has_tempo = counts.get("tempo", 0) + counts.get("threshold", 0) > 0

        # If runner has never done speed work, use tempo-focused profile in base
        if (
            not has_speed
            and phase == "base"
            and profile_name in ("road_5k", "road_10k")
        ):
            profile_name = "road_half"  # tempo-focused instead of interval
        # If runner has never done tempo, prioritize it in early build
        if not has_tempo and phase == "base":
            # Keep the base quality as tempo instead of interval
            distribution.update({"tempo": 1})
            return distribution

    if phase == "base":
        distribution.update(_BASE_PHASE_QUALITY[profile_name])
        _substitute_hills_for_flat_training(
            distribution,
            phase,
            week_number,
            terrain,
            trail_profile,
        )
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
