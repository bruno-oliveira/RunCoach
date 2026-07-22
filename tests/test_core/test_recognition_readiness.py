"""Tests for the readiness beat in select_today_focus (core/coaching/recognition)."""

from app.core.coaching.recognition import select_today_focus


def test_low_readiness_eases_a_hard_session():
    f = select_today_focus(
        {
            "today_readiness_band": "run_down",
            "today_readiness_drivers": ["you slept 5h", "your legs are heavy"],
            "today_workout_type": "interval",
            "today_is_rest": False,
        }
    )
    assert f is not None
    assert f["kind"] == "readiness_ease"
    # Names the concrete drivers and offers to down-shift today's quality work.
    assert "You slept 5h and your legs are heavy" in f["message"]
    assert "interval" in f["message"]


def test_low_readiness_on_easy_day_keeps_it_easy():
    f = select_today_focus(
        {
            "today_readiness_band": "depleted",
            "today_readiness_drivers": [],
            "today_workout_type": "easy",
            "today_is_rest": False,
        }
    )
    assert f["kind"] == "readiness_ease"
    assert "easy" in f["message"].lower()


def test_low_readiness_on_rest_day_affirms_rest():
    f = select_today_focus(
        {
            "today_readiness_band": "run_down",
            "today_readiness_drivers": ["your energy is low"],
            "today_is_rest": True,
        }
    )
    assert f["kind"] == "readiness_ease"
    assert "rest" in f["message"].lower()


def test_primed_readiness_encourages_a_hard_session():
    f = select_today_focus(
        {
            "today_readiness_band": "primed",
            "today_workout_type": "tempo",
            "today_is_rest": False,
        }
    )
    assert f["kind"] == "readiness_push"


def test_primed_readiness_stays_quiet_on_easy_day():
    # Being fresh on an easy day isn't worth a beat — falls through.
    f = select_today_focus(
        {
            "today_readiness_band": "primed",
            "today_workout_type": "easy",
            "today_is_rest": False,
        }
    )
    assert f is None


def test_middling_readiness_does_not_speak():
    # An ordinary "ok"/"good" morning must never nag — falls through to the
    # rest of the focus logic (which is clean here).
    assert (
        select_today_focus(
            {
                "today_readiness_band": "good",
                "today_workout_type": "easy",
                "direction": "hold",
            }
        )
        is None
    )


def test_readiness_ease_takes_priority_over_push_signals():
    # A rough morning must win even if the engine otherwise says "increase".
    f = select_today_focus(
        {
            "today_readiness_band": "run_down",
            "today_readiness_drivers": ["your energy is low"],
            "today_workout_type": "tempo",
            "direction": "increase",
            "tsb_form": "primed",
        }
    )
    assert f["kind"] == "readiness_ease"
