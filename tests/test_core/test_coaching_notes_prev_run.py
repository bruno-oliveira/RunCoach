"""Tests for P2 §5.3 — generate_coaching_note prev_run prefix."""

from types import SimpleNamespace

from app.core.coaching.coaching_notes_generator import generate_coaching_note


def _run(workout_type, perceived_effort):
    return SimpleNamespace(workout_type=workout_type, perceived_effort=perceived_effort)


class TestPrevRunPrefix:
    def test_no_prev_run_returns_unchanged(self):
        original = generate_coaching_note("easy", "build", 4, 21.1)
        with_prev = generate_coaching_note("easy", "build", 4, 21.1, prev_run=None)
        assert original == with_prev

    def test_hard_tempo_yesterday_adds_prefix(self):
        note = generate_coaching_note(
            "easy", "build", 4, 21.1, prev_run=_run("tempo", 8)
        )
        assert note.startswith("After yesterday's hard tempo,")

    def test_hard_interval_yesterday_adds_prefix(self):
        note = generate_coaching_note(
            "easy", "build", 4, 21.1, prev_run=_run("interval", 9)
        )
        assert note.startswith("After yesterday's hard interval,")

    def test_long_run_yesterday_adds_prefix(self):
        note = generate_coaching_note(
            "easy", "build", 4, 21.1, prev_run=_run("long", 7)
        )
        assert note.startswith("After yesterday's long run,")

    def test_easy_with_low_effort_adds_controlled_prefix(self):
        note = generate_coaching_note(
            "tempo", "build", 4, 21.1, prev_run=_run("easy", 3)
        )
        assert note.startswith("Yesterday was easy and well-controlled —")

    def test_easy_with_high_effort_no_prefix(self):
        baseline = generate_coaching_note("tempo", "build", 4, 21.1)
        prefixed = generate_coaching_note(
            "tempo", "build", 4, 21.1, prev_run=_run("easy", 8)
        )
        assert baseline == prefixed

    def test_low_effort_tempo_no_prefix(self):
        baseline = generate_coaching_note("easy", "build", 4, 21.1)
        prefixed = generate_coaching_note(
            "easy", "build", 4, 21.1, prev_run=_run("tempo", 4)
        )
        assert baseline == prefixed
