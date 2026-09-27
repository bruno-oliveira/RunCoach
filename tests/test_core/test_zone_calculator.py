"""Tests for the 5-band display zone table (audit B1 monotonic + G6 partition)."""

import pytest

from app.core.training.physiology.zone_calculator import calculate_zones

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
    """G6: the tempo band spans a meaningful range, not an ~8 s sliver."""
    z = calculate_zones(vdot=50)
    slow, fast = z["zone_3_tempo"]["pace_range"]
    assert slow - fast > 0.2, f"tempo band too thin: {slow}..{fast}"


def test_goal_pace_anchors_zone_5_and_is_left_intact():
    """B1: the performance/goal path keeps zone 5 at the user's goal pace."""
    z = calculate_zones(vdot=50, goal_pace=4.5)
    assert z["zone_5_race"]["pace"] == 4.5
    assert "target effort" in z["zone_5_race"]["description"]


def test_race_pace_hr_label_is_distance_aware():
    """Race pace is pinned to the goal, but its HR effort label tracks the race
    distance: a 5K goal is a high-HR effort, a marathon goal a sustained
    aerobic one — not always the band's nominal 95-100%."""
    short = calculate_zones(vdot=50, goal_pace=4.5, max_hr=190, race_distance_km=5.0)
    long = calculate_zones(vdot=50, goal_pace=4.5, max_hr=190, race_distance_km=42.195)
    # Pace is the literal goal in both.
    assert short["zone_5_race"]["pace"] == 4.5
    assert long["zone_5_race"]["pace"] == 4.5
    # 5K borrows the VO2max band's HR; marathon the tempo band's (lower).
    assert short["zone_5_race"]["hr_range"] == short["zone_4_vo2max"]["hr_range"]
    assert long["zone_5_race"]["hr_range"] == long["zone_3_tempo"]["hr_range"]
    assert short["zone_5_race"]["hr_range"] != long["zone_5_race"]["hr_range"]


def test_race_pace_hr_label_untouched_without_distance():
    """Omitting race_distance_km leaves the legacy zone-5 HR label intact."""
    z = calculate_zones(vdot=50, goal_pace=4.5, max_hr=190)
    assert z["zone_5_race"]["hr_range"] == "95-100%"


@pytest.mark.parametrize("vdot", [35, 50, 65])
def test_threshold_pace_sits_on_the_zone_3_4_line(vdot):
    """Threshold pace is where HR reaches LTHR, and LTHR is the Zone 3/4 edge
    of the HR bands -- so T must be the fast edge of zone 3 and the slow edge of
    zone 4. It used to open zone 3, labelling T..I paces with a band that ends
    at LTHR: half a zone below the HR those paces actually produce."""
    from app.core.training.physiology.vdot_calculator import VDOTCalculator

    t_pace = VDOTCalculator.get_pace_zones(vdot)["T"]["pace_min_km"]
    z = calculate_zones(vdot=vdot, max_hr=190, lthr=170)
    assert z["zone_3_tempo"]["pace_range"][1] == t_pace
    assert z["zone_4_vo2max"]["pace_range"][0] == t_pace
    # ...alongside the BPM band that ends / starts on LTHR.
    assert z["zone_3_tempo"]["hr_bpm_range"].endswith("-170 BPM")
    assert z["zone_4_vo2max"]["hr_bpm_range"].startswith("170-")


def test_easy_pace_is_zone_2():
    """Easy runs target HR zone 2, so the E band is zone 2's pace range."""
    from app.core.training.physiology.vdot_calculator import VDOTCalculator

    e = VDOTCalculator.get_pace_zones(50)["E"]
    z = calculate_zones(vdot=50)
    assert z["zone_2_aerobic"]["pace_range"] == (
        e["pace_min_km_slow"],
        e["pace_min_km_fast"],
    )


@pytest.mark.parametrize("vdot", [40, 60])
def test_each_anchor_is_the_fast_edge_of_its_band(vdot):
    """The workout builders read `pace`; it must lie on its own band."""
    z = calculate_zones(vdot=vdot)
    for slug in _ORDER:
        slow, fast = z[slug]["pace_range"]
        assert slow > fast
        assert z[slug]["pace"] == fast
