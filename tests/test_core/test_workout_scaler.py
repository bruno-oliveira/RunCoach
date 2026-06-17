"""Tests for app.contexts.plan.generators.workout_scaler.

Covers cap-enforcement edge cases that previously lived inline in
weekly_plan_builder and had no direct test coverage:
- is_prescriptive identifies key workouts and tempo/interval/hill builds
- set_distance preserves description/steps alignment for non-prescriptive types
- enforce_long_run_ratio_cap redistributes excess long-run km to easy runs
- scale_down respects the prescriptive invariant
"""

from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_ratio_cap,
    is_prescriptive,
    scale_down,
    set_distance,
)


class TestIsPrescriptive:
    def test_key_workout_is_prescriptive(self):
        assert is_prescriptive({"type": "easy", "key_workout_id": "kw_001"}) is True

    def test_tempo_is_prescriptive(self):
        assert is_prescriptive({"type": "tempo"}) is True

    def test_interval_is_prescriptive(self):
        assert is_prescriptive({"type": "interval"}) is True

    def test_hill_is_prescriptive(self):
        assert is_prescriptive({"type": "hill"}) is True

    def test_easy_is_not_prescriptive(self):
        assert is_prescriptive({"type": "easy"}) is False

    def test_long_is_not_prescriptive(self):
        assert is_prescriptive({"type": "long"}) is False


class TestSetDistance:
    def test_set_distance_on_easy_run_updates_distance(self):
        workout = {"type": "easy", "distance": 5.0, "steps": []}
        set_distance(workout, 6.0)
        assert workout["distance"] == 6.0

    def test_set_distance_rescales_steps_for_easy(self):
        workout = {
            "type": "easy",
            "distance": 5.0,
            "steps": [{"distance_m": 5000, "duration_s": 1800}],
        }
        set_distance(workout, 10.0)
        assert workout["distance"] == 10.0
        assert workout["steps"][0]["distance_m"] == 10000
        assert workout["steps"][0]["duration_s"] == 3600

    def test_set_distance_no_op_when_unchanged(self):
        steps = [{"distance_m": 5000}]
        workout = {"type": "easy", "distance": 5.0, "steps": steps}
        set_distance(workout, 5.0)
        assert workout["steps"][0]["distance_m"] == 5000


class TestScaleDown:
    def test_scale_down_shrinks_easy_when_over_budget(self):
        workouts = [
            {"type": "easy", "distance": 8.0, "steps": []},
            {"type": "easy", "distance": 8.0, "steps": []},
        ]
        new_total = scale_down(workouts, total_km=10.0)
        assert new_total <= 10.1
        assert all(w["distance"] < 8.0 for w in workouts)

    def test_scale_down_leaves_prescriptive_alone(self):
        workouts = [
            {"type": "easy", "distance": 8.0, "steps": []},
            {"type": "tempo", "distance": 8.0, "steps": []},
        ]
        scale_down(workouts, total_km=10.0)
        # Tempo (prescriptive) must keep its 8 km dose.
        tempo = next(w for w in workouts if w["type"] == "tempo")
        assert tempo["distance"] == 8.0

    def test_scale_down_no_op_when_within_budget(self):
        workouts = [{"type": "easy", "distance": 5.0, "steps": []}]
        scale_down(workouts, total_km=10.0)
        assert workouts[0]["distance"] == 5.0


class TestEnforceLongRunRatioCap:
    def test_cap_redistributes_excess_to_easy_runs(self):
        # 4 running days; long is 60% of total which exceeds default 55% cap.
        workouts = [
            {"type": "easy", "distance": 5.0, "steps": []},
            {"type": "easy", "distance": 5.0, "steps": []},
            {"type": "easy", "distance": 5.0, "steps": []},
            {"type": "long", "distance": 30.0, "steps": []},
        ]
        total_before = sum(w["distance"] for w in workouts)
        new_total = enforce_long_run_ratio_cap(workouts, phase="build")
        long_w = next(w for w in workouts if w["type"] == "long")
        assert long_w["distance"] <= total_before * 0.55 + 0.05
        # Total should be preserved (excess redistributed, not deleted).
        assert abs(new_total - total_before) < 0.5

    def test_cap_applies_at_low_frequency(self):
        # Low-frequency plans (2-3 runs) now get the long-run cap too: an
        # uncapped long run absorbs all the volume the week can't place
        # elsewhere, pushing it to 85-90% of the week. With one easy run to
        # receive the excess, the long run is brought back under the ratio.
        workouts = [
            {"type": "easy", "distance": 5.0, "steps": []},
            {"type": "long", "distance": 30.0, "steps": []},
        ]
        total_before = sum(w["distance"] for w in workouts)
        enforce_long_run_ratio_cap(workouts, phase="build", max_runs=2)
        long_w_after = next(w for w in workouts if w["type"] == "long")
        # 2-run weeks are inherently long-run-centric, so the ceiling is looser.
        assert long_w_after["distance"] <= total_before * 0.62 + 0.05

    def test_low_frequency_ratio_looser_than_high_frequency(self):
        # A 2-run week tolerates a bigger long-run share than a 3-run week,
        # which in turn is no looser than the 4+ run default.
        from app.core.training.long_run_calculator import (
            get_weekly_long_run_ratio_cap,
        )

        two = get_weekly_long_run_ratio_cap("build", max_runs=2)
        three = get_weekly_long_run_ratio_cap("build", max_runs=3)
        four = get_weekly_long_run_ratio_cap("build", max_runs=4)
        assert two > three >= four == 0.55

    def test_cap_skipped_when_already_below_ratio(self):
        # Long is 40% of total — well below 55% cap, no change expected.
        workouts = [
            {"type": "easy", "distance": 6.0, "steps": []},
            {"type": "easy", "distance": 6.0, "steps": []},
            {"type": "easy", "distance": 6.0, "steps": []},
            {"type": "long", "distance": 12.0, "steps": []},
        ]
        long_before = next(w for w in workouts if w["type"] == "long")["distance"]
        enforce_long_run_ratio_cap(workouts, phase="build")
        long_after = next(w for w in workouts if w["type"] == "long")["distance"]
        assert long_after == long_before
