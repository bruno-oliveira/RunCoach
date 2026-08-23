"""The simulation ladder: where loop rehearsals land and how big they get.

The scheduler's contract is that simulations are spaced, never land on a
deload, climb monotonically, and finish on a dress rehearsal pinned to the
last loading week before the taper — while the week's own volume keeps the
final veto over how many loops it can actually carry.
"""

import pytest

from app.core.training import phase_calculator
from app.core.training.backyard_profile import classify_backyard
from app.core.training.backyard_simulation import (
    _SIM_SPACING_WEEKS,
    LoopSimulation,
    build_simulation_schedule,
    fit_simulation_to_week,
    peak_simulation_loops,
    weekly_backyard_focus,
)


def _schedule(loops, weeks, distance_km=160.9):
    profile = classify_backyard(loops)
    phases = phase_calculator.calculate_phases(weeks, distance_km)
    return build_simulation_schedule(weeks, phases, profile), phases


class TestSchedulePlacement:
    def test_no_simulation_lands_on_a_deload(self):
        schedule, phases = _schedule(24, 20)
        deloads = phase_calculator.recovery_week_set(phases)
        assert schedule
        assert not (set(schedule) & deloads)

    def test_no_simulation_lands_in_the_taper(self):
        schedule, phases = _schedule(24, 20)
        last_loading = phases["base"] + phases["build"] + phases["peak"]
        assert max(schedule) <= last_loading

    def test_dress_rehearsal_is_the_last_loading_week(self):
        schedule, phases = _schedule(24, 20)
        last_loading = phases["base"] + phases["build"] + phases["peak"]
        assert schedule[max(schedule)].role == "dress_rehearsal"
        assert max(schedule) == last_loading

    def test_simulations_are_spaced_apart(self):
        schedule, _ = _schedule(36, 28)
        weeks = sorted(schedule)
        gaps = [b - a for a, b in zip(weeks, weeks[1:])]
        assert all(gap >= _SIM_SPACING_WEEKS for gap in gaps)

    def test_exactly_one_dress_rehearsal(self):
        schedule, _ = _schedule(36, 28)
        roles = [s.role for s in schedule.values()]
        assert roles.count("dress_rehearsal") == 1

    @pytest.mark.parametrize("weeks", range(8, 41))
    def test_every_plan_length_produces_a_valid_schedule(self, weeks):
        schedule, phases = _schedule(24, weeks)
        deloads = phase_calculator.recovery_week_set(phases)
        assert not (set(schedule) & deloads)
        assert all(1 <= w <= weeks for w in schedule)


class TestLadderProgression:
    def test_loops_never_decrease(self):
        schedule, _ = _schedule(36, 28)
        loops = [schedule[w].loops for w in sorted(schedule)]
        assert loops == sorted(loops)

    def test_the_biggest_simulation_is_the_dress_rehearsal(self):
        schedule, _ = _schedule(24, 20)
        biggest = max(schedule.values(), key=lambda s: s.loops)
        assert biggest.role == "dress_rehearsal"

    def test_peak_rehearsal_is_a_fraction_of_the_goal_never_the_goal(self):
        for loops in (10, 14, 24, 36, 48):
            profile = classify_backyard(loops)
            assert peak_simulation_loops(profile) < loops

    def test_ambitious_goals_rehearse_a_smaller_share(self):
        share = lambda y: peak_simulation_loops(classify_backyard(y)) / y  # noqa: E731
        assert share(10) > share(24) > share(48)

    def test_rehearsal_is_capped_so_it_stays_training(self):
        assert peak_simulation_loops(classify_backyard(48)) <= 12


class TestNightRehearsal:
    def test_goals_that_cross_darkness_get_an_evening_simulation(self):
        schedule, _ = _schedule(24, 20)
        assert any(s.start_time == "evening" for s in schedule.values())
        assert any(s.role == "night" for s in schedule.values())

    def test_daylight_goals_never_schedule_a_night_run(self):
        schedule, _ = _schedule(8, 12, distance_km=53.6)
        assert all(s.role != "night" for s in schedule.values())
        assert all(s.start_time == "morning" for s in schedule.values())

    def test_a_full_night_goal_rehearses_overnight_on_the_dress_rehearsal(self):
        schedule, _ = _schedule(24, 20)
        assert schedule[max(schedule)].is_overnight


class TestFittingToTheWeek:
    def _sim(self, loops):
        return LoopSimulation(
            week_number=10,
            loops=loops,
            loop_km=6.706,
            role="progression",
            start_time="morning",
        )

    def test_a_week_that_can_afford_it_keeps_every_loop(self):
        sim = self._sim(4)
        assert fit_simulation_to_week(sim, 120.0) is sim

    def test_a_small_week_drops_rungs_rather_than_blowing_the_budget(self):
        fitted = fit_simulation_to_week(self._sim(8), 50.0)
        assert fitted is not None
        assert fitted.loops < 8
        assert fitted.distance_km <= 50.0 * 0.55 + 0.05

    def test_a_dress_rehearsal_is_allowed_to_be_the_week(self):
        big = LoopSimulation(10, 8, 6.706, "dress_rehearsal", "morning")
        ordinary = LoopSimulation(10, 8, 6.706, "progression", "morning")
        assert (
            fit_simulation_to_week(big, 60.0).loops
            > fit_simulation_to_week(ordinary, 60.0).loops
        )

    def test_a_week_too_small_for_two_loops_gets_no_simulation(self):
        assert fit_simulation_to_week(self._sim(6), 15.0) is None

    def test_fitting_preserves_role_and_start_time(self):
        fitted = fit_simulation_to_week(
            LoopSimulation(10, 9, 6.706, "night", "evening"), 60.0
        )
        assert fitted.role == "night"
        assert fitted.start_time == "evening"


class TestWeeklyFocus:
    def test_focus_is_always_enabled_on_a_backyard_week(self):
        block = weekly_backyard_focus("base", False, classify_backyard(24))
        assert block["enabled"] is True
        assert block["simulation"] is None
        assert block["target_loops"] == 24

    def test_deload_weeks_say_deload_whatever_the_phase(self):
        block = weekly_backyard_focus("peak", True, classify_backyard(24))
        assert "Deload" in str(block["focus"])

    def test_a_simulation_week_carries_its_session(self):
        sim = LoopSimulation(12, 6, 6.706, "night", "evening")
        block = weekly_backyard_focus("peak", False, classify_backyard(24), sim)
        assert block["simulation"]["loops"] == 6
        assert block["simulation"]["overnight"] is True
        assert block["simulation"]["elapsed_hours"] == 6

    def test_pace_and_budget_are_rendered_for_display(self):
        block = weekly_backyard_focus("build", False, classify_backyard(24))
        assert block["loop_pace_str"].endswith("/km")
        assert block["loop_budget_min"] + block["turnaround_min"] == 60
