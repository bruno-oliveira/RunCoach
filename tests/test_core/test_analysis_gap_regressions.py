"""Regression coverage for the two September 2026 generation audits."""

import pytest

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training.profiles.backyard_profile import classify_backyard
from app.core.training.profiles.trail_profile import classify_trail


def _running(week):
    return [
        workout
        for workout in week["daily_workouts"]
        if workout.get("type") not in ("rest", "recovery")
        and (workout.get("distance") or 0) > 0
    ]


def test_unsampled_10k_base_respects_delivered_high_water_ramp():
    plan = TrainingPlanGenerator().generate_plan(15, 10, 8, 5)
    high_water = 15.0
    for week in plan:
        if week.get("is_recovery") or week.get("is_race_week"):
            continue
        assert week["training_km"] <= high_water * 1.12
        high_water = max(high_water, week["training_km"])


def test_short_race_taper_keeps_quality_and_coherent_prerace_runs():
    plan = TrainingPlanGenerator().generate_plan(5, 5, 6, 3)
    taper = [week for week in plan if week["phase"] == "taper"]
    assert any(
        workout["type"] in ("tempo", "interval", "hill")
        for week in taper
        for workout in _running(week)
    )
    prerace = [w for w in _running(plan[-1]) if w["type"] != "race"]
    assert sum(w["distance"] for w in prerace) >= 4.0
    assert all(w["distance"] >= 1.0 for w in prerace)


def test_low_frequency_detraining_is_explicitly_marked():
    generator = TrainingPlanGenerator()
    plan = generator.generate_plan(40, 5, 16, 2)
    adjustments = plan[0]["generation_adjustments"]
    assert adjustments[0]["code"] == "frequency_volume_cap"
    assert adjustments[0]["delivered_peak_km"] < 36


def test_beginner_plan_resolves_frequency_builds_10k_and_ends_on_race():
    generator = BeginnerPlanGenerator()
    plan = generator.generate_plan(10, 12, 5)
    assert generator.last_resolved_runs_per_week == 3
    assert plan[0]["requested_runs_per_week"] == 5
    extension_longs = [
        max(
            (w["distance"] for w in _running(week) if w["type"] == "long"),
            default=0,
        )
        for week in plan
        if week["phase"] in ("build", "peak")
    ]
    assert extension_longs == sorted(extension_longs)
    assert max(extension_longs) >= 8.0
    races = [w for w in _running(plan[-1]) if w["type"] == "race"]
    assert len(races) == 1
    assert races[0]["day"] == 7
    assert races[0]["distance"] == 10


@pytest.mark.parametrize("distance", [5.0, 10.0])
@pytest.mark.parametrize("weeks", [8, 10, 12, 16])
@pytest.mark.parametrize("requested_runs", [3, 4, 5])
def test_beginner_product_matrix_keeps_duration_frequency_and_race(
    distance, weeks, requested_runs
):
    generator = BeginnerPlanGenerator()
    plan = generator.generate_plan(distance, weeks, requested_runs)
    assert len(plan) == weeks
    assert generator.last_resolved_runs_per_week == 3
    assert all(week["resolved_runs_per_week"] == 3 for week in plan)
    assert all(week["requested_runs_per_week"] == requested_runs for week in plan)
    assert any(workout["type"] == "race" for workout in _running(plan[-1]))


def test_frequency_peak_has_no_material_regression_when_adding_days():
    def peak(*args, **kwargs):
        plan = TrainingPlanGenerator().generate_plan(*args, **kwargs)
        return max(
            week["training_km"]
            for week in plan
            if not week.get("is_recovery") and not week.get("is_race_week")
        )

    road = [peak(62.5, 42.2, 16, runs) for runs in range(3, 7)]
    trail_profile = classify_trail(30, 1000)
    trail = [
        peak(15, 30, 12, runs, trail_profile=trail_profile) for runs in range(3, 7)
    ]
    backyard_profile = classify_backyard(48)
    backyard = [
        peak(
            198,
            backyard_profile.equivalent_distance_km,
            24,
            runs,
            backyard_profile=backyard_profile,
        )
        for runs in range(3, 7)
    ]

    # Workout rotation and one-decimal card rounding can move at most a small
    # fraction of one session; the old defect was a 13 km drop at five days.
    for peaks in (road, trail, backyard):
        assert all(
            next_peak >= prior_peak - 2.0
            for prior_peak, next_peak in zip(peaks, peaks[1:])
        )


def test_performance_plan_uses_shared_final_contract():
    plan = PerformancePlanGenerator().generate_plan(10, 6, 5.4, 8, 25, 3)[
        "weekly_plans"
    ]
    assert check_plan_structure(plan) == {"fatal": [], "warnings": []}
    assert all(week["validation"]["status"] == "valid" for week in plan)
    assert any(w["type"] == "race" for w in plan[-1]["daily_workouts"])
    assert plan[-1]["is_race_week"] is True


def test_performance_loading_weeks_obey_delivered_high_water_ramp():
    plan = PerformancePlanGenerator().generate_plan(5, 6, 5.4, 12, 20, 6)[
        "weekly_plans"
    ]
    high_water = 20.0
    for week in plan:
        if week.get("is_recovery") or week.get("is_race_week"):
            continue
        assert week["training_km"] <= high_water * 1.12
        high_water = max(high_water, week["training_km"])


@pytest.mark.parametrize("weeks", [5, 17])
def test_performance_generator_rejects_duration_instead_of_clamping(weeks):
    with pytest.raises(ValueError, match="6-16"):
        PerformancePlanGenerator().generate_plan(10, 6, 5.4, weeks, 25, 4)
