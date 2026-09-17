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
