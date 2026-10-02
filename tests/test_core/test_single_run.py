"""Pure-logic tests for standalone workout building and its watch event."""

from datetime import date

import pytest

from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.watch_mirror import (
    build_single_run_event,
    owns_event,
    single_run_external_id,
)
from app.core.training.workouts.single_run import (
    SINGLE_RUN_TYPES,
    build_single_run,
    distance_for_duration,
    estimated_minutes,
    is_similar_distance,
    max_distance_km,
    min_distance_km,
    single_run_family,
)

ZONES = VDOTCalculator.get_pace_zones(45.0)


@pytest.mark.parametrize("run_type", SINGLE_RUN_TYPES)
def test_builds_each_type_with_paced_steps(run_type):
    workout = build_single_run(run_type, 9.0, ZONES, weekly_km=30)

    assert workout["type"] == run_type
    assert workout["steps"]
    assert workout["key_workout_name"]
    # A single run has no week, so the plan-grid position must not leak out.
    assert "day" not in workout
    assert workout["distance"] == pytest.approx(9.0, abs=1.0)
    assert estimated_minutes(workout)


def test_quality_sessions_have_a_warmup_and_cooldown():
    for run_type in ("tempo", "interval"):
        kinds = [s["kind"] for s in build_single_run(run_type, 8.0, ZONES, 30)["steps"]]
        assert kinds[0] == "warmup" and kinds[-1] == "cooldown"


def test_tempo_cites_threshold_pace_from_the_runners_zones():
    workout = build_single_run("tempo", 8.0, ZONES, 30)
    assert ZONES["T"]["pace_str"] in workout["description"]


@pytest.mark.parametrize("run_type", SINGLE_RUN_TYPES)
def test_rejects_distances_outside_the_types_range(run_type):
    with pytest.raises(ValueError):
        build_single_run(run_type, min_distance_km(run_type) - 0.5, ZONES, 30)
    with pytest.raises(ValueError):
        build_single_run(run_type, max_distance_km(run_type) + 0.5, ZONES, 30)


def test_quality_ceiling_is_tighter_than_the_aerobic_one():
    # A plan never hands out a 15 km threshold block; neither does this.
    assert max_distance_km("tempo") < max_distance_km("long")
    assert max_distance_km("interval") < max_distance_km("easy")


def test_unknown_type_is_rejected():
    with pytest.raises(ValueError):
        build_single_run("fartlek", 8.0, ZONES, 30)


def test_without_fitness_the_session_is_by_effort_and_claims_no_duration():
    workout = build_single_run("tempo", 6.0, None, weekly_km=0)

    assert workout["steps"]
    assert "/km" not in workout["description"]
    assert estimated_minutes(workout) is None


@pytest.mark.parametrize("run_type", ["easy", "tempo", "interval"])
def test_duration_resolves_to_a_session_of_about_that_length(run_type):
    distance = distance_for_duration(run_type, 45, ZONES, weekly_km=30)
    took = estimated_minutes(build_single_run(run_type, distance, ZONES, 30))

    assert took == pytest.approx(45, abs=3)


def test_duration_too_short_for_the_type_is_rejected():
    with pytest.raises(ValueError, match="long run"):
        distance_for_duration("long", 20, ZONES, weekly_km=30)


def test_event_is_dated_directly_and_namespaced():
    workout = build_single_run("interval", 8.0, ZONES, 30)
    event = build_single_run_event("abc", date(2026, 10, 3), workout)

    assert event["start_date_local"] == "2026-10-03T00:00:00"
    assert event["external_id"] == single_run_external_id("abc") == "runcoach-single-abc"
    assert event["category"] == "WORKOUT" and event["type"] == "Run"
    assert event["name"] == "Intervals"
    assert event["moving_time"] > 0


def test_no_plan_reconcile_can_claim_a_single_run_event():
    # The safety property: a plan mirror deletes only what `owns_event` admits.
    external_id = single_run_external_id("3f2c9a52-0000-4000-8000-000000000000")
    assert not owns_event("3f2c9a52-0000-4000-8000-000000000000", external_id)
    assert not owns_event("some-other-plan", external_id)


@pytest.mark.parametrize(
    "workout_type, family",
    [
        ("recovery", "easy"),
        ("medium_long", "long"),
        ("cruise_interval", "tempo"),
        ("vo2max", "interval"),
        ("hill", None),
        ("race", None),
        (None, None),
    ],
)
def test_workout_types_fold_onto_single_run_families(workout_type, family):
    assert single_run_family(workout_type) == family


def test_every_single_run_type_is_its_own_family():
    assert all(single_run_family(t) == t for t in SINGLE_RUN_TYPES)


def test_similar_distance_scales_with_the_session_and_has_a_floor():
    assert is_similar_distance(10.0, 13.9)
    assert not is_similar_distance(10.0, 14.5)
    # 40% of 3 km is 1.2 km; the floor keeps a short session forgiving.
    assert is_similar_distance(3.0, 4.5)
    assert not is_similar_distance(6.0, 21.0)
