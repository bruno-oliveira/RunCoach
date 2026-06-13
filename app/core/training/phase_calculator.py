"""Phase calculation logic for training plans.

Handles phase distribution (base/build/peak/taper), distance categorization,
and recovery week determination.

Trail / ultra plans dispatch through ``TrailProfile`` (see
``app/core/training/trail_profile.py``):

* ``PHASE_DISTRIBUTIONS`` keys are derived from a base trail distribution
  table × elevation-class adjustments — yielding ``TrailFlat``,
  ``TrailRolling``, ``TrailHilly``, ``TrailMountainous`` slots.
* ``calculate_phases`` consults the bracket (short / standard / ultra /
  long_ultra) so ultras get a 3-week taper.

Legacy ``'Trail'`` and ``'FlatTrail'`` keys are retained as aliases of
``TrailHilly`` and ``TrailFlat`` so older callsites keep working until the
next refactor pass.
"""

from typing import Dict, Optional

from app.core.training.road_profile import RoadBand, classify_road
from app.core.training.trail_profile import TrailProfile, is_trail_target
from app.exceptions import InsufficientTimeException

MIN_WEEKS_FOR_PHASES = 6

# Road bands map to the capitalized distribution keys used below.
_ROAD_BAND_TO_KEY: Dict[RoadBand, str] = {
    "5k": "5K",
    "10k": "10K",
    "half": "Half",
    "marathon": "Marathon",
}


# --- Trail distribution: base × elevation-class adjustments -----------------
#
# Base trail distribution mirrors the legacy ``'Trail'`` (hilly) baseline.
# Elevation-class adjustments shift the (tempo / interval / hill) split; easy
# absorbs the residual so weekly buckets always sum to 1.0.
#
# This addresses user flaw #2: flat trails no longer drop quality work — they
# get a tempo + interval boost in place of hill repeats so the runner gets
# comparable training stress.

_TRAIL_BASE_DISTRIBUTION = {
    "base": {"long": 0.45, "tempo": 0.0, "interval": 0.0, "hill": 0.05},
    "build": {"long": 0.45, "tempo": 0.06, "interval": 0.06, "hill": 0.08},
    "peak": {"long": 0.43, "tempo": 0.06, "interval": 0.06, "hill": 0.08},
    "taper": {"long": 0.40, "tempo": 0.06, "interval": 0.0, "hill": 0.04},
}

# Each adjustment dict updates (tempo, interval, hill); flat zeroes hills out
# entirely (no terrain access). Mountainous shifts intensity from intervals
# (track-style speed work) toward hill repeats.
_ELEVATION_ADJUSTMENTS = {
    "flat": {"tempo": +0.10, "interval": +0.05, "hill_zero": True},
    "rolling": {"tempo": +0.04, "interval": 0.00, "hill_delta": -0.04},
    "hilly": {"tempo": 0.00, "interval": 0.00, "hill_delta": 0.00},
    "mountainous": {"tempo": 0.00, "interval": -0.02, "hill_delta": +0.03},
}

_TRAIL_ELEVATION_KEYS = ("flat", "rolling", "hilly", "mountainous")


def _build_trail_distribution(phase: str, elevation_class: str) -> Dict[str, float]:
    base = dict(_TRAIL_BASE_DISTRIBUTION[phase])
    adj = _ELEVATION_ADJUSTMENTS[elevation_class]

    if adj.get("hill_zero"):
        base["hill"] = 0.0
    else:
        base["hill"] = max(0.0, base["hill"] + adj.get("hill_delta", 0.0))

    base["tempo"] = max(0.0, base["tempo"] + adj["tempo"])
    base["interval"] = max(0.0, base["interval"] + adj["interval"])

    others = base["long"] + base["tempo"] + base["interval"] + base["hill"]
    base["easy"] = round(max(0.0, 1.0 - others), 4)
    return base


def _trail_key(elevation_class: str) -> str:
    return f"Trail{elevation_class.capitalize()}"


