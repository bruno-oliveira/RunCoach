"""Heart rate says how far back a training run was held, within bounds."""

import pytest

from app.core.training.physiology.submaximal_vdot import (
    MAX_HEART_RATE_LIFT,
    MIN_SUBMAXIMAL_RUNS,
    TrainingRun,
    aerobic_vdot,
    heart_rate_vdot,
    intensity_at_heart_rate,
    lifted_for_held_back_training,
)
from app.core.training.physiology.vdot_calculator import VDOTCalculator

LTHR = 160
VDOT = 40.0
ZONES = VDOTCalculator.get_pace_zones(VDOT)
THRESHOLD_PACE = ZONES["T"]["pace_min_km"]
EASY_FAST_PACE = ZONES["E"]["pace_min_km_fast"]
TOP_OF_AEROBIC = round(LTHR * 0.909)


def _run(pace, hr, minutes=40.0, gain=0.0) -> TrainingRun:
    return TrainingRun(pace, hr, minutes, minutes / pace, gain)


class TestIntensity:
    def test_threshold_heart_rate_is_threshold_intensity(self):
        assert intensity_at_heart_rate(LTHR, LTHR) == VDOTCalculator.ZONE_PCT["T"]

    def test_the_aerobic_zone_spans_the_easy_band(self):
        assert intensity_at_heart_rate(LTHR * 0.795, LTHR) == pytest.approx(0.65)
        assert intensity_at_heart_rate(LTHR * 0.909, LTHR) == pytest.approx(0.75)

    def test_it_rises_with_heart_rate_between_the_edges(self):
        low, mid, high = (intensity_at_heart_rate(hr, LTHR) for hr in (130, 140, 150))
        assert low < mid < high

    @pytest.mark.parametrize("hr", [LTHR * 0.7, LTHR + 1, LTHR * 1.2])
    def test_there_is_no_reading_outside_aerobic_to_threshold(self, hr):
        assert intensity_at_heart_rate(hr, LTHR) is None


class TestOneRun:
    def test_a_threshold_run_shows_the_runner_s_vdot(self):
        reading = heart_rate_vdot(_run(THRESHOLD_PACE, LTHR, minutes=30), LTHR)
        assert reading == pytest.approx(VDOT, abs=0.5)

    def test_so_does_a_jog_at_the_top_of_the_aerobic_zone(self):
        reading = heart_rate_vdot(_run(EASY_FAST_PACE, TOP_OF_AEROBIC), LTHR)
        assert reading == pytest.approx(VDOT, abs=0.5)

    def test_the_same_jog_scored_as_a_race_is_far_lower(self):
        raw = VDOTCalculator.calculate_vdot(40.0 / EASY_FAST_PACE, 40 * 60)
        assert raw < VDOT - 5

    def test_a_reading_is_never_below_the_race_score(self):
        """Three hours at threshold heart rate is drift, not a held-back effort."""
        run = _run(6.5, LTHR, minutes=180)
        raw = VDOTCalculator.calculate_vdot(run.distance_km, 180 * 60)
        assert heart_rate_vdot(run, LTHR) == pytest.approx(raw, abs=0.2)

    @pytest.mark.parametrize(
        "run",
        [
            _run(6.0, 140, minutes=15),  # heart rate still catching up
            _run(6.0, 140, gain=400.0),  # the hill set the pace
            _run(6.0, None),
            TrainingRun(None, 140, 40.0, 6.6, 0.0),
            TrainingRun(6.0, 140, 40.0, None, 0.0),
            TrainingRun(6.0, 140, None, 6.6, 0.0),
            _run(5.0, LTHR + 8),  # above threshold: no reading
        ],
    )
    def test_runs_that_cannot_be_read_give_nothing(self, run):
        assert heart_rate_vdot(run, LTHR) is None


class TestAcrossRuns:
    def test_is_the_median_not_the_best(self):
        runs = [_run(pace, 140) for pace in (6.4, 6.2, 6.0, 5.8, 5.0)]
        middle = heart_rate_vdot(_run(6.0, 140), LTHR)
        assert aerobic_vdot(runs, LTHR) == round(middle, 1)

    def test_is_withheld_below_the_minimum(self):
        runs = [_run(6.0, 140)] * (MIN_SUBMAXIMAL_RUNS - 1)
        assert aerobic_vdot(runs, LTHR) is None

    def test_is_withheld_without_a_threshold_heart_rate(self):
        assert aerobic_vdot([_run(6.0, 140)] * 10, None) is None


class TestLift:
    def test_raises_the_estimate_to_the_heart_rate_reading(self):
        assert lifted_for_held_back_training(36.0, 38.5) == 38.5

    def test_never_lowers_what_pace_has_shown(self):
        assert lifted_for_held_back_training(40.0, 37.0) == 40.0

    def test_is_capped(self):
        assert lifted_for_held_back_training(31.0, 40.0) == 31.0 + MAX_HEART_RATE_LIFT

    def test_no_reading_leaves_the_estimate(self):
        assert lifted_for_held_back_training(36.0, None) == 36.0

    def test_nothing_shown_in_pace_means_no_estimate(self):
        assert lifted_for_held_back_training(None, 40.0) is None
