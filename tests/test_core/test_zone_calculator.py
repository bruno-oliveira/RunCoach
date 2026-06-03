"""Tests for the 5-band display zone table (audit B1 monotonic + G6 partition)."""

import pytest

from app.core.training.zone_calculator import calculate_zones

_ORDER = [
    "zone_1_recovery",
    "zone_2_aerobic",
    "zone_3_tempo",
    "zone_4_vo2max",
    "zone_5_race",
]


@pytest.mark.parametrize("vdot", [40, 50, 60, 70])
def test_fitness_ladder_is_strictly_faster_each_step(vdot):
    """B1: with no goal pace the ladder must be strictly monotonic (each zone
    faster than the previous), including zone 5."""
    z = calculate_zones(vdot=vdot)
    paces = [z[k]["pace"] for k in _ORDER]
    for a, b in zip(paces, paces[1:]):
        assert b < a, f"VDOT {vdot}: zone paces not strictly faster: {paces}"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vdot": 50},  # fitness / vdot path
        {},  # no-vdot fallback
        {"vdot": 50, "goal_pace": 4.5},  # performance / goal path
    ],
)
def test_zones_are_a_contiguous_partition(kwargs):
    """G6: adjacent bands share an edge — no pace region falls into no zone.

    The zone-5 anchor may sit apart on the goal path (the runner's literal race
    target), so contiguity is asserted across zones 1-4.
    """
    z = calculate_zones(**kwargs)
    for lo, hi in zip(_ORDER, _ORDER[1:]):
        if hi == "zone_5_race" and kwargs.get("goal_pace") is not None:
            continue
        prev_fast = z[lo]["pace_range"][1]
        next_slow = z[hi]["pace_range"][0]
        assert abs(prev_fast - next_slow) < 0.01, (
            f"gap between {lo} (fast {prev_fast}) and {hi} (slow {next_slow})"
        )


def test_tempo_band_is_not_a_sliver():
    """G6: the tempo band spans a meaningful range (T..I), not an ~8 s sliver."""
    z = calculate_zones(vdot=50)
    slow, fast = z["zone_3_tempo"]["pace_range"]
    assert slow - fast > 0.2, f"tempo band too thin: {slow}..{fast}"


def test_goal_pace_anchors_zone_5_and_is_left_intact():
    """B1: the performance/goal path keeps zone 5 at the user's goal pace."""
    z = calculate_zones(vdot=50, goal_pace=4.5)
    assert z["zone_5_race"]["pace"] == 4.5
    assert "target effort" in z["zone_5_race"]["description"]
