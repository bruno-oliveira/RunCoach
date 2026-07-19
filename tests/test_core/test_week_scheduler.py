"""Tests for week day scheduling: hard-day spacing and slot rotation."""

from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.week_scheduler import schedule_workout_types

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
