"""Deriving a VDOT from a stated race result: the implausible-input branch.

`compute_vdot_from_time` fed the plan generator whatever `VDOTCalculator`
returned, and that calculator deliberately returns `None` for a physically
implausible pace (a typo, or a distance/time mismatch). The return type said
`tuple[float, float]`, so the `None` was invisible until the model layer was
typed and pyright could see through it — the runner would have got a whole
training block paced off a fallback, with nothing saying why.
"""

import pytest

from app.schemas.plan_config import compute_vdot_from_time


class TestValidInput:
    def test_derives_vdot_and_pace(self):
        vdot, pace_min_km = compute_vdot_from_time(5.0, "22:30")

        assert vdot > 0
        assert pace_min_km == pytest.approx(22.5 / 5.0)

    def test_accepts_hh_mm_ss(self):
        vdot, pace_min_km = compute_vdot_from_time(21.1, "1:45:30")

        assert vdot > 0
        assert pace_min_km == pytest.approx(105.5 / 21.1, rel=1e-6)


class TestUnparseableTime:
    def test_rejects_garbage(self):
        with pytest.raises(ValueError, match="Could not parse"):
            compute_vdot_from_time(5.0, "not a time")

    def test_names_the_field_in_the_message(self):
        with pytest.raises(ValueError, match="recent_race_time"):
            compute_vdot_from_time(5.0, "nonsense", "recent_race_time")

    def test_rejects_zero_time(self):
        with pytest.raises(ValueError, match="Could not parse"):
            compute_vdot_from_time(5.0, "0:00")


class TestImplausiblePace:
    def test_raises_instead_of_returning_a_null_fitness_estimate(self):
        """30 seconds for a 5K is ~0.1 min/km: bad data, not a fitness level."""
        with pytest.raises(ValueError, match="not physically plausible"):
            compute_vdot_from_time(5.0, "0:30")

    def test_the_message_names_the_distance_and_the_field(self):
        with pytest.raises(ValueError) as exc:
            compute_vdot_from_time(10.0, "0:30", "goal_time")

        message = str(exc.value)
        assert "goal_time" in message
        assert "10" in message

    def test_never_returns_none_for_either_tuple_slot(self):
        """The declared contract is (float, float) — pin it."""
        for distance, time_str in [
            (5.0, "22:30"),
            (42.2, "3:30:00"),
            (21.1, "1:20:00"),
        ]:
            vdot, pace = compute_vdot_from_time(distance, time_str)

            assert isinstance(vdot, float) and vdot is not None
            assert isinstance(pace, float) and pace is not None
