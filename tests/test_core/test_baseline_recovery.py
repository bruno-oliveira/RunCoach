"""Tests for the pure baseline-recovery helpers."""

from app.core.training.baseline_recovery import (
    parse_adjustment_multiplier,
    recover_baseline,
    strip_annotations,
)


class TestParseAdjustmentMultiplier:
    def test_parses_single_multiplier(self):
        assert parse_adjustment_multiplier("Easy run (Adjusted: x1.15)") == 1.15

    def test_returns_none_without_annotation(self):
        assert parse_adjustment_multiplier("Easy run") is None
        assert parse_adjustment_multiplier(None) is None
        assert parse_adjustment_multiplier("") is None

    def test_ignores_non_adjusted_annotations(self):
        # "Adapted"/"Recalibrated" do not carry a recoverable multiplier.
        assert parse_adjustment_multiplier("(Adapted: shorter)") is None
        assert parse_adjustment_multiplier("(Recalibrated: VDOT 50)") is None

    def test_multiplies_stacked_annotations(self):
        result = parse_adjustment_multiplier("(Adjusted: x1.1) (Adjusted: x1.2)")
        assert result == round(1.1 * 1.2, 10)


class TestRecoverBaseline:
    def test_recovers_corrupted_baseline(self):
        # baseline frozen to the already-adjusted distance + lingering note.
        true_baseline, true_distance, recovered = recover_baseline(
            9.2, 9.2, "Easy run (Adjusted: x1.15)"
        )
        assert recovered is True
        assert true_baseline == 8.0
        assert true_distance == 8.0

    def test_leaves_genuine_adjustment_untouched(self):
        # A real adaptation diverges baseline from distance.
        baseline, distance, recovered = recover_baseline(
            9.2, 8.0, "Easy run (Adjusted: x1.15)"
        )
        assert recovered is False
        assert (baseline, distance) == (8.0, 9.2)

    def test_no_change_when_note_has_no_multiplier(self):
        baseline, distance, recovered = recover_baseline(9.2, 9.2, "Easy run")
        assert recovered is False
        assert (baseline, distance) == (9.2, 9.2)

    def test_handles_missing_values(self):
        assert recover_baseline(None, 5.0, "(Adjusted: x1.1)") == (5.0, None, False)
        assert recover_baseline(5.0, None, "(Adjusted: x1.1)") == (None, 5.0, False)
        assert recover_baseline(0, 0, "(Adjusted: x1.1)") == (0, 0, False)


class TestStripAnnotations:
    def test_strips_and_returns_none_when_empty(self):
        assert strip_annotations("(Adjusted: x1.15)") is None

    def test_preserves_real_note(self):
        assert strip_annotations("Easy run (Adjusted: x1.15)") == "Easy run"

    def test_passthrough_when_no_annotation(self):
        assert strip_annotations("Easy run") == "Easy run"
        assert strip_annotations(None) is None
