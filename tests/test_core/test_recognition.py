"""Tests for the pure recognition/purpose/focus helpers (core/coaching/recognition).

Covers the accurate chips (lifetime journey + plan-week framing, kept as distinct
scopes), today's purpose line, the signal-driven focus selector, and the
deterministic 3-beat fallback note.
"""

from app.core.coaching.recognition import (
    build_fallback_note,
    build_recognition,
    select_today_focus,
    today_purpose_line,
)


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
            "current_week": 6,
            "total_weeks": 12,
            "workout_type": "tempo",
            "distance_km": 8.0,
            "hr_zone_target": 4,
            "is_rest": False,
        },
        "journey": {"vdot_now": 48.0, "vdot_start": 44.0, "vdot_trend": "improving"},
        "focus": None,
        "week_pulse": None,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------
# build_recognition — lifetime journey + plan-week framing, never a mixed ratio
# --------------------------------------------------------------------------


def test_recognition_chips_full():
    chips = build_recognition(_facts())["chips"]
    assert any("7-week streak" in c for c in chips)
    assert "(your best)" in chips[0]
    assert any("24 weeks training" in c for c in chips)
    assert any(c == "VDOT 44→48" for c in chips)
    assert any(c == "Week 6 of 12" for c in chips)
    # The old plan/lifetime-mixing ratio is gone.
    assert not any("sessions this week" in c for c in chips)


def test_recognition_week_chip_requires_both_bounds():
    chips = build_recognition(
        _facts(today={"available": True, "current_week": 6, "total_weeks": None})
    )["chips"]
    assert not any(c.startswith("Week ") for c in chips)


def test_recognition_no_vdot_chip_when_delta_negligible():
    chips = build_recognition(_facts(journey={"vdot_now": 44.2, "vdot_start": 44.0}))[
        "chips"
    ]
    assert not any("VDOT" in c for c in chips)


def test_recognition_new_runner_uses_total_runs():
    chips = build_recognition(
        _facts(
            training_age={
                "current_streak_weeks": 0,
                "weeks_since_first_run": 1,
                "total_runs": 6,
            }
        )
    )["chips"]
    assert any("6 runs logged" in c for c in chips)
    assert not any("weeks training" in c for c in chips)


def test_recognition_empty_facts_no_chips():
    assert build_recognition({})["chips"] == []


# --------------------------------------------------------------------------
# today_purpose_line — what today builds + how to run it
# --------------------------------------------------------------------------


def test_purpose_tempo_with_zone():
    line = today_purpose_line(_facts()["today"])
    assert "lactate-threshold" in line
    assert "Zone 4" in line


def test_purpose_easy():
    line = today_purpose_line(
        {"available": True, "workout_type": "easy", "hr_zone_target": 2}
    )
    assert "aerobic" in line and "Zone 2" in line


def test_purpose_threshold_alias_maps_to_tempo():
    line = today_purpose_line({"available": True, "workout_type": "threshold"})
    assert "lactate-threshold" in line


def test_purpose_rest_day():
    line = today_purpose_line(
        {"available": True, "is_rest": True, "workout_type": "rest"}
    )
    assert "rest day" in line.lower()


def test_purpose_unavailable_is_none():
    assert today_purpose_line({"available": False}) is None


# --------------------------------------------------------------------------
# select_today_focus — one adjustment, safety-first, None on a clean day
# --------------------------------------------------------------------------


def test_focus_none_on_clean_day():
    assert (
        select_today_focus({"direction": "hold", "today_workout_type": "easy"}) is None
    )


def test_focus_ease_on_overreach():
    f = select_today_focus({"overreach": True, "today_workout_type": "tempo"})
    assert f["kind"] == "ease"


def test_focus_ease_on_decrease_direction():
    assert select_today_focus({"direction": "decrease"})["kind"] == "ease"


def test_focus_ease_rest_variant_mentions_rest():
    f = select_today_focus({"overreach": True, "today_is_rest": True})
    assert f["kind"] == "ease"
    assert "rest" in f["message"].lower()


def test_focus_rest_day_otherwise_none():
    assert (
        select_today_focus({"today_is_rest": True, "effort_trend": "increasing"})
        is None
    )


def test_focus_execution_easy_hold_back():
    f = select_today_focus(
        {"today_workout_type": "easy", "today_pattern": "faster than planned"}
    )
    assert f["kind"] == "execution"
    assert "hold back" in f["message"].lower()


def test_focus_execution_tempo_commit():
    f = select_today_focus(
        {"today_workout_type": "tempo", "today_pattern": "slower than target"}
    )
    assert f["kind"] == "execution"
    assert "commit" in f["message"].lower()


def test_focus_effort_watch():
    assert (
        select_today_focus(
            {"effort_trend": "increasing", "today_workout_type": "easy"}
        )["kind"]
        == "effort_watch"
    )


def test_focus_push_when_primed():
    assert select_today_focus({"tsb_form": "primed"})["kind"] == "push"
    assert select_today_focus({"direction": "increase"})["kind"] == "push"


def test_focus_safety_outranks_push_and_effort():
    # Overreach must win even if other signals would also fire.
    f = select_today_focus(
        {"overreach": True, "effort_trend": "increasing", "direction": "increase"}
    )
    assert f["kind"] == "ease"


# --------------------------------------------------------------------------
# build_fallback_note — 3 beats, no manufactured concern on a clean day
# --------------------------------------------------------------------------


def test_fallback_note_three_beats():
    note = build_fallback_note(
        _facts(focus={"kind": "execution", "message": "Hold back on the easy stuff."})
    )
    assert note.startswith("7 straight weeks")  # recognition
    assert "lactate-threshold" in note  # purpose
    assert "Hold back on the easy stuff." in note  # focus


def test_fallback_note_no_focus_has_no_adjustment():
    note = build_fallback_note(_facts(focus=None))
    assert "lactate-threshold" in note
    # Only recognition + purpose; no invented warning.
    assert note.count(".") <= 3


def test_fallback_note_empty_is_safe():
    note = build_fallback_note({})
    assert "consistency" in note.lower()


def test_fallback_note_week_pulse_last_resort():
    note = build_fallback_note(
        {"training_age": {}, "today": {"available": False}, "week_pulse": "Nice work."}
    )
    assert note == "Nice work."
