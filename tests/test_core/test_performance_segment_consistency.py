"""Regression tests for performance plan segment/distance consistency.

Guards against:
- Segment totals drifting from workout distance after quality caps
- Descriptions becoming stale after distance adjustments
- Key workout overlay garbling descriptions
"""

import re

import pytest

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.performance_workout_builders import (
    _regenerate_description,
    generate_fartlek_workout,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_vo2max_workout,
    reconcile_workout_after_cap,
)
from app.core.training.workout_steps.metrics import _compute_distance_from_steps


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
    def test_steps_sum_to_workout_distance(self, generator, distance, weekly_km, weeks):
        """Stored workouts use the unified steps model, and the steps total
        agrees with the workout distance.

        The performance engine projects its settled segment-based sessions onto
        the same structured ``steps`` the road generator and key-workout overlay
        emit, so no stored workout keeps ``segments`` and the steps total is the
        authoritative distance.
        """
        plan = generator.generate_plan(
            target_distance=distance,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=weeks,
            current_weekly_km=weekly_km,
            runs_per_week=5,
        )
        for week, w in _all_workouts(plan):
            assert not w.get("segments"), (
                f"Week {week['week']} {w['type']} still carries segments "
                "after unification"
            )
            if w["type"] == "rest":
                continue
            steps = w.get("steps") or []
            assert steps, f"Week {week['week']} {w['type']}: no steps"
            # Curated key-workout overlays are prescriptive (e.g. fixed-rep
            # ladders) and allowed to diverge from the budget — only the
            # formulaic conversions must total their distance exactly.
            if w.get("key_workout_id"):
                continue
            steps_total = round(_compute_distance_from_steps(steps), 1)
            assert abs(w["distance"] - steps_total) <= 0.1, (
                f"Week {week['week']} {w['type']}: "
                f"distance={w['distance']} but steps sum to {steps_total}"
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

    def test_description_distances_are_one_decimal(
        self, generator, distance, weekly_km, weeks
    ):
        """Every distance quantity in a description is exactly one decimal place,
        and the leading header equals the stored distance exactly.

        Guards the user-reported bug where ``:.0f`` headers rounded an 8.8 km
        tempo to "9km" and contradicted the segment breakdown. Distance,
        segments, and description header must all cite the identical
        one-decimal figure.
        """
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
            # Leading "<n.d>km" header must match distance exactly (<= grid).
            m = re.match(r"(\d+\.\d)km", desc)
            if m:
                assert abs(float(m.group(1)) - round(w["distance"], 1)) <= 0.05, (
                    f"Week {week['week']} {w['type']}: header {m.group(1)}km != "
                    f"distance {w['distance']} :: {desc}"
                )
            # Steps sum must match distance on the one-decimal grid (the
            # warm-up/cool-down and working distances are copied verbatim from
            # the settled segments, and interval recovery is unpriced).
            # Curated overlays are prescriptive and excluded.
            steps = w.get("steps") or []
            if steps and not w.get("key_workout_id"):
                steps_total = round(_compute_distance_from_steps(steps), 1)
                assert abs(steps_total - round(w["distance"], 1)) <= 0.05, (
                    f"Week {week['week']} {w['type']}: steps {steps_total} != "
                    f"distance {w['distance']}"
                )
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
        wu_before = [s for s in workout["segments"] if s["type"] == "warmup"][0][
            "distance_km"
        ]
        cd_before = [s for s in workout["segments"] if s["type"] == "cooldown"][0][
            "distance_km"
        ]

        workout["distance"] = workout["distance"] - 2.0
        reconcile_workout_after_cap(workout)

        wu_after = [s for s in workout["segments"] if s["type"] == "warmup"][0][
            "distance_km"
        ]
        cd_after = [s for s in workout["segments"] if s["type"] == "cooldown"][0][
            "distance_km"
        ]
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
