"""The easy band is the runner's own easy pace, not a slice of their VDOT."""

import copy

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.physiology.personal_easy_band import (
    EASY_BAND_HALF_WIDTH,
    MIN_EASY_RUNS,
    EasyRunSample,
    easy_pace_moved,
    has_personal_easy_band,
    is_easy_run,
    personal_easy_pace,
    personal_easy_range,
    with_personal_easy_band,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator

CEILING = 141


def _run(pace=6.3, hr=136, km=8.0, gain=20.0) -> EasyRunSample:
    return EasyRunSample(pace, hr, km, gain)


class TestWhichRunsCount:
    def test_a_flat_run_under_the_ceiling_counts(self):
        assert is_easy_run(_run(), CEILING)

    def test_a_run_at_the_ceiling_still_counts(self):
        assert is_easy_run(_run(hr=CEILING), CEILING)

    @pytest.mark.parametrize(
        "sample",
        [
            _run(hr=CEILING + 1),  # steady, not easy
            _run(hr=None),  # nothing to judge the effort by
            _run(km=2.0),  # a shakeout
            _run(km=8.0, gain=400.0),  # hills slow the pace, not the effort
            _run(pace=None),
            _run(pace=0.0),
        ],
    )
    def test_everything_else_is_left_out(self, sample):
        assert not is_easy_run(sample, CEILING)


class TestMeasuredPace:
    def test_is_the_median_of_the_easy_runs(self):
        runs = [_run(pace=p) for p in (6.2, 6.3, 6.4, 6.5, 9.0)]
        assert personal_easy_pace(runs, CEILING) == 6.4

    def test_ignores_runs_that_were_not_easy(self):
        easy = [_run(pace=6.3)] * MIN_EASY_RUNS
        hard = [_run(pace=5.0, hr=165)] * 10
        assert personal_easy_pace(easy + hard, CEILING) == 6.3

    def test_is_withheld_below_the_minimum(self):
        assert personal_easy_pace([_run()] * (MIN_EASY_RUNS - 1), CEILING) is None

    def test_is_withheld_without_a_heart_rate_ceiling(self):
        assert personal_easy_pace([_run()] * 10, None) is None


class TestBand:
    def test_is_fifteen_seconds_either_side(self):
        assert personal_easy_range(6.0, None) == (6.25, 5.75)

    def test_stays_clear_of_threshold(self):
        slow, fast = personal_easy_range(6.32, 6.07)
        assert slow == 6.57
        assert fast == pytest.approx(6.07 + 10 / 60, abs=0.01)

    def test_is_withheld_when_the_measured_pace_is_at_threshold(self):
        assert personal_easy_range(6.0, 6.0) is None

    @pytest.mark.parametrize("pace", [None, 0.0])
    def test_is_withheld_without_a_pace(self, pace):
        assert personal_easy_range(pace, 5.0) is None


class TestZones:
    def test_only_the_easy_zone_moves(self):
        zones = VDOTCalculator.get_pace_zones(45)
        personal = with_personal_easy_band(zones, 6.0)
        assert personal["E"]["pace_min_km_slow"] == 6.25
        assert personal["E"]["pace_min_km_fast"] == 5.75
        assert personal["E"]["pace_str"] == "6:15/km–5:45/km"
        assert has_personal_easy_band(personal)
        for key in zones:
            if key != "E":
                assert personal[key] == zones[key]

    def test_easy_and_long_runs_share_the_band_and_recovery_sits_below(self):
        subs = with_personal_easy_band(VDOTCalculator.get_pace_zones(45), 6.0)["E"][
            "sub_zones"
        ]
        assert subs["easy"]["pace_str"] == subs["long_run"]["pace_str"]
        assert subs["recovery"]["pace_min_km_fast"] == 6.25
        assert subs["recovery"]["pace_min_km_slow"] == 6.75

    def test_the_input_is_not_mutated(self):
        zones = VDOTCalculator.get_pace_zones(45)
        before = copy.deepcopy(zones)
        with_personal_easy_band(zones, 6.0)
        assert zones == before

    def test_no_measured_pace_leaves_the_vdot_band(self):
        zones = VDOTCalculator.get_pace_zones(45)
        assert with_personal_easy_band(zones, None) is zones
        assert not has_personal_easy_band(zones)

    def test_an_incoherent_pace_leaves_the_vdot_band(self):
        zones = VDOTCalculator.get_pace_zones(45)
        threshold = zones["T"]["pace_min_km"]
        assert with_personal_easy_band(zones, threshold) is zones

    def test_no_zones_stays_no_zones(self):
        assert with_personal_easy_band(None, 6.0) is None


class TestDeadBand:
    def test_a_first_measurement_always_applies(self):
        assert easy_pace_moved(None, 6.3)

    def test_a_lost_measurement_never_clears_the_band(self):
        assert not easy_pace_moved(6.3, None)

    def test_a_few_seconds_is_noise(self):
        assert not easy_pace_moved(6.30, 6.30 - 4 / 60)

    def test_five_seconds_is_a_move(self):
        assert easy_pace_moved(6.30, 6.30 - 5 / 60)
        assert easy_pace_moved(6.30, 6.30 + 5 / 60)


class TestGeneratedPlan:
    """The band reaches every easy-paced step, and nothing else."""

    @staticmethod
    def _steps(plan):
        return [
            (step["kind"], step["pace_zone"], step["pace_str"], week["week"])
            for week in plan
            for workout in week["daily_workouts"]
            for step in workout.get("steps") or []
        ]

    def test_easy_steps_carry_the_band_and_quality_paces_are_untouched(self):
        args = (40, 21.1, 12, 4)
        vdot_only = self._steps(TrainingPlanGenerator().generate_plan(*args, vdot=45))
        personal = self._steps(
            TrainingPlanGenerator().generate_plan(*args, vdot=45, easy_pace_min_km=6.0)
        )
        easy = {
            pace
            for kind, zone, pace, _ in personal
            if (kind, zone) != ("recovery", "E") and zone == "E"
        }
        assert easy == {"6:15/km–5:45/km"}
        assert [s for s in personal if s[1] != "E"] == [
            s for s in vdot_only if s[1] != "E"
        ]

    @pytest.mark.parametrize("easy_pace, jog", [(6.0, "6:45/km–6:15/km"), (None, None)])
    def test_a_jog_between_reps_is_slower_than_the_easy_band(self, easy_pace, jog):
        """Recovering between hard efforts is not an easy run."""
        plan = TrainingPlanGenerator().generate_plan(
            40, 21.1, 12, 4, vdot=45, easy_pace_min_km=easy_pace
        )
        zones = with_personal_easy_band(VDOTCalculator.get_pace_zones(45), easy_pace)
        expected = jog or zones["E"]["sub_zones"]["recovery"]["pace_str"]
        jogs = {
            pace
            for kind, zone, pace, _ in self._steps(plan)
            if (kind, zone) == ("recovery", "E")
        }
        assert jogs == {expected}
        assert expected != zones["E"]["pace_str"]

    def test_the_band_width_is_the_documented_one(self):
        assert EASY_BAND_HALF_WIDTH * 60 == 15


class TestJogOnTheWatch:
    """A stored jog with no pace of its own borrows, and jogs slower."""

    def test_an_open_jog_targets_the_stretch_past_the_easy_band(self):
        from app.core.training.workouts.workout_steps.intervals_export import (
            resolve_pace_bounds,
            zone_paces_of,
        )

        warmup = {"kind": "warmup", "pace_zone": "E", "pace_str": "6:15/km–5:45/km"}
        jog = {"kind": "recovery", "pace_zone": "E", "pace_str": None}
        zone_paces = zone_paces_of([warmup, jog])

        assert resolve_pace_bounds(warmup, zone_paces) == [6.25, 5.75]
        assert resolve_pace_bounds(jog, zone_paces) == [6.75, 6.25]

    def test_a_jog_s_own_pace_never_speaks_for_the_easy_zone(self):
        from app.core.training.workouts.workout_steps.intervals_export import (
            zone_paces_of,
        )

        jog = {"kind": "recovery", "pace_zone": "E", "pace_str": "6:45/km–6:15/km"}
        run = {"kind": "run", "pace_zone": "E", "pace_str": "6:15/km–5:45/km"}
        assert zone_paces_of([jog, run]) == {"E": "6:15/km–5:45/km"}
