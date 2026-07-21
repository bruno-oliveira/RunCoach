"""Unit tests for the steps -> Intervals.icu workout description converter."""

import pytest

from app.core.training.workout_steps.intervals_export import build_intervals_workout


def _interval_day() -> dict:
    return {
        "type": "interval",
        "key_workout_name": "5K VO2max 1000s",
        "distance": 9.0,
        "steps": [
            {"kind": "warmup", "distance_m": 2000, "pace_zone": "E", "repeat": 1},
            {
                "kind": "run",
                "label": "5 × 1 km",
                "distance_m": 1000,
                "pace_zone": "I",
                "pace_str": "4:00/km",
                "repeat": 5,
            },
            {"kind": "recovery", "duration_s": 90, "repeat": 4},
            {"kind": "cooldown", "distance_m": 1500, "pace_zone": "E", "repeat": 1},
        ],
    }


def test_interval_repeat_becomes_nx_block_with_absolute_pace():
    workout = build_intervals_workout(_interval_day())
    desc = workout["description"]

    # Repeats stay as an Nx block wrapping work + recovery (not expanded).
    assert "5x" in desc
    # Work rep carries its concrete pace_str as an absolute target.
    assert "- 1km 4:00/km Pace" in desc  # meters rendered as km
    # Recovery has no pace -> easy-default absolute pace (8:00/km).
    assert "- 90s 8:00/km Pace" in desc
    # Warm-up / cool-down have zone E but no pace_str -> E default (8:00/km).
    assert "- 2km 8:00/km Pace" in desc
    assert "- 1.5km 8:00/km Pace" in desc
    assert workout["name"]  # non-empty


def test_pace_range_renders_fast_slow():
    day = {
        "type": "long",
        "distance": 16.0,
        "steps": [
            {
                "kind": "run",
                "distance_m": 16000,
                "pace_zone": "E",
                "pace_str": "6:00-6:40/km",
                "repeat": 1,
            },
        ],
    }
    desc = build_intervals_workout(day)["description"]
    assert "- 16km 6:00/km-6:40/km Pace" in desc


def test_distance_never_uses_bare_meters():
    # 'm' means minutes in Intervals.icu, so meters must be km.
    desc = build_intervals_workout(_interval_day())["description"]
    assert "400m" not in desc
    assert "1000m" not in desc


def test_moving_time_is_estimated_positive():
    workout = build_intervals_workout(_interval_day())
    assert workout["moving_time"] > 0


def test_missing_pace_str_falls_back_to_zone_default():
    # No pace_str anywhere; the zone's default pace becomes the absolute target
    # so the watch still gets a concrete pace band.
    day = {
        "type": "tempo",
        "distance": 8.0,
        "steps": [
            {"kind": "warmup", "duration_s": 600, "pace_zone": "E", "repeat": 1},
            {"kind": "run", "duration_s": 1200, "pace_zone": "T", "repeat": 1},
        ],
    }
    workout = build_intervals_workout(day)
    assert "- 10m 8:00/km Pace" in workout["description"]  # 600s -> 10m, E default
    assert "- 20m 6:30/km Pace" in workout["description"]  # T default 6.5 -> 6:30
    assert workout["moving_time"] == 1800


def test_legacy_day_without_steps_uses_distance_fallback():
    workout = build_intervals_workout({"type": "easy", "distance": 8.0})
    assert workout["description"] == "- 8km 8:00/km Pace"  # easy -> E default


def test_rest_day_raises():
    with pytest.raises(ValueError):
        build_intervals_workout({"type": "rest", "distance": 0})
