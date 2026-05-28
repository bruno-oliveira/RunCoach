"""Tests for the threshold-ladder verdict helper."""

from app.core.coaching.verdict import verdict_from_thresholds


class TestLowerIsBetter:
    """Default ladder: value <= threshold, ascending best→worst."""

    def test_boundaries_are_inclusive(self):
        # thresholds (5, 15, 30) -> on_track/close/behind/far_behind
        assert verdict_from_thresholds(5, (5, 15, 30)) == "on_track"
        assert verdict_from_thresholds(5.1, (5, 15, 30)) == "close"
        assert verdict_from_thresholds(15, (5, 15, 30)) == "close"
        assert verdict_from_thresholds(15.1, (5, 15, 30)) == "behind"
        assert verdict_from_thresholds(30, (5, 15, 30)) == "behind"
        assert verdict_from_thresholds(30.1, (5, 15, 30)) == "far_behind"

    def test_zero_and_negative_are_best(self):
        assert verdict_from_thresholds(0, (5, 15, 30)) == "on_track"
        assert verdict_from_thresholds(-3, (5, 15, 30)) == "on_track"


class TestHigherIsBetter:
    """Descending ladder: value >= threshold."""

    def test_completion_rate_ladder(self):
        labels = ("on_track", "close", "needs_attention", "far_behind")
        thresholds = (85, 70, 50)
        assert (
            verdict_from_thresholds(85, thresholds, labels, higher_is_better=True)
            == "on_track"
        )
        assert (
            verdict_from_thresholds(84, thresholds, labels, higher_is_better=True)
            == "close"
        )
        assert (
            verdict_from_thresholds(70, thresholds, labels, higher_is_better=True)
            == "close"
        )
        assert (
            verdict_from_thresholds(50, thresholds, labels, higher_is_better=True)
            == "needs_attention"
        )
        assert (
            verdict_from_thresholds(49, thresholds, labels, higher_is_better=True)
            == "far_behind"
        )
