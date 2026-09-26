"""Road race distance bands — single source for the 5K/10K/Half/Marathon cutoffs.

Mirrors :func:`app.core.training.trail_profile.classify_trail` for road races:
the bracket boundaries that decide which preset a road distance maps to live
here, so shifting or adding a band is a one-line change instead of a sweep
across the phase, mileage, pace, and tip modules. Each consumer maps the
returned band to its own per-distance values.
"""

from __future__ import annotations

from typing import Literal, Tuple

RoadBand = Literal["5k", "10k", "half", "marathon"]

# Upper-inclusive cutoffs in km, shortest→longest. Anything beyond the last
# cutoff falls into the marathon band.
_ROAD_BAND_CUTOFFS: Tuple[Tuple[float, RoadBand], ...] = (
    (5.0, "5k"),
    (10.0, "10k"),
    (21.1, "half"),
)


def classify_road(distance_km: float) -> RoadBand:
    """Map a road race distance (km) to its training band."""
    for cutoff, band in _ROAD_BAND_CUTOFFS:
        if distance_km <= cutoff:
            return band
    return "marathon"


# Canonical race names, keyed by the exact distances the goal form offers.
_RACE_NAMES: Tuple[Tuple[float, str], ...] = (
    (5.0, "5K"),
    (10.0, "10K"),
    (21.1, "Half Marathon"),
    (42.2, "Marathon"),
)


def race_name(distance_km: object) -> str:
    """Name a road race the way a runner says it: "Half Marathon", not "21.1K".

    Accepts the stored ``target_distance`` as-is (a float, or the text column's
    ``"21.1"``). A non-standard distance reads as kilometres ("28 km"); a value
    that isn't a number at all is returned unchanged rather than raising in a
    template.
    """
    try:
        km = float(distance_km)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(distance_km)
    for canonical, name in _RACE_NAMES:
        if abs(km - canonical) < 0.05:
            return name
    return f"{km:g} km"
