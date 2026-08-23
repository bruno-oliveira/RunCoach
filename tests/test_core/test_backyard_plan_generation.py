"""End-to-end backyard plan generation.

The load-bearing claims: a backyard plan carries loop simulations sized in
whole loops, those loops survive every week-budget pass unshrunk, the plan
closes on the goal loop count rather than on a distance, and none of it leaks
into an ordinary trail plan.
"""

import pytest

from app.contexts.plan.generators.plan_generator import (
    BACKYARD_RACE_DAY_NUMBER,
    TrainingPlanGenerator,
)
from app.core.training.backyard_profile import classify_backyard
from app.core.training.key_workout_library import (
    _BACKYARD_ONLY_IDS,
    KeyWorkoutLibrary,
)
from app.core.training.trail_profile import classify_trail
from app.core.training.workout_steps import _compute_distance_from_steps


def _build(loops, current_km, weeks, runs=5, loop_elev=0.0, vdot=45):
    profile = classify_backyard(loops, loop_elevation_gain_m=loop_elev)
    plan = TrainingPlanGenerator().generate_plan(
        current_km=current_km,
        target_distance=profile.equivalent_distance_km,
        weeks=weeks,
        max_runs_per_week=runs,
        vdot=vdot,
        backyard_profile=profile,
    )
    return profile, plan


def _simulations(plan):
    return [
        w
        for week in plan
        for w in week["daily_workouts"]
        if w.get("backyard_simulation")
    ]