def _build_phase_distributions() -> Dict[str, Dict[str, Dict[str, float]]]:
    distributions: Dict[str, Dict[str, Dict[str, float]]] = {
        "base": {
            "5K": {
                "long": 0.35,
                "tempo": 0.0,
                "interval": 0.05,
                "hill": 0.0,
                "easy": 0.60,
            },
            "10K": {
                "long": 0.40,
                "tempo": 0.0,
                "interval": 0.05,
                "hill": 0.0,
                "easy": 0.55,
            },
            "Half": {
                "long": 0.45,
                "tempo": 0.05,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.50,
            },
            "Marathon": {
                "long": 0.45,
                "tempo": 0.05,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.50,
            },
        },
        "build": {
            "5K": {
                "long": 0.35,
                "tempo": 0.12,
                "interval": 0.10,
                "hill": 0.05,
                "easy": 0.38,
            },
            "10K": {
                "long": 0.40,
                "tempo": 0.12,
                "interval": 0.10,
                "hill": 0.05,
                "easy": 0.33,
            },
            "Half": {
                "long": 0.45,
                "tempo": 0.10,
                "interval": 0.08,
                "hill": 0.04,
                "easy": 0.33,
            },
            "Marathon": {
                "long": 0.45,
                "tempo": 0.10,
                "interval": 0.08,
                "hill": 0.04,
                "easy": 0.33,
            },
        },
        "peak": {
            "5K": {
                "long": 0.33,
                "tempo": 0.12,
                "interval": 0.10,
                "hill": 0.05,
                "easy": 0.40,
            },
            "10K": {
                "long": 0.38,
                "tempo": 0.12,
                "interval": 0.10,
                "hill": 0.05,
                "easy": 0.35,
            },
            "Half": {
                "long": 0.43,
                "tempo": 0.10,
                "interval": 0.08,
                "hill": 0.04,
                "easy": 0.35,
            },
            "Marathon": {
                "long": 0.43,
                "tempo": 0.10,
                "interval": 0.08,
                "hill": 0.04,
                "easy": 0.35,
            },
        },
        "taper": {
            "5K": {
                "long": 0.30,
                "tempo": 0.12,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.58,
            },
            "10K": {
                "long": 0.35,
                "tempo": 0.12,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.53,
            },
            "Half": {
                "long": 0.40,
                "tempo": 0.10,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.50,
            },
            "Marathon": {
                "long": 0.40,
                "tempo": 0.10,
                "interval": 0.0,
                "hill": 0.0,
                "easy": 0.50,
            },
        },
    }

    for phase in distributions:
        for elev in _TRAIL_ELEVATION_KEYS:
            distributions[phase][_trail_key(elev)] = _build_trail_distribution(
                phase, elev
            )
        # Legacy aliases retained so unmigrated callsites keep working.
        distributions[phase]["Trail"] = distributions[phase][_trail_key("hilly")]
        distributions[phase]["FlatTrail"] = distributions[phase][_trail_key("flat")]

    return distributions


PHASE_DISTRIBUTIONS = _build_phase_distributions()


# --- Distance category dispatch --------------------------------------------


def _normalise_terrain(terrain: Optional[str]) -> Optional[str]:
    """Map the legacy ``terrain`` parameter onto an elevation_class key."""
    if terrain is None:
        return None
    if terrain == "flat":
        return "flat"
    if terrain in _TRAIL_ELEVATION_KEYS:
        return terrain
    # Legacy "hilly" or any unknown non-flat string defaults to hilly.
    return "hilly"


