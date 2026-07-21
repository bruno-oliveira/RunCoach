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


def test_interval_repeat_becomes_nx_block_with_pace_zones():
    workout = build_intervals_workout(_interval_day())
    desc = workout["description"]

    # Repeats stay as an Nx block wrapping work + recovery (not expanded).
    assert "5x" in desc
    assert "- 1km Z5 Pace" in desc  # I -> Z5, meters rendered as km
    assert "- 90s Z1 Pace Recovery" in desc  # duration in seconds, easy target
    # Warm-up / cool-down are easy-zone and distance-based.
    assert "- 2km Z1 Pace Warmup" in desc
    assert "- 1.5km Z1 Pace Cooldown" in desc
    assert workout["name"]  # non-empty


def test_distance_never_uses_bare_meters():
    # 'm' means minutes in Intervals.icu, so meters must be km.
    desc = build_intervals_workout(_interval_day())["description"]
    assert "400m" not in desc
    assert "1000m" not in desc


def test_moving_time_is_estimated_positive():
    workout = build_intervals_workout(_interval_day())
    assert workout["moving_time"] > 0


def test_missing_pace_str_falls_back_to_zone_default():
    # No pace_str anywhere; duration-based work priced via _DEFAULT_PACES so the
    # moving-time estimate is still positive and the zone target still renders.
    day = {
        "type": "tempo",
        "distance": 8.0,
        "steps": [
            {"kind": "warmup", "duration_s": 600, "pace_zone": "E", "repeat": 1},
            {"kind": "run", "duration_s": 1200, "pace_zone": "T", "repeat": 1},
        ],
    }
    workout = build_intervals_workout(day)
    assert "- 10m Z1 Pace Warmup" in workout["description"]  # 600s -> 10m
    assert "- 20m Z4 Pace" in workout["description"]  # T -> Z4
    assert workout["moving_time"] == 1800


def test_legacy_day_without_steps_uses_distance_fallback():
    workout = build_intervals_workout({"type": "easy", "distance": 8.0})
    assert workout["description"] == "- 8km Z2 Pace"  # easy -> Z2


def test_rest_day_raises():
    with pytest.raises(ValueError):
        build_intervals_workout({"type": "rest", "distance": 0})
