"""Regression tests for the LATER tranche of the plan-quality audit.

Covers: strength across generators (G8), fitness race specificity (G9),
beginner C25K rework (G10), per-session pace cues (E2), readiness↔TSB (G7),
the long-run time cap (E7), and the session-hit-rate recalibration (E5).
"""

import json

import pytest

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.fitness_plan_generator import FitnessPlanGenerator
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.workout_scaler import long_run_pace_min_km
from app.contexts.runner.fitness.readiness_scoring import score_taper
from app.core.coaching.coaching_notes_generator import build_pace_cue
from app.core.training import long_run_calculator
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_builders import attach_strength_sessions

# ── G8 — strength across all 4 generators ──────────────────────────────────


def test_attach_strength_sessions_targets_easy_runs():
    workouts = [
        {"day": 1, "type": "easy"},
        {"day": 2, "type": "tempo"},
        {"day": 3, "type": "easy"},
    ]
    attached = attach_strength_sessions(workouts, 5, "build", target_distance=10.0)
    assert len(attached) == 2
    assert workouts[0].get("strength_session")
    assert not workouts[1].get("strength_session")  # tempo skipped
    assert workouts[2].get("strength_session")


def test_attach_strength_sessions_respects_max_sessions():
    workouts = [{"day": d, "type": "run_walk"} for d in (1, 3, 5)]
    attached = attach_strength_sessions(
        workouts, 4, "base", attach_types=("run_walk",), max_sessions=1
    )
    assert len(attached) == 1


def test_performance_generator_attaches_strength():
    plan = PerformancePlanGenerator().generate_plan(
        10.0, 5.0, 4.5, 10, 40, runs_per_week=5
    )
    weeks_with_strength = [
        w for w in plan["weekly_plans"] if w.get("strength_training")
    ]
    assert len(weeks_with_strength) == len(plan["weekly_plans"])


def test_fitness_generator_attaches_strength():
    plan = FitnessPlanGenerator().generate_plan(40, 10, 5, vdot=50)
    assert all(w.get("strength_training") for w in plan["weekly_plans"])


def test_beginner_strength_starts_after_habit_established():
    plan = BeginnerPlanGenerator().generate_plan(5.0, 10, 3)
    # Weeks 1-2 stay strength-free; later weeks get exactly one session.
    assert plan[0]["strength_training"] == []
    assert plan[1]["strength_training"] == []
    assert len(plan[2]["strength_training"]) == 1


# ── G9 — fitness race specificity ──────────────────────────────────────────


def test_fitness_focus_distance_changes_plan():
    g = FitnessPlanGenerator()
    p5 = g.generate_plan(40, 10, 5, vdot=50, focus_area="balanced", focus_distance=5.0)
    p21 = g.generate_plan(
        40, 10, 5, vdot=50, focus_area="balanced", focus_distance=21.1
    )
    assert json.dumps(p5["weekly_plans"]) != json.dumps(p21["weekly_plans"])


def test_fitness_peak_has_race_pace_session():
    plan = FitnessPlanGenerator().generate_plan(
        40, 10, 5, vdot=50, focus_area="balanced", focus_distance=5.0
    )
    race_pace = [
        d
        for w in plan["weekly_plans"]
        if w["phase"] == "peak"
        for d in w["daily_workouts"]
        if d.get("type") == "race_pace"
    ]
    assert race_pace, "peak weeks should include a race-pace session"


# ── G10 — beginner C25K rework ─────────────────────────────────────────────


def test_beginner_distances_are_nonzero_and_differentiated():
    plan = BeginnerPlanGenerator().generate_plan(5.0, 10, 3)
    for week in plan:
        dists = [d["distance"] for d in week["daily_workouts"]]
        assert all(x > 0 for x in dists), "no zero-distance run days"
        assert len(set(dists)) > 1, "the endurance day must differ from standard days"


def test_beginner_weekly_volume_is_monotonic_through_build():
    plan = BeginnerPlanGenerator().generate_plan(10.0, 12, 3)
    prev = 0.0
    for week in plan:
        if week["phase"] == "taper":
            continue
        assert week["total_km"] >= prev - 1e-9, "weekly volume regressed"
        prev = week["total_km"]


# ── E2 — per-session concrete rationale ────────────────────────────────────


def test_pace_cue_uses_vdot_zones():
    zones = VDOTCalculator.get_pace_zones(50)
    easy = build_pace_cue("easy", "build", zones)
    interval = build_pace_cue("interval", "build", zones)
    assert easy and "E-pace" in easy
    assert interval and "I-pace" in interval


def test_pace_cue_none_without_zones():
    assert build_pace_cue("tempo", "peak", None) is None


def test_long_run_peak_cue_mentions_race_pace():
    zones = VDOTCalculator.get_pace_zones(50)
    cue = build_pace_cue("long", "peak", zones)
    assert cue and "M-pace" in cue


# ── G7 — readiness reconciled with TSB ─────────────────────────────────────


def test_score_taper_unchanged_without_tsb():
    score, _ = score_taper(14, 16)  # taper window
    assert score == 95.0


def test_score_taper_penalized_by_fatigue_near_race():
    fresh, _ = score_taper(14, 16, tsb=8.0, tsb_form="fresh")
    fatigued, detail = score_taper(14, 16, tsb=-25.0, tsb_form="fatigued")
    assert fresh > fatigued, "lingering fatigue near the race must lower readiness"
    assert "TSB" in detail


# ── E7 — long-run time cap ─────────────────────────────────────────────────


def test_long_run_time_cap_binds_for_slow_runner():
    pace = 7.1  # min/km, very slow long-run pace
    capped = long_run_calculator.calculate_long_run_distance(
        80, 42.2, 16, 12, "peak", False, "intermediate", long_run_pace_min_km=pace
    )
    assert capped * pace / 60.0 <= long_run_calculator.MAX_LONG_RUN_HOURS + 0.05


def test_long_run_time_cap_skipped_without_pace():
    uncapped = long_run_calculator.calculate_long_run_distance(
        80, 42.2, 16, 12, "peak", False, "intermediate", long_run_pace_min_km=None
    )
    capped = long_run_calculator.calculate_long_run_distance(
        80, 42.2, 16, 12, "peak", False, "intermediate", long_run_pace_min_km=7.1
    )
    assert uncapped > capped


def test_full_plan_long_run_respects_time_cap_for_slow_runner():
    vdot = 32
    plan = TrainingPlanGenerator().generate_plan(60, 42.2, 16, vdot=vdot)
    pace = long_run_pace_min_km(VDOTCalculator.get_pace_zones(vdot))
    longest = max(
        (
            d["distance"]
            for w in plan
            for d in w["daily_workouts"]
            if d["type"] == "long" and not d.get("key_workout_id")
        ),
        default=0,
    )
    assert longest > 0
    assert longest * pace / 60.0 <= long_run_calculator.MAX_LONG_RUN_HOURS + 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
