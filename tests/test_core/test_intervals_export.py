"""Unit tests for the steps -> Intervals.icu workout description converter."""

import pytest

from app.core.training.workouts.workout_steps.intervals_export import (
    build_intervals_workout,
)


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

    # Five reps with four recoveries: four rep+recovery units, then the last
    # rep runs straight into the cool-down (no phantom fifth recovery).
    assert "Rep 4x\n- Interval 1km 4:00/km Pace\n- Recovery 1m30s" in desc
    assert desc.count("- Interval 1km 4:00/km Pace") == 2
    assert "5x" not in desc
    # A zone-less recovery has no pace to borrow, so it stays open rather than
    # beeping an 8:00/km default that isn't the runner's number.
    assert "- Recovery 1m30s\n" in desc
    # Warm-up / cool-down have zone E but no pace_str -> E default (8:00/km).
    assert "- Warmup 2km 8:00/km Pace" in desc
    assert "- Cooldown 1.5km 8:00/km Pace" in desc
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
    assert "- Easy 16km 6:00/km-6:40/km Pace" in desc


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
    assert "- Warmup 10m 8:00/km Pace" in workout["description"]  # 600s -> 10m
    assert "- Threshold 20m 6:30/km Pace" in workout["description"]  # T -> 6:30
    assert workout["moving_time"] == 1800


def test_legacy_day_without_steps_uses_distance_fallback():
    workout = build_intervals_workout({"type": "easy", "distance": 8.0})
    assert workout["description"] == "- Easy 8km 8:00/km Pace"  # E default


def test_rest_day_raises():
    with pytest.raises(ValueError):
        build_intervals_workout({"type": "rest", "distance": 0})


def _step(kind, repeat=1, **kw):
    return {"kind": kind, "repeat": repeat, **kw}


def test_over_under_alternates_instead_of_running_all_overs_first():
    day = {
        "steps": [
            _step("run", 6, duration_s=90, pace_zone="I", pace_str="3:54/km"),
            _step("run", 6, duration_s=150, pace_zone="T", pace_str="4:20/km"),
        ]
    }
    desc = build_intervals_workout(day)["description"]
    assert desc == (
        "Rep 6x\n- Interval 1m30s 3:54/km Pace\n- Threshold 2m30s 4:20/km Pace"
    )


def test_back_to_back_sets_stay_separate():
    day = {
        "steps": [
            _step("run", 4, distance_m=400, pace_zone="I", pace_str="4:00/km"),
            _step("recovery", 4, distance_m=200),
            _step("run", 4, distance_m=200, pace_zone="R", pace_str="3:40/km"),
            _step("recovery", 4, distance_m=200),
        ]
    }
    desc = build_intervals_workout(day)["description"]
    assert desc.count("Rep 4x") == 2
    assert desc.index("0.4km") < desc.index("- Fast 0.2km")


def test_two_reps_with_one_recovery_expand_without_header():
    day = {
        "steps": [
            _step("run", 2, distance_m=800, pace_zone="T", pace_str="5:46/km"),
            _step("recovery", 1, duration_s=90, pace_zone="E", effort="jog"),
            _step("cooldown", distance_m=900, pace_zone="E", pace_str="6:26-7:12/km"),
        ]
    }
    lines = build_intervals_workout(day)["description"].split("\n\n")
    assert lines[:3] == [
        "- Threshold 0.8km 5:46/km Pace",
        # A zone-E recovery borrows the runner's own easy range from a sibling.
        "- Recovery 1m30s 6:26/km-7:12/km Pace",
        "- Threshold 0.8km 5:46/km Pace",
    ]


def test_walks_rests_and_hills_carry_no_pace_alarm():
    day = {
        "steps": [
            _step("run", 10, duration_s=30, pace_zone="R", effort="hard uphill"),
            _step("recovery", 10, duration_s=60, pace_zone="WALK", effort="walk"),
            _step("rest", duration_s=480, effort="off the feet"),
        ]
    }
    desc = build_intervals_workout(day)["description"]
    assert "Rep 10x\n- Hill 30s\n- Walk 1m" in desc
    assert "- Rest 8m" in desc
    assert "Pace" not in desc


def test_strides_get_the_jog_back_their_note_prescribes():
    day = {
        "steps": [
            _step("run", distance_m=5000, pace_zone="E", pace_str="6:00/km"),
            _step("strides", 6, distance_m=100, pace_zone="R", pace_str="3:40/km"),
        ]
    }
    desc = build_intervals_workout(day)["description"]
    assert "Rep 5x\n- Stride 0.1km 3:40/km Pace\n- Jog back 1m" in desc
    assert desc.endswith("- Stride 0.1km 3:40/km Pace")


def test_cues_never_contain_digits():
    # Text before the duration is the cue; a digit there could be misread as
    # the step's duration by Intervals.icu.
    from app.core.training.workouts.workout_steps.intervals_export import step_cue

    for zone in ("E", "M", "T", "I", "R", "5K", "10K", "race"):
        assert not any(
            ch.isdigit() for ch in step_cue({"kind": "run", "pace_zone": zone})
        )
