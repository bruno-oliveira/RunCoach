"""Trail profile classification for parameterized trail / ultra plans.

Replaces the legacy ``target_distance == 30.0`` literal and the binary
``terrain in {'flat', 'hilly'}`` toggle with a profile derived from the
user's actual race goal: distance and total elevation gain.

The profile drives:

* phase distribution (hill vs tempo allocation)
* mileage progression and peak ceilings
* long-run cap and back-to-back scheduling
* strength rotation (plyometric vs trail-stability)
* key-workout selection (vertical repeats vs flat-trail tempo)
* race protocol (pacer / drop-bag / night-run sections)
* nutrition uplift (continuous in distance + elevation)

Range validation is the caller's responsibility (PlanRequest validators).
This module is pure classification: any non-negative input produces a
profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# Legacy sentinel: plans created before parameterized trail profiles encoded
# "this is a trail plan" as a 30 km target distance. New code threads a
# TrailProfile instead; this constant + ``is_trail_target`` keep the one
# remaining literal in a single place during the migration.
TRAIL_SENTINEL_KM = 30.0

# Supported trail distance range. Below 8 km the user picks a road preset
# (5K / 10K). 163 km ≈ 100 miles, the upper bound the user explicitly named.
TRAIL_DISTANCE_MIN_KM = 8.0
TRAIL_DISTANCE_MAX_KM = 163.0

TRAIL_ELEVATION_MIN_M = 0.0
TRAIL_ELEVATION_MAX_M = 10000.0

# Bracket cutoffs in km. Each band is upper-exclusive; ``long_ultra``
# absorbs everything from 80 km up to TRAIL_DISTANCE_MAX_KM.
_BRACKET_SHORT_MAX_KM = 21.0
_BRACKET_STANDARD_MAX_KM = 42.2
_BRACKET_ULTRA_MAX_KM = 80.0

# Elevation-class cutoffs in m/km. Aligned with
# vdot_calculator.TRAIL_ELEVATION_M_PER_KM (20 m/km) — our ``rolling``
# band straddles that historical threshold rather than replacing it.
_ELEV_FLAT_MAX_M_PER_KM = 10.0
_ELEV_ROLLING_MAX_M_PER_KM = 25.0
_ELEV_HILLY_MAX_M_PER_KM = 50.0


Bracket = Literal["short", "standard", "ultra", "long_ultra"]
ElevationClass = Literal["flat", "rolling", "hilly", "mountainous"]


@dataclass(frozen=True)
class TrailProfile:
    """Parameterized trail profile threaded through plan generation."""

    distance_km: float
    elevation_gain_m: float
    bracket: Bracket
    elevation_class: ElevationClass

    @property
    def m_per_km(self) -> float:
        if self.distance_km <= 0:
            return 0.0
        return self.elevation_gain_m / self.distance_km

    @property
    def is_ultra(self) -> bool:
        return self.bracket in ("ultra", "long_ultra")

    @property
    def is_long_ultra(self) -> bool:
        return self.bracket == "long_ultra"

    @property
    def category_key(self) -> str:
        """Compound key consumed by phase distribution and workout lookup.

        Example: ``Trail_standard_hilly``, ``Trail_long_ultra_mountainous``.
        """
        return f"Trail_{self.bracket}_{self.elevation_class}"


def _classify_bracket(distance_km: float) -> Bracket:
    if distance_km < _BRACKET_SHORT_MAX_KM:
        return "short"
    if distance_km < _BRACKET_STANDARD_MAX_KM:
        return "standard"
    if distance_km < _BRACKET_ULTRA_MAX_KM:
        return "ultra"
    return "long_ultra"


def _classify_elevation(distance_km: float, elevation_gain_m: float) -> ElevationClass:
    if distance_km <= 0:
        return "flat"
    m_per_km = elevation_gain_m / distance_km
    if m_per_km < _ELEV_FLAT_MAX_M_PER_KM:
        return "flat"
    if m_per_km < _ELEV_ROLLING_MAX_M_PER_KM:
        return "rolling"
    if m_per_km < _ELEV_HILLY_MAX_M_PER_KM:
        return "hilly"
    return "mountainous"


def classify_trail(distance_km: float, elevation_gain_m: float) -> TrailProfile:
    """Build a :class:`TrailProfile` from raw inputs.

    Args:
        distance_km: Race distance in km. Expected in
            [``TRAIL_DISTANCE_MIN_KM``, ``TRAIL_DISTANCE_MAX_KM``] but the
            classifier is defensive: any non-negative value yields a profile.
        elevation_gain_m: Total race elevation gain in m. Expected in
            [0, ``TRAIL_ELEVATION_MAX_M``].
    """
    bracket = _classify_bracket(distance_km)
    elevation_class = _classify_elevation(distance_km, elevation_gain_m)
    return TrailProfile(
        distance_km=distance_km,
        elevation_gain_m=elevation_gain_m,
        bracket=bracket,
        elevation_class=elevation_class,
    )


def is_trail_target(
    distance_km: float, trail_profile: Optional[TrailProfile] = None
) -> bool:
    """True when a plan should be treated as trail.

    Prefers an explicit ``trail_profile``; falls back to the legacy
    ``TRAIL_SENTINEL_KM`` (30 km) for plans that predate parameterized trail
    profiles. Single home for the sentinel check that was scattered across the
    phase, mileage, strength, and distribution modules.
    """
    return trail_profile is not None or distance_km == TRAIL_SENTINEL_KM


# --- Bracket-aware plan constraints -----------------------------------------
# Used by PlanRequest validators to enforce week / runs-per-week / mileage
# floors that scale with race demands. Brackets defined above.

_BRACKET_MIN_WEEKS = {
    "short": 5,
    "standard": 6,
    "ultra": 12,
    "long_ultra": 16,
}

_BRACKET_MAX_WEEKS = {
    "short": 18,
    "standard": 22,
    "ultra": 32,
    "long_ultra": 40,
}

_BRACKET_MIN_RUNS = {
    "short": 3,
    "standard": 4,
    "ultra": 5,
    "long_ultra": 6,
}


def trail_min_weeks(profile: TrailProfile) -> int:
    return _BRACKET_MIN_WEEKS[profile.bracket]


def trail_max_weeks(profile: TrailProfile) -> int:
    return _BRACKET_MAX_WEEKS[profile.bracket]


def trail_min_runs_per_week(profile: TrailProfile) -> int:
    return _BRACKET_MIN_RUNS[profile.bracket]


def trail_min_weekly_mileage(profile: TrailProfile) -> float:
    """Minimum recommended weekly base mileage to start a plan for this profile.

    Floor is 15 km/wk (matches legacy 30 km/hilly), then scales with distance
    so an ultra runner can't start from a 15 km base. Mountainous adds 20%
    because the eccentric and metabolic load is higher per km.
    """
    base = max(15.0, 0.35 * profile.distance_km)
    if profile.elevation_class == "mountainous":
        base *= 1.20
    return round(base, 1)


def trail_max_weekly_mileage(profile: TrailProfile) -> float:
    """Soft upper bound used to surface a 'high mileage' warning.

    Continuous in distance + elevation; saturates around 140 km/wk.
    """
    raw = 35.0 + 0.85 * profile.distance_km + 0.0035 * profile.elevation_gain_m
    return round(min(140.0, max(50.0, raw)), 1)
