"""Regression tests for performance plan segment/distance consistency.

Guards against:
- Segment totals drifting from workout distance after quality caps
- Descriptions becoming stale after distance adjustments
- Key workout overlay garbling descriptions
"""

import re

import pytest

from app.contexts.plan.generators.performance_plan_generator import PerformancePlanGenerator
from app.contexts.plan.generators.performance_workout_builders import (
    _regenerate_description,
    generate_fartlek_workout,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_vo2max_workout,
    reconcile_workout_after_cap,
)


@pytest.fixture
def generator():
    return PerformancePlanGenerator()


@pytest.fixture
def zones(generator):
    return generator.calculate_training_zones(5.0)


def _all_workouts(plan):
    for week in plan["weekly_plans"]:
        for w in week["daily_workouts"]:
            yield week, w


# ---- Segment-distance agreement across full plans ----


@pytest.mark.parametrize(
    "distance,weekly_km,weeks",
    [
        (5.0, 25, 8),
        (10.0, 30, 8),
        (21.1, 45, 10),
        (42.2, 50, 12),
    ],
    ids=["5K", "10K", "half", "marathon"],
)
class TestSegmentDistanceConsistency:

    def test_segments_sum_to_workout_distance(self, generator, distance, weekly_km, weeks):
        plan = generator.generate_plan(
            target_distance=distance,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=weeks,
            current_weekly_km=weekly_km,
            runs_per_week=5,
        )
        for week, w in _all_workouts(plan):
            segments = w.get("segments", [])
            if not segments:
                continue
            seg_total = round(sum(s["distance_km"] for s in segments), 1)
            assert abs(w["distance"] - seg_total) < 0.2, (
                f"Week {week['week']} {w['type']}: "
                f"distance={w['distance']} but segments sum to {seg_total}"
            )

    def test_description_matches_distance(self, generator, distance, weekly_km, weeks):
        """Description's leading distance should agree with workout distance."""
        plan = generator.generate_plan(
            target_distance=distance,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=weeks,
            current_weekly_km=weekly_km,
            runs_per_week=5,
        )
        for week, w in _all_workouts(plan):
            if w["type"] in ("rest", "easy"):
                continue
            desc = w.get("description", "")
            m = re.match(r"(\d+(?:\.\d+)?)\s*km", desc)
            if not m:
                continue
            desc_km = float(m.group(1))
            assert abs(desc_km - w["distance"]) <= 1.0, (
                f"Week {week['week']} {w['type']}: "
                f"description says {desc_km}km but distance is {w['distance']}"
            )

    def test_no_garbled_descriptions(self, generator, distance, weekly_km, weeks):
        """Descriptions must not contain duplicated warmup/cooldown phrases."""
        plan = generator.generate_plan(
            target_distance=distance,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=weeks,
            current_weekly_km=weekly_km,
            runs_per_week=5,
        )
        for week, w in _all_workouts(plan):
            desc = w.get("description", "")
            assert "Warm up" not in desc or desc.count("Warm up") <= 1, (
                f"Week {week['week']} {w['type']}: duplicated warmup in '{desc}'"
            )
            assert "Cool down" not in desc or desc.count("Cool down") <= 1, (
                f"Week {week['week']} {w['type']}: duplicated cooldown in '{desc}'"
            )


# ---- reconcile_workout_after_cap unit tests ----


class TestReconcileAfterCap:

    def test_reduces_main_segment_when_capped(self, zones):
        workout = generate_tempo_workout(zones, 40, 3, "build")
        original_segs = sum(s["distance_km"] for s in workout["segments"])
        workout["distance"] = original_segs - 3.0
        reconcile_workout_after_cap(workout)

        seg_total = round(sum(s["distance_km"] for s in workout["segments"]), 1)
        assert abs(workout["distance"] - seg_total) < 0.2

    def test_warmup_cooldown_preserved(self, zones):
        workout = generate_tempo_workout(zones, 40, 3, "build")
        wu_before = [s for s in workout["segments"] if s["type"] == "warmup"][0]["distance_km"]
        cd_before = [s for s in workout["segments"] if s["type"] == "cooldown"][0]["distance_km"]

        workout["distance"] = workout["distance"] - 2.0
        reconcile_workout_after_cap(workout)

        wu_after = [s for s in workout["segments"] if s["type"] == "warmup"][0]["distance_km"]
        cd_after = [s for s in workout["segments"] if s["type"] == "cooldown"][0]["distance_km"]
        assert wu_after == wu_before
        assert cd_after == cd_before

    def test_interval_reps_adjusted(self, zones):
        workout = generate_vo2max_workout(zones, 40, 3, "build")
        main = [s for s in workout["segments"] if s["type"] == "main"][0]
        original_reps = main["intervals"]["reps"]

        workout["distance"] = workout["distance"] - 3.0
        reconcile_workout_after_cap(workout)

        main_after = [s for s in workout["segments"] if s["type"] == "main"][0]
        assert main_after["intervals"]["reps"] <= original_reps

    def test_no_change_when_already_consistent(self, zones):
        workout = generate_tempo_workout(zones, 30, 1, "base")
        desc_before = workout["description"]
        segs_before = [s["distance_km"] for s in workout["segments"]]

        reconcile_workout_after_cap(workout)

        assert workout["description"] == desc_before
        assert [s["distance_km"] for s in workout["segments"]] == segs_before

    def test_description_rebuilt_after_cap(self, zones):
        workout = generate_race_pace_workout(zones, 40, 3, "peak")
        workout["distance"] = workout["distance"] - 2.0
        reconcile_workout_after_cap(workout)

        assert "warmup" in workout["description"]
        assert "cooldown" in workout["description"]
        desc_km = float(re.match(r"(\d+)", workout["description"]).group(1))
        assert abs(desc_km - workout["distance"]) <= 1.0


# ---- _regenerate_description unit tests ----


class TestRegenerateDescription:

    def test_tempo_description_format(self, zones):
        workout = generate_tempo_workout(zones, 30, 1, "base")
        workout["description"] = "garbled text"
        _regenerate_description(workout)

        assert "tempo" in workout["description"]
        assert "warmup" in workout["description"]
        assert "cooldown" in workout["description"]

    def test_vo2max_description_has_reps(self, zones):
        workout = generate_vo2max_workout(zones, 30, 1, "build")
        workout["description"] = "garbled text"
        _regenerate_description(workout)

        assert "intervals" in workout["description"]
        assert re.search(r"\dx\d+m", workout["description"])

    def test_race_pace_description_format(self, zones):
        workout = generate_race_pace_workout(zones, 30, 1, "peak")
        workout["description"] = "garbled text"
        _regenerate_description(workout)

        assert "race pace" in workout["description"]

    def test_fartlek_description_has_surges(self, zones):
        workout = generate_fartlek_workout(zones, 30, 1, "build")
        workout["description"] = "garbled text"
        _regenerate_description(workout)

        assert "fartlek" in workout["description"]
        assert "surges" in workout["description"]

    def test_skips_unknown_type(self, zones):
        workout = {"type": "unknown", "distance": 5, "segments": []}
        _regenerate_description(workout)
        assert "type" in workout
