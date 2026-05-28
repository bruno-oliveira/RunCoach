"""Characterization tests for the road-band classifier.

Locks the band boundaries that previously lived as inline `<=` ladders across
the phase, mileage, pace, and tip modules.
"""

import pytest

from app.core.training.road_profile import classify_road
from app.core.training.trail_profile import TRAIL_SENTINEL_KM, is_trail_target


@pytest.mark.parametrize(
    "distance_km, expected",
    [
        (4.9, "5k"),
        (5.0, "5k"),
        (5.1, "10k"),
        (10.0, "10k"),
        (10.1, "half"),
        (21.1, "half"),
        (21.2, "marathon"),
        (30.0, "marathon"),  # legacy trail sentinel still classifies as a road band
        (42.2, "marathon"),
        (100.0, "marathon"),
    ],
)
def test_classify_road_boundaries(distance_km, expected):
    assert classify_road(distance_km) == expected


class TestIsTrailTarget:
    def test_explicit_profile_wins(self):
        sentinel = object()  # any non-None trail_profile
        assert is_trail_target(10.0, sentinel) is True

    def test_legacy_sentinel(self):
        assert is_trail_target(TRAIL_SENTINEL_KM) is True
        assert is_trail_target(30) is True  # int form matches 30.0

    def test_road_distances_are_not_trail(self):
        for d in (5.0, 10.0, 21.1, 42.2):
            assert is_trail_target(d) is False
