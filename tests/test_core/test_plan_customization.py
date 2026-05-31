"""Tests for structured plan customization (intensity / swap / AI suggestions).

These guard the Area-3 rewrite: customization now routes through the same
builders generation uses, so every customised workout stays internally
consistent (distance == steps == cited description) instead of carrying
hand-written prose that drifts from its structured steps.
"""

import copy
import re

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_adjustments import (
    adjust_intensity,
    apply_ai_suggestions,
    swap_workout,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_steps import _compute_distance_from_steps


@pytest.fixture(scope="module")
def plan_data():
    return TrainingPlanGenerator().generate_plan(40, 21.1, 12, vdot=45.0)


@pytest.fixture(scope="module")
def pace_zones():
    return VDOTCalculator.get_pace_zones(45.0)


def _cited_km(text):
    return [float(m) for m in re.findall(r"(\d+\.\d+)\s*km", text or "")]


def _assert_consistent(wo):
    """A workout's distance, steps and prose must agree."""
    steps = wo.get("steps") or []
    if steps:
        steps_total = _compute_distance_from_steps(steps)
        assert abs((wo.get("distance") or 0) - steps_total) <= 0.2, (
            f"distance {wo.get('distance')} vs steps {steps_total:.2f}"
        )
        step_kms = {
            round((s.get("distance_m") or 0) / 1000.0, 1)
            for s in steps
            if s.get("distance_m")
        }
        resolvable = {round(wo.get("distance") or 0, 1)} | step_kms
        for n in _cited_km(wo.get("description", "")):
            assert any(abs(n - r) <= 0.2 for r in resolvable), (
                f"description cites {n} km not in {sorted(resolvable)}: "
                f"{wo.get('description')}"
            )


def _week(pd, n):
    return next(w for w in pd if w["week"] == n)


def _total_matches(week):
    return (
        abs(
            week["total_km"]
            - round(sum((w.get("distance") or 0) for w in week["daily_workouts"]), 1)
        )
        < 0.01
    )


def test_intensity_low_demotes_quality_to_easy(plan_data, pace_zones):
    wknum = next(
        w["week"]
        for w in plan_data
        for x in w["daily_workouts"]
        if x["type"] in ("tempo", "interval", "hill")
    )
    pd = copy.deepcopy(plan_data)
    adjust_intensity(pd, wknum, "low", pace_zones)
    week = _week(pd, wknum)
    assert not [
        w for w in week["daily_workouts"] if w["type"] in ("tempo", "interval", "hill")
    ]
    for wo in week["daily_workouts"]:
        _assert_consistent(wo)
    assert _total_matches(week)


def test_intensity_high_promotes_easy_to_tempo_with_steps(plan_data, pace_zones):
    wknum = next(
        w["week"]
        for w in plan_data
        for x in w["daily_workouts"]
        if x["type"] == "easy" and (x.get("distance") or 0) > 0
    )
    pd = copy.deepcopy(plan_data)
    adjust_intensity(pd, wknum, "high", pace_zones)
    week = _week(pd, wknum)
    tempos = [w for w in week["daily_workouts"] if w["type"] == "tempo"]
    assert tempos, "expected at least one easy run promoted to tempo"
    for wo in tempos:
        assert wo.get("steps"), "promoted tempo must carry structured steps"
        _assert_consistent(wo)


def test_swap_rest_to_run_seeds_sensible_distance(plan_data, pace_zones):
    # Find a week that has both a rest day and some runs.
    wknum, restday = next(
        (w["week"], d["day"])
        for w in plan_data
        for d in w["daily_workouts"]
        if d["type"] == "rest"
    )
    pd = copy.deepcopy(plan_data)
    swap_workout(pd, wknum, f"{restday},tempo", pace_zones)
    week = _week(pd, wknum)
    swapped = next(w for w in week["daily_workouts"] if w["day"] == restday)
    assert swapped["type"] == "tempo"
    assert swapped["distance"] != 5.0  # not the old hard-coded default
    assert swapped["distance"] > 0
    _assert_consistent(swapped)
    assert _total_matches(week)


def test_swap_to_rest_zeroes_distance(plan_data, pace_zones):
    wknum, runday = next(
        (w["week"], d["day"])
        for w in plan_data
        for d in w["daily_workouts"]
        if d["type"] in ("easy", "tempo", "interval") and (d.get("distance") or 0) > 0
    )
    pd = copy.deepcopy(plan_data)
    swap_workout(pd, wknum, f"{runday},rest", pace_zones)
    week = _week(pd, wknum)
    swapped = next(w for w in week["daily_workouts"] if w["day"] == runday)
    assert swapped["type"] == "rest"
    assert (swapped.get("distance") or 0) == 0
    assert _total_matches(week)


def test_swap_unknown_type_is_noop(plan_data, pace_zones):
    pd = copy.deepcopy(plan_data)
    before = copy.deepcopy(pd)
    swap_workout(pd, 1, "2,not_a_real_type", pace_zones)
    assert pd == before


def test_ai_more_speed_makes_real_interval(plan_data, pace_zones):
    wknum = next(
        w["week"]
        for w in plan_data
        for x in w["daily_workouts"]
        if x["type"] == "easy" and (x.get("distance") or 0) > 0
    )
    pd = copy.deepcopy(plan_data)
    apply_ai_suggestions(pd, wknum, "more_speed", pace_zones)
    week = _week(pd, wknum)
    intervals = [w for w in week["daily_workouts"] if w["type"] == "interval"]
    assert intervals, "more_speed should create an interval session"
    for wo in intervals:
        assert wo.get("steps")
        # No hard-coded prose leaking through.
        assert "6x400m at 5K pace with 400m recovery" not in (wo.get("notes") or "")
        _assert_consistent(wo)
    assert _total_matches(week)


def test_ai_more_endurance_extends_long_consistently(plan_data, pace_zones):
    wknum, before_dist = next(
        (w["week"], d["distance"])
        for w in plan_data
        for d in w["daily_workouts"]
        if d["type"] == "long" and (d.get("distance") or 0) > 0
    )
    pd = copy.deepcopy(plan_data)
    apply_ai_suggestions(pd, wknum, "more_endurance", pace_zones)
    week = _week(pd, wknum)
    long_run = next(w for w in week["daily_workouts"] if w["type"] == "long")
    assert long_run["distance"] > before_dist
    _assert_consistent(long_run)
    assert _total_matches(week)


def test_ai_more_rest_turns_easy_into_rest(plan_data, pace_zones):
    wknum = next(
        w["week"]
        for w in plan_data
        for x in w["daily_workouts"]
        if x["type"] == "easy" and (x.get("distance") or 0) > 0
    )
    pd = copy.deepcopy(plan_data)
    apply_ai_suggestions(pd, wknum, "more_rest", pace_zones)
    week = _week(pd, wknum)
    assert any(w["type"] == "rest" for w in week["daily_workouts"])
    assert _total_matches(week)