def get_distance_category(
    target_distance: float,
    terrain: Optional[str] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> str:
    """Map target distance (and optional trail context) to a distribution key.

    Args:
        target_distance: Race distance in km.
        terrain: Legacy terrain access string. ``"flat"`` selects the flat
            trail distribution; other non-None values are treated as hilly.
        trail_profile: Preferred input — when present its elevation_class
            wins over the legacy ``terrain`` argument.
    """
    if trail_profile is not None:
        return _trail_key(trail_profile.elevation_class)

    if is_trail_target(target_distance, trail_profile):
        # Legacy default: 30 km plans without an explicit trail_profile
        # default to the hilly distribution (matches the historic behavior).
        normalised = _normalise_terrain(terrain) or "hilly"
        return _trail_key(normalised)
    return _ROAD_BAND_TO_KEY[classify_road(target_distance)]


# --- Phase length profiles --------------------------------------------------
#
# These drive how many weeks land in base / build / peak / taper. Trail
# phase weeks depend on the **bracket** (ultra and long_ultra get a 3-week
# taper); the per-week distribution above depends on the **elevation class**.

_ROAD_PHASE_PROFILES = {
    "5K": {"base_pct": 0.35, "build_pct": 0.30, "peak_pct": 0.20, "taper": 2},
    "10K": {"base_pct": 0.35, "build_pct": 0.30, "peak_pct": 0.15, "taper": 2},
    "Half": {"base_pct": 0.35, "build_pct": 0.35, "peak_pct": 0.15, "taper": 2},
    "Marathon": {"base_pct": 0.30, "build_pct": 0.35, "peak_pct": 0.15, "taper": 3},
}

_TRAIL_BRACKET_PROFILES = {
    "short": {"base_pct": 0.35, "build_pct": 0.35, "peak_pct": 0.15, "taper": 2},
    "standard": {"base_pct": 0.35, "build_pct": 0.35, "peak_pct": 0.15, "taper": 2},
    "ultra": {"base_pct": 0.30, "build_pct": 0.35, "peak_pct": 0.20, "taper": 3},
    "long_ultra": {"base_pct": 0.30, "build_pct": 0.35, "peak_pct": 0.20, "taper": 3},
}


def _phase_profile_for(target_distance: float, trail_profile: Optional[TrailProfile]):
    if trail_profile is not None:
        return _TRAIL_BRACKET_PROFILES[trail_profile.bracket]
    category = get_distance_category(target_distance)
    if category in _ROAD_PHASE_PROFILES:
        return _ROAD_PHASE_PROFILES[category]
    # Legacy 30 km without trail_profile → standard-bracket trail profile.
    return _TRAIL_BRACKET_PROFILES["standard"]


def calculate_phases(
    weeks: int,
    target_distance: float = 10.0,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, int]:
    """
    Calculate distance-aware phase distribution.

    Marathon, ultra, and long-ultra plans get longer builds and tapers.
    5K plans get more sharpening (peak) and shorter tapers.

    Args:
        weeks: Total training plan duration.
        target_distance: Race distance in km (affects road phase proportions).
        trail_profile: Optional trail profile; when present its bracket
            drives the phase split (ultras get a 3-week taper).

    Returns:
        Dict with phase durations: ``{'base': int, 'build': int, 'peak': int, 'taper': int}``.
    """
    if weeks < MIN_WEEKS_FOR_PHASES:
        raise InsufficientTimeException(
            f"Minimum {MIN_WEEKS_FOR_PHASES} weeks required for structured periodization.",
            suggestion=f"Extend your plan to at least {MIN_WEEKS_FOR_PHASES} weeks for a safe base/build/peak/taper structure.",
        )

    profile = _phase_profile_for(target_distance, trail_profile)

    # Taper is prescribed by distance (marathon = 3 weeks, 5K = 1 week)
    taper = min(profile["taper"], max(1, weeks // 4))

    # Distribute remaining weeks among base/build/peak
    remaining = weeks - taper
    total_pct = profile["base_pct"] + profile["build_pct"] + profile["peak_pct"]
    base = max(2, round(remaining * profile["base_pct"] / total_pct))
    build = max(2, round(remaining * profile["build_pct"] / total_pct))
    peak = max(1, remaining - base - build)

    # Safety: if rounding pushed us over, trim from the largest non-taper phase
    # but never let any phase drop below its floor
    while base + build + peak + taper > weeks:
        if base >= build and base >= peak and base > 2:
            base -= 1
        elif build >= peak and build > 2:
            build -= 1
        elif peak > 1:
            peak -= 1
        else:
            # All at minimums — trim from the largest anyway
            if base >= build and base >= peak:
                base -= 1
            elif build >= peak:
                build -= 1
            else:
                peak -= 1

    # Safety: if rounding left us short, add to build
    while base + build + peak + taper < weeks:
        build += 1

    return {"base": base, "build": build, "peak": peak, "taper": taper}


def get_phase(week_number: int, phases: Dict[str, int]) -> str:
    """
    Determine which phase a given week belongs to.

    Returns: 'base', 'build', 'peak', or 'taper'
    """
    if week_number <= phases["base"]:
        return "base"
    elif week_number <= phases["base"] + phases["build"]:
        return "build"
    elif week_number <= phases["base"] + phases["build"] + phases["peak"]:
        return "peak"
    else:
        return "taper"


# Loading weeks between deloads — a classic 3:1 cycle (3 loading weeks then one
# recovery/down week). Counted continuously across base+build+peak so the
# absorption cadence stays even regardless of phase boundaries.
LOADING_WEEKS_PER_BLOCK = 3


def recovery_week_set(phases: Optional[Dict[str, int]]) -> frozenset[int]:
    """Week numbers that are deload/recovery weeks for a given phase split.

    A recovery week is inserted after every ``LOADING_WEEKS_PER_BLOCK`` loading
    weeks, counted continuously across the base+build+peak span so the cadence
    does not reset at phase boundaries (the old per-phase counter left the most
    common 8-12 week plans with zero deloads). Taper weeks are never recovery
    weeks, and the final loading week before the taper is always preserved as a
    peak-stimulus week rather than converted into a deload.
    """
    if not phases:
        return frozenset()
    loading_span = (
        phases.get("base", 0) + phases.get("build", 0) + phases.get("peak", 0)
    )
    recovery: set[int] = set()
    loading_streak = 0
    for week in range(1, loading_span + 1):
        # Keep the last non-taper week as a loading (peak) week — never deload it.
        if week == loading_span:
            break
        if loading_streak == LOADING_WEEKS_PER_BLOCK:
            recovery.add(week)
            loading_streak = 0
        else:
            loading_streak += 1

    # A short peak block (<= 2 weeks) must not lose its opening week to the
    # cadence: a 16-week marathon split (base 5 / build 6 / peak 2) landed
    # the wk-12 deload on the first peak week, leaving a single true peak
    # week. Snap that deload one week earlier (last build week) so the
    # runner absorbs *before* the peak block and then runs all of it.
    peak_len = phases.get("peak", 0)
    first_peak = phases.get("base", 0) + phases.get("build", 0) + 1
    if (
        0 < peak_len <= 2
        and first_peak in recovery
        and first_peak - 1 >= 1
        and (first_peak - 1) not in recovery
    ):
        recovery.discard(first_peak)
        recovery.add(first_peak - 1)
    return frozenset(recovery)


def is_recovery_week(
    week_number: int, phase: str, phases: Optional[Dict[str, int]] = None
) -> bool:
    """
    Determine if a week is a recovery/deload week.

    Deloads follow a global ~3:1 cadence (a recovery week after every
    ``LOADING_WEEKS_PER_BLOCK`` loading weeks) spanning base+build+peak, so
    every plan of ~8 weeks or longer gets at least one mid-plan absorption
    week. No recovery weeks in taper; the final loading week before the taper
    is always preserved. See :func:`recovery_week_set`.
    """
    if phase == "taper":
        return False
    if not phases:
        return week_number % 4 == 0
    return week_number in recovery_week_set(phases)


# Trail brackets that get an intensive weekend. Short-bracket plans (8-21 km on
# a compressed prep) are excluded — there isn't room for an overcompensation
# block before the taper.
_ITW_BRACKETS = ("standard", "ultra", "long_ultra")


def is_intensive_weekend(
    week_number: int,
    phase: str,
    phases: Dict[str, int],
    trail_profile: Optional[TrailProfile] = None,
) -> bool:
    """Whether ``week_number`` should be a trail Intensive Training Weekend.

    An ITW concentrates a Saturday trail-quality session and a Sunday long
    run on fatigued legs to trigger overcompensation (the RunMotion
    "intensive weekend" concept). Fires at most once per plan, on the final
    loading week of the peak phase — the last hard week before the taper,
    which is naturally 2-3 weeks before the race depending on taper length.

    True only for trail plans (``trail_profile`` set) of a standard/ultra/
    long_ultra bracket. The peak phase's last week is never the recovery week
    (recovery falls on week-in-peak 3 of a 4+ week peak), so it is always a
    valid loading week.
    """
    if trail_profile is None:
        return False
    if trail_profile.bracket not in _ITW_BRACKETS:
        return False
    if phase != "peak":
        return False
    peak_end_week = phases["base"] + phases["build"] + phases["peak"]
    if is_recovery_week(week_number, phase, phases):
        return False
    return week_number == peak_end_week
