"""Tests for the pure recognition helper (app/core/coaching/recognition).

Covers the guaranteed-accurate chips and the deterministic fallback note that
backs the Coach's Note when the AI voice is unavailable.
"""

from app.core.coaching.recognition import build_fallback_note, build_recognition


def _facts(**over):
    base = {
        "training_age": {
            "current_streak_weeks": 7,
            "longest_streak_weeks": 7,
            "weeks_since_first_run": 24,
            "total_runs": 76,
        },
        "today": {
            "available": True,
            "phase": "build",
            "workout_type": "tempo",
            "distance_km": 8.0,
            "is_rest": False,
            "done_this_week": 3,
            "due_this_week": 3,
        },
        "journey": {"vdot_now": 48.0, "vdot_start": 44.0, "vdot_trend": "improving"},
        "stance": {},
        "week_pulse": None,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------
# build_recognition — chips are computed, accurate, conditional
# --------------------------------------------------------------------------


def test_recognition_chips_full():
    rec = build_recognition(_facts())
    chips = rec["chips"]
    assert any("7-week streak" in c for c in chips)
    assert "(your best)" in chips[0]  # streak == longest >= 3
    assert any(c == "3/3 sessions this week" for c in chips)
    assert any("24 weeks training" in c for c in chips)
    assert any(c == "VDOT 44→48" for c in chips)
    # raw fields surface alongside the chips
    assert rec["streak_weeks"] == 7
    assert rec["vdot_now"] == 48.0


def test_recognition_no_streak_chip_below_two_weeks():
    rec = build_recognition(_facts(training_age={"current_streak_weeks": 1}))
    assert not any("streak" in c for c in rec["chips"])


def test_recognition_no_vdot_chip_when_delta_negligible():
    rec = build_recognition(
        _facts(journey={"vdot_now": 44.2, "vdot_start": 44.0, "vdot_trend": "stable"})
    )
    assert not any("VDOT" in c for c in rec["chips"])


def test_recognition_empty_facts_no_chips():
    rec = build_recognition({})
    assert rec["chips"] == []
    assert rec["streak_weeks"] == 0


def test_recognition_falls_back_to_total_runs_when_new():
    rec = build_recognition(
        _facts(
            training_age={
                "current_streak_weeks": 0,
                "weeks_since_first_run": 1,
                "total_runs": 6,
            }
        )
    )
    assert any("6 runs logged" in c for c in rec["chips"])
    assert not any("weeks training" in c for c in rec["chips"])


# --------------------------------------------------------------------------
# build_fallback_note — recognition-first, grounded, robust to missing data
# --------------------------------------------------------------------------


def test_fallback_note_leads_with_streak():
    note = build_fallback_note(_facts())
    assert note.startswith("You've put together 7 straight weeks")
    assert "44" in note and "48" in note  # journey delta woven in
    assert "tempo" in note  # today framed
    assert 1 <= note.count(".") <= 4


def test_fallback_note_rest_day():
    note = build_fallback_note(
        _facts(today={"available": True, "is_rest": True, "workout_type": "rest"})
    )
    assert "rest day" in note.lower()


def test_fallback_note_empty_facts_is_safe():
    note = build_fallback_note({})
    assert note  # never empty
    assert "consistency" in note.lower()


def test_fallback_note_uses_week_pulse_when_nothing_else():
    note = build_fallback_note(
        {
            "training_age": {},
            "today": {"available": False},
            "journey": {},
            "week_pulse": "Strong week so far — keep going!",
        }
    )
    assert note == "Strong week so far — keep going!"
