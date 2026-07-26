"""Tests for the Today card's view model — mostly the one line under the session.

The card exists to put the check-in next to the session it should change, so
the advisory is the whole feature. It has to be quiet by default (a line on
every ordinary day is noise nobody reads) and it must never claim the plan
already moved, because it hasn't — only Adjust my plan moves it.
"""

from datetime import date

from app.core.coaching.today_card import (
    build_today_card,
    format_date_label,
    format_detail,
    title_for,
)


def _workout(**overrides) -> dict:
    base = {"id": "w1", "type": "easy", "distance": 8.0, "duration_min": 45}
    base.update(overrides)
    return base


TODAY = date(2026, 7, 26)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_date_label_avoids_platform_specific_strftime():
    # "%-d" is glibc-only; the label is assembled from .day instead.
    assert format_date_label(date(2026, 7, 5)) == "Sun 5 Jul"
    assert format_date_label(date(2026, 12, 26)) == "Sat 26 Dec"


def test_title_humanises_underscored_types():
    assert title_for("race_pace") == "Race Pace"
    assert title_for("tempo") == "Tempo"
    assert title_for(None) == "Run"
    assert title_for("") == "Run"


def test_detail_drops_whichever_half_is_missing():
    assert format_detail(8.0, 45) == "8.0 km · ≈ 45 min"
    assert format_detail(8.0, None) == "8.0 km"
    assert format_detail(None, 45) == "≈ 45 min"
    assert format_detail(0, None) == ""


# ---------------------------------------------------------------------------
# Session assembly
# ---------------------------------------------------------------------------


def test_no_workout_leaves_the_card_without_a_session():
    card = build_today_card(today=TODAY, workout=None)
    assert card.session is None
    assert card.has_session is False
    assert card.advisory is None


def test_rest_day_is_titled_rather_than_typed():
    card = build_today_card(today=TODAY, workout=_workout(type="rest", distance=0))
    assert card.session is not None
    assert card.session.is_rest
    assert card.session.title == "Rest day"


def test_zero_distance_recovery_counts_as_rest_but_a_real_one_does_not():
    resting = build_today_card(
        today=TODAY, workout=_workout(type="recovery", distance=0, duration_min=None)
    )
    assert resting.session is not None and resting.session.is_rest

    running = build_today_card(
        today=TODAY, workout=_workout(type="recovery", distance=4.0)
    )
    assert running.session is not None and not running.session.is_rest


def test_logged_km_marks_the_session_and_rounds():
    card = build_today_card(today=TODAY, workout=_workout(), logged_km=8.2449)
    assert card.session is not None
    assert card.session.logged is True
    assert card.session.logged_km == 8.2


# ---------------------------------------------------------------------------
# The advisory — silence is the default
# ---------------------------------------------------------------------------


def test_no_checkin_means_no_advisory():
    card = build_today_card(today=TODAY, workout=_workout(type="tempo"))
    assert card.advisory is None


def test_good_morning_before_an_easy_run_says_nothing():
    card = build_today_card(
        today=TODAY, workout=_workout(type="easy"), readiness_band="good"
    )
    assert card.advisory is None


def test_run_down_before_a_hard_session_points_at_adjust_not_at_a_change():
    card = build_today_card(
        today=TODAY, workout=_workout(type="tempo"), readiness_band="run_down"
    )
    assert card.advisory is not None
    assert "Adjust my plan" in card.advisory
    # The plan has not moved, so the copy must not imply that it has.
    assert "eased" not in card.advisory.lower()
    assert "changed" not in card.advisory.lower()


def test_run_down_before_an_easy_run_keeps_it_easy_rather_than_escalating():
    card = build_today_card(
        today=TODAY, workout=_workout(type="easy"), readiness_band="depleted"
    )
    assert card.advisory is not None
    assert "easy" in card.advisory.lower()
    assert "Adjust my plan" not in card.advisory


def test_flat_morning_only_speaks_up_before_a_hard_session():
    hard = build_today_card(
        today=TODAY, workout=_workout(type="interval"), readiness_band="ok"
    )
    assert hard.advisory is not None and "conservatively" in hard.advisory

    easy = build_today_card(
        today=TODAY, workout=_workout(type="easy"), readiness_band="ok"
    )
    assert easy.advisory is None


def test_primed_before_a_hard_session_encourages_it():
    card = build_today_card(
        today=TODAY, workout=_workout(type="vo2max"), readiness_band="primed"
    )
    assert card.advisory is not None and "commit" in card.advisory


def test_a_logged_session_gets_no_advice_after_the_fact():
    card = build_today_card(
        today=TODAY,
        workout=_workout(type="tempo"),
        readiness_band="depleted",
        logged_km=9.0,
    )
    assert card.advisory is None


def test_rest_day_advisory_only_appears_on_a_rough_morning():
    rough = build_today_card(
        today=TODAY,
        workout=_workout(type="rest", distance=0),
        readiness_band="run_down",
    )
    assert rough.advisory is not None and "Rest day" in rough.advisory

    fine = build_today_card(
        today=TODAY, workout=_workout(type="rest", distance=0), readiness_band="primed"
    )
    assert fine.advisory is None


def test_fatigue_softening_is_reported_only_when_readiness_has_nothing_to_say():
    softened = build_today_card(
        today=TODAY, workout=_workout(type="tempo"), fatigue_softened=True
    )
    assert softened.advisory is not None and "softened" in softened.advisory

    # A rough check-in is more specific and more urgent, so it wins.
    both = build_today_card(
        today=TODAY,
        workout=_workout(type="tempo"),
        readiness_band="run_down",
        fatigue_softened=True,
    )
    assert both.advisory is not None and "Adjust my plan" in both.advisory


def test_readiness_details_are_carried_through_for_the_template():
    card = build_today_card(
        today=TODAY,
        workout=_workout(),
        week_number=3,
        total_weeks=12,
        phase="build",
        readiness_band="ok",
        readiness_score=52.5,
        readiness_label="A bit flat",
        readiness_drivers=["you slept 5h"],
    )
    assert (card.week_number, card.total_weeks, card.phase) == (3, 12, "build")
    assert card.readiness_score == 52.5
    assert card.readiness_label == "A bit flat"
    assert card.readiness_drivers == ["you slept 5h"]