class TestSimulationsAreInstalled:
    def test_a_plan_carries_multiple_simulations(self):
        _, plan = _build(24, 70, 20)
        assert len(_simulations(plan)) >= 3

    def test_every_simulation_is_a_whole_number_of_loops(self):
        profile, plan = _build(24, 70, 20)
        for sim in _simulations(plan):
            loops = sim["backyard_simulation"]["loops"]
            assert sim["distance"] == pytest.approx(loops * profile.loop_km, abs=0.05)

    def test_simulation_steps_price_out_to_the_stated_distance(self):
        _, plan = _build(24, 70, 20)
        for sim in _simulations(plan):
            assert _compute_distance_from_steps(sim["steps"]) == pytest.approx(
                sim["distance"], abs=0.1
            )

    def test_a_simulation_has_one_turnaround_fewer_than_it_has_loops(self):
        """The session ends when the runner stops, not with a rest."""
        _, plan = _build(24, 70, 20)
        for sim in _simulations(plan):
            loops = sim["backyard_simulation"]["loops"]
            runs = [s for s in sim["steps"] if s["kind"] == "run"]
            rests = [s for s in sim["steps"] if s["kind"] == "rest"]
            assert len(runs) == loops
            assert len(rests) == loops - 1

    def test_turnarounds_cost_the_session_no_distance(self):
        _, plan = _build(24, 70, 20)
        for sim in _simulations(plan):
            for step in sim["steps"]:
                if step["kind"] == "rest":
                    assert step["distance_m"] is None
                    assert step["pace_zone"] is None

    def test_simulations_climb_across_the_plan(self):
        _, plan = _build(24, 70, 20)
        loops = [s["backyard_simulation"]["loops"] for s in _simulations(plan)]
        assert loops == sorted(loops)
        assert loops[-1] > loops[0]

    def test_no_simulation_lands_on_a_deload(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            if week["is_recovery"]:
                assert not any(
                    w.get("backyard_simulation") for w in week["daily_workouts"]
                )


class TestSimulationsSurviveTheBudgetPasses:
    """A loop is indivisible; no scaling pass may shave one."""

    def test_simulations_are_marked_fixed_structure_and_prescriptive(self):
        _, plan = _build(24, 70, 20)
        for sim in _simulations(plan):
            assert sim["fixed_structure"] is True
            assert sim["key_workout_id"] in _BACKYARD_ONLY_IDS

    def test_simulation_distance_stays_a_loop_multiple_even_on_a_lean_plan(self):
        """A tight weekly budget drops rungs; it never produces half a loop."""
        profile, plan = _build(12, 42, 14, runs=4)
        sims = _simulations(plan)
        assert sims
        for sim in sims:
            ratio = sim["distance"] / profile.loop_km
            assert ratio == pytest.approx(round(ratio), abs=0.02)

    def test_the_dress_rehearsal_is_allowed_to_dominate_its_week(self):
        _, plan = _build(24, 70, 20)
        rehearsal = next(
            w
            for week in plan
            for w in week["daily_workouts"]
            if (w.get("backyard_simulation") or {}).get("role") == "dress_rehearsal"
        )
        week = next(wk for wk in plan if rehearsal in wk["daily_workouts"])
        assert rehearsal["distance"] / week["total_km"] > 0.4

    def test_a_simulation_is_never_smaller_than_the_long_run_it_replaced(self):
        """The loop format is the gentler way to cover the same distance."""
        _, plan = _build(24, 70, 20)
        typical_long = max(
            (w.get("distance") or 0)
            for week in plan
            if not week["is_recovery"] and week["phase"] in ("base", "build")
            for w in week["daily_workouts"]
            if w["type"] == "long" and not w.get("backyard_simulation")
        )
        first_sim = _simulations(plan)[0]
        assert first_sim["distance"] >= typical_long * 0.9


class TestTheWeekendShape:
    def test_a_daylight_simulation_is_followed_by_a_second_day_or_rest(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            sims = [w for w in week["daily_workouts"] if w.get("backyard_simulation")]
            if not sims or sims[0]["backyard_simulation"]["start_time"] != "morning":
                continue
            sunday = next(w for w in week["daily_workouts"] if w["day"] == 7)
            assert sunday["type"] == "rest" or (
                sunday.get("key_workout_id") == "backyard_b2b_day2"
            )

    def test_an_overnight_simulation_is_followed_by_rest(self):
        """The runner is asleep, not adding a session."""
        _, plan = _build(24, 70, 20)
        found = False
        for week in plan:
            sims = [w for w in week["daily_workouts"] if w.get("backyard_simulation")]
            if sims and sims[0]["backyard_simulation"]["start_time"] == "evening":
                found = True
                sunday = next(w for w in week["daily_workouts"] if w["day"] == 7)
                assert sunday["type"] == "rest"
        assert found

    def test_every_week_still_has_seven_days(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            assert sorted(w["day"] for w in week["daily_workouts"]) == [
                1,
                2,
                3,
                4,
                5,
                6,
                7,
            ]


class TestBackyardSpecificQuality:
    def test_a_plan_installs_the_specific_midweek_sessions(self):
        _, plan = _build(36, 85, 28)
        installed = {
            w["key_workout_id"]
            for week in plan
            for w in week["daily_workouts"]
            if w.get("key_workout_id") in _BACKYARD_ONLY_IDS
        }
        assert "backyard_loop_repeats" in installed
        assert "backyard_turnaround_drill" in installed

    def test_interval_work_survives_the_specific_sessions(self):
        """Loop pace sits under an aerobic ceiling somebody has to build."""
        _, plan = _build(36, 85, 28)
        generic_quality = [
            w
            for week in plan
            for w in week["daily_workouts"]
            if w["type"] == "interval"
            and w.get("key_workout_id") not in _BACKYARD_ONLY_IDS
        ]
        assert len(generic_quality) >= 3

    def test_every_installed_id_resolves_in_the_catalog(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            for w in week["daily_workouts"]:
                kid = w.get("key_workout_id")
                if kid in _BACKYARD_ONLY_IDS:
                    assert KeyWorkoutLibrary.get_by_id(kid) is not None


class TestRaceDay:
    def test_the_plan_ends_on_the_goal_loop_count(self):
        profile, plan = _build(24, 70, 20)
        race = next(w for w in plan[-1]["daily_workouts"] if w.get("is_race"))
        assert race["day"] == BACKYARD_RACE_DAY_NUMBER
        assert race["distance"] == pytest.approx(profile.total_distance_km, abs=0.1)
        assert "24" in race["key_workout_name"]

    def test_race_day_is_saturday_so_the_race_can_run_into_sunday(self):
        _, plan = _build(24, 70, 20)
        final = plan[-1]
        assert final["is_race_week"] is True
        sunday = next(w for w in final["daily_workouts"] if w["day"] == 7)
        assert sunday["type"] == "rest"

    def test_race_week_is_a_taper_apart_from_the_race(self):
        _, plan = _build(24, 70, 20)
        final = plan[-1]
        non_race = sum(
            w.get("distance", 0) or 0
            for w in final["daily_workouts"]
            if not w.get("is_race")
        )
        peak = max(w["total_km"] for w in plan[:-1] if not w["is_recovery"])
        assert non_race < peak * 0.5

    def test_race_steps_price_out_to_the_full_loop_count(self):
        """The race is compressed into a repeat block; it must still add up."""
        profile, plan = _build(24, 70, 20)
        race = next(w for w in plan[-1]["daily_workouts"] if w.get("is_race"))
        assert _compute_distance_from_steps(race["steps"]) == pytest.approx(
            profile.total_distance_km, abs=0.1
        )

    def test_race_day_is_never_rescaled_by_the_week(self):
        _, plan = _build(24, 70, 20)
        race = next(w for w in plan[-1]["daily_workouts"] if w.get("is_race"))
        assert race["fixed_structure"] is True

    def test_a_forty_eight_loop_race_shows_the_real_total_not_the_projection(self):
        """The projection is clamped at 163 km; the race is not."""
        profile, plan = _build(48, 90, 36)
        race = next(w for w in plan[-1]["daily_workouts"] if w.get("is_race"))
        assert race["distance"] > profile.equivalent_distance_km
        assert race["distance"] == pytest.approx(profile.total_distance_km, abs=0.1)


class TestNoLeakIntoOtherPlans:
    def test_a_plain_trail_plan_gets_no_backyard_sessions(self):
        plan = TrainingPlanGenerator().generate_plan(
            current_km=70,
            target_distance=160.9,
            weeks=20,
            max_runs_per_week=5,
            vdot=45,
            trail_profile=classify_trail(160.9, 1440.0),
        )
        for week in plan:
            assert week.get("backyard") is None
            for w in week["daily_workouts"]:
                assert w.get("key_workout_id") not in _BACKYARD_ONLY_IDS
                assert not w.get("backyard_simulation")

    def test_a_road_plan_gets_no_backyard_sessions(self):
        plan = TrainingPlanGenerator().generate_plan(
            current_km=40, target_distance=42.2, weeks=16, max_runs_per_week=5, vdot=45
        )
        for week in plan:
            assert week.get("backyard") is None
            for w in week["daily_workouts"]:
                assert w.get("key_workout_id") not in _BACKYARD_ONLY_IDS

    def test_backyard_sessions_never_enter_the_rotation(self):
        for phase in ("base", "build", "peak", "taper"):
            for wtype in ("interval", "tempo", "hill", "long"):
                picked = KeyWorkoutLibrary.ordered_candidates(
                    160.9,
                    phase,
                    0,
                    wtype,
                    trail_profile=classify_trail(160.9, 1440.0),
                )
                assert all(w["id"] not in _BACKYARD_ONLY_IDS for w in picked)


class TestWeeklyBackyardBlock:
    def test_every_week_carries_the_operating_instructions(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            block = week["backyard"]
            assert block["enabled"] is True
            assert block["target_loops"] == 24
            assert block["loop_budget_min"] + block["turnaround_min"] == 60

    def test_simulation_weeks_surface_their_session_in_the_block(self):
        _, plan = _build(24, 70, 20)
        for week in plan:
            has_sim = any(w.get("backyard_simulation") for w in week["daily_workouts"])
            assert bool(week["backyard"]["simulation"]) == has_sim


class TestPlanShapes:
    @pytest.mark.parametrize(
        "loops,current_km,weeks,runs",
        [
            (8, 30, 10, 3),
            (12, 45, 14, 4),
            (24, 70, 20, 5),
            (36, 90, 28, 5),
            (48, 120, 36, 6),
        ],
    )
    def test_every_supported_goal_shape_generates(self, loops, current_km, weeks, runs):
        profile, plan = _build(loops, current_km, weeks, runs=runs)
        assert len(plan) == weeks
        assert _simulations(plan)
        race = next(w for w in plan[-1]["daily_workouts"] if w.get("is_race"))
        assert race["distance"] == pytest.approx(profile.total_distance_km, abs=0.1)

    def test_a_hilly_loop_still_generates_and_keeps_its_gradient(self):
        profile, plan = _build(24, 75, 20, loop_elev=200.0)
        assert profile.elevation_class in ("hilly", "mountainous")
        assert _simulations(plan)
        assert plan[0]["backyard"]["flat_equivalent_pace_str"].endswith("/km")
