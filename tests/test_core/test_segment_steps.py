"""Unit tests for the segment -> steps projection used to unify the engines."""

from app.contexts.plan.generators.segment_steps import (
    apply_steps_model,
    segments_to_steps,
)


def _warmup_seg():
    return {
        "name": "Warm-up",
        "distance_km": 2.0,
        "pace_formatted": "6:00/km",
        "pace_raw": 6.0,
        "zone": "zone_1",
        "zone_label": "Zone 1",
        "type": "warmup",
    }


def _cooldown_seg():
    return {**_warmup_seg(), "name": "Cool-down", "type": "cooldown"}


def test_plain_tempo_segments_become_steps():
    workout = {
        "type": "tempo",
        "distance": 9.0,
        "segments": [
            _warmup_seg(),
            {
                "name": "Tempo",
                "distance_km": 5.0,
                "pace_formatted": "4:59/km",
                "pace_raw": 4.98,
                "zone": "zone_3",
                "zone_label": "Zone 3",
                "type": "main",
            },
            _cooldown_seg(),
        ],
    }
    segments_to_steps(workout)

    assert "segments" not in workout
    steps = workout["steps"]
    assert [s["kind"] for s in steps] == ["warmup", "run", "cooldown"]
    main = steps[1]
    assert main["label"] == "Tempo"
    assert main["pace_zone"] == "T"
    assert main["pace_str"] == "4:59/km"
    assert main["distance_m"] == 5000


def test_vo2max_intervals_split_into_work_and_recovery():
    workout = {
        "type": "vo2max",
        "distance": 8.0,
        "segments": [
            _warmup_seg(),
            {
                "name": "Intervals",
                "distance_km": 4.0,
                "pace_formatted": "4:20/km",
                "pace_raw": 4.33,
                "zone": "zone_4",
                "zone_label": "Zone 4",
                "type": "main",
                "intervals": {"reps": 5, "interval_m": 800, "recovery_min": 2},
            },
            _cooldown_seg(),
        ],
    }
    segments_to_steps(workout)
    steps = workout["steps"]

    work = next(s for s in steps if s["kind"] == "run")
    assert work["label"] == "5 × 800 m"
    assert work["distance_m"] == 800
    assert work["repeat"] == 5
    assert work["pace_zone"] == "I"

    recovery = next(s for s in steps if s["kind"] == "recovery")
    assert recovery["duration_s"] == 120
    assert recovery["distance_m"] is None  # unpriced — not part of the budget
    assert recovery["repeat"] == 4


def test_fartlek_surges_become_single_working_step():
    workout = {
        "type": "fartlek",
        "distance": 10.0,
        "segments": [
            _warmup_seg(),
            {
                "name": "Fartlek",
                "distance_km": 6.0,
                "pace_formatted": "5:20/km - 4:50/km",
                "pace_raw": 5.0,
                "zone": "mixed",
                "zone_label": "Mixed Zones",
                "type": "main",
                "intervals": {
                    "reps": 8,
                    "interval_m": "1-3min surges",
                    "recovery_min": None,
                },
            },
            _cooldown_seg(),
        ],
    }
    segments_to_steps(workout)
    steps = workout["steps"]

    surge = steps[1]
    assert surge["label"] == "8 × 1-3min surges"
    assert surge["distance_m"] == 6000
    assert surge["pace_str"] == "5:20/km - 4:50/km"
    assert surge["pace_zone"] is None  # "mixed" carries no single zone letter


def test_already_stepped_workout_is_untouched():
    existing = [{"kind": "run", "label": "keep me", "distance_m": 5000}]
    workout = {"type": "interval", "steps": list(existing), "segments": [_warmup_seg()]}
    segments_to_steps(workout)
    # An overlay already installed steps; the segments are left as-is and the
    # steps are not rebuilt.
    assert workout["steps"] == existing


def _race_pace_workout():
    return {
        "type": "race_pace",
        "distance": 7.0,
        "segments": [
            _warmup_seg(),
            {
                "name": "Race Pace",
                "distance_km": 3.0,
                "pace_formatted": "4:00/km",
                "pace_raw": 4.0,
                "zone": "zone_5",
                "zone_label": "Zone 5",
                "type": "main",
            },
            _cooldown_seg(),
        ],
    }


def test_race_pace_badge_scales_with_goal_distance():
    cases = {5.0: "5K", 10.0: "10K", 21.1: "T", 42.2: "M"}
    for target, expected in cases.items():
        wo = _race_pace_workout()
        segments_to_steps(wo, target_distance=target)
        main = next(s for s in wo["steps"] if s["label"] == "Race Pace")
        assert main["pace_zone"] == expected, (
            f"goal {target}km -> {main['pace_zone']}, expected {expected}"
        )


def test_race_pace_badge_defaults_to_marathon_when_unknown():
    wo = _race_pace_workout()
    segments_to_steps(wo)  # no target distance
    main = next(s for s in wo["steps"] if s["label"] == "Race Pace")
    assert main["pace_zone"] == "M"


def test_rest_day_without_segments_is_noop():
    workout = {"type": "rest", "distance": 0}
    segments_to_steps(workout)
    assert "steps" not in workout


def test_apply_steps_model_converts_whole_week():
    week = [
        {"type": "rest", "distance": 0},
        {
            "type": "easy",
            "distance": 6.0,
            "segments": [
                {
                    "name": "Easy Run",
                    "distance_km": 6.0,
                    "pace_formatted": "6:30/km",
                    "pace_raw": 6.5,
                    "zone": "zone_1",
                    "zone_label": "Zone 1",
                    "type": "main",
                }
            ],
        },
    ]
    apply_steps_model(week)
    assert "segments" not in week[1]
    assert week[1]["steps"][0]["kind"] == "run"
    assert week[1]["steps"][0]["pace_zone"] == "E"
