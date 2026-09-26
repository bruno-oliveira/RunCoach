"""Tests for week day scheduling: hard-day spacing and slot rotation."""

import pytest

from app.core.training.frequency import get_composer
from app.core.training.periodization.week_scheduler import (
    schedule_from_composer,
    schedule_workout_types,
)
from app.core.training.workouts.key_workout_library import KeyWorkoutLibrary

_QUALITY = ("interval", "tempo", "hill")


def _base_distribution(**overrides):
    dist = {"easy": 2, "long": 1, "interval": 0, "tempo": 0, "hill": 0, "rest": 1}
    dist.update(overrides)
    return dist


class TestQualityDaySpacing:
    def test_two_quality_sessions_are_not_on_consecutive_days(self):
        types = schedule_workout_types(
            _base_distribution(interval=1, tempo=1),
            phase="build",
            week_number=7,
            is_recovery_week=False,
        )
        quality_days = [i for i, t in enumerate(types) if t in _QUALITY]
        assert len(quality_days) == 2
        assert quality_days[1] - quality_days[0] >= 2, (
            f"quality sessions on adjacent days: {types}"
        )

    def test_no_quality_on_the_day_before_the_long_run(self):
        types = schedule_workout_types(
            _base_distribution(interval=1, tempo=1),
            phase="peak",
            week_number=9,
            is_recovery_week=False,
        )
        long_day = types.index("long")
        assert types[long_day - 1] not in _QUALITY, (
            f"hard day immediately before the long run: {types}"
        )

    def test_single_quality_session_sits_mid_week(self):
        types = schedule_workout_types(
            _base_distribution(easy=3, tempo=1),
            phase="build",
            week_number=5,
            is_recovery_week=False,
        )
        assert types[3] == "tempo"

    def test_recovery_week_schedules_no_quality(self):
        types = schedule_workout_types(
            _base_distribution(easy=4),
            phase="build",
            week_number=4,
            is_recovery_week=True,
        )
        assert not any(t in _QUALITY for t in types)


def _composer_week(runs, phase, quality=None, recovery_week=False):
    return schedule_from_composer(
        get_composer(runs), phase, quality or {}, recovery_week
    )


def _running_days(types):
    return {i for i, t in enumerate(types) if t not in ("rest", "recovery")}


def _longest_streak(days):
    """Longest run of consecutive days, wrapping Sunday into Monday."""
    best = 0
    for start in days:
        length = 0
        while length < 7 and (start + length) % 7 in days:
            length += 1
        best = max(best, length)
    return best


_COMPOSER_WEEKS = [
    (runs, phase, quality)
    for runs in (2, 3, 4, 5, 6)
    for phase in ("base", "build", "peak")
    for quality in ({}, {"interval": 1}, {"interval": 1, "tempo": 1})
]


class TestComposerDaySpacing:
    """The composer path decides which weekday each slot lands on."""

    def test_four_runs_are_not_bunched_at_the_start_of_the_week(self):
        # Regression: the fixed fill order ran Mon/Tue/Wed, then rested
        # until the Saturday long run.
        types = _composer_week(4, "base")
        assert _running_days(types) == {0, 2, 3, 5}, types

    def test_four_run_quality_week_keeps_an_easy_day_between_hard_ones(self):
        types = _composer_week(4, "build", {"interval": 1})
        assert types[0] == "interval" and types[5] == "long", types
        assert types[1] == "rest", types
        assert _longest_streak(_running_days(types)) <= 2, types

    @pytest.mark.parametrize("runs,phase,quality", _COMPOSER_WEEKS)
    def test_nothing_hard_the_day_before_the_long_run(self, runs, phase, quality):
        types = _composer_week(runs, phase, quality)
        assert types[4] not in ("medium_long",) + _QUALITY, types

    @pytest.mark.parametrize("runs,phase,quality", _COMPOSER_WEEKS)
    def test_running_day_count_matches_frequency(self, runs, phase, quality):
        types = _composer_week(runs, phase, quality)
        assert len(_running_days(types)) == runs, types

    @pytest.mark.parametrize("runs", (2, 3, 4, 5))
    def test_no_more_than_three_running_days_in_a_row(self, runs):
        for phase in ("base", "build", "peak"):
            types = _composer_week(runs, phase, {"interval": 1, "tempo": 1})
            assert _longest_streak(_running_days(types)) <= 3, (runs, phase, types)


class TestSameTypeSlotRotation:
    def test_second_same_type_slot_selects_a_different_session(self):
        """Marathon peak grants {"tempo": 2}; the two slots must differ."""
        first = KeyWorkoutLibrary.get_for_phase(
            42.2, "peak", week_in_phase=0, workout_type="tempo", slot_index=0
        )
        second = KeyWorkoutLibrary.get_for_phase(
            42.2, "peak", week_in_phase=0, workout_type="tempo", slot_index=1
        )
        assert first is not None and second is not None
        assert first["id"] != second["id"]

    def test_slot_index_defaults_keep_selection_reproducible(self):
        a = KeyWorkoutLibrary.get_for_phase(
            21.1, "build", week_in_phase=2, workout_type="interval"
        )
        b = KeyWorkoutLibrary.get_for_phase(
            21.1, "build", week_in_phase=2, workout_type="interval"
        )
        assert a is not None
        assert a["id"] == b["id"]
