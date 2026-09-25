"""Lock-screen copy, week review maths, and notification preferences."""

from datetime import date, timedelta

from app.core.coaching import notification_prefs as prefs
from app.core.coaching.push_messages import (
    RunFacts,
    after_sync_message,
    fmt_pace,
    morning_brief_message,
    week_review_message,
)
from app.core.coaching.week_review import build_week_review, week_planned_km

MONDAY = date(2026, 9, 21)


def test_pace_formatting_rounds_seconds_and_rejects_absurd_values():
    assert fmt_pace(5.25) == "5:15/km"
    assert fmt_pace(4.9999) == "5:00/km"
    assert fmt_pace(None) is None
    assert fmt_pace(45) is None


def test_a_run_that_moved_the_plan_is_one_notification_not_two():
    msg = after_sync_message(
        RunFacts(distance_km=8.24, pace_min_km=5.2, feedback="Nicely controlled."),
        plan_id="p1",
        adaptation_headline="Eased upcoming volume ~6%.",
    )
    assert msg.title == "8.2 km logged · 5:12/km — plan adjusted"
    assert msg.body == "Eased upcoming volume ~6%."
    assert msg.url == "/plan/p1#today-card"
    assert msg.tag == "plan-p1"


def test_a_plain_run_carries_its_feedback():
    msg = after_sync_message(
        RunFacts(distance_km=10, feedback="Right in zone 2."), plan_id=None
    )
    assert msg.title == "10 km logged"
    assert msg.body == "Right in zone 2."
    assert msg.url == "/analytics"


def test_long_bodies_are_clipped_on_a_word_boundary():
    msg = after_sync_message(
        RunFacts(distance_km=5, feedback="word " * 80), plan_id="p"
    )
    assert len(msg.body) <= 170
    assert msg.body.endswith("…")


def test_morning_brief_leads_with_what_the_body_says():
    msg = morning_brief_message(
        plan_id="p",
        session_title="Tempo",
        session_detail="8 km",
        readiness_label="Run-down",
        drivers=["your HRV is 18% below your usual", "you slept 5h"],
    )
    assert msg.title == "Today: Tempo · 8 km"
    assert msg.body.startswith("Your HRV is 18% below your usual and you slept 5h")


def test_week_review_message_numbers():
    msg = week_review_message(
        plan_id="p",
        week_number=6,
        planned_km=40,
        done_km=34.5,
        sessions_done=4,
        sessions_planned=5,
        next_week_km=42,
    )
    assert msg.title == "Week 6: 34.5 km of 40 km"
    assert msg.body == "4 of 5 sessions done. Next week: 42 km."


def _week(week_no: int = 3):
    return {
        "week": week_no,
        "daily_workouts": [
            {"day": 1, "type": "easy", "distance": 6},
            {"day": 2, "type": "rest", "distance": 0},
            {"day": 3, "type": "tempo", "distance": 8},
            {"day": 5, "type": "easy", "distance": 6},
            {"day": 7, "type": "long", "distance": 14},
        ],
    }


def test_week_review_counts_sessions_by_date_and_rest_day_runs_as_km_only():
    runs = [
        (MONDAY, 6.0),
        (MONDAY + timedelta(days=1), 5.0),  # a run on the rest day
        (MONDAY + timedelta(days=2), 8.2),
        (MONDAY + timedelta(days=6), 14.0),
        (MONDAY + timedelta(days=8), 20.0),  # next week — ignored
    ]
    review = build_week_review(_week(), week_start=MONDAY, runs=runs)
    assert review.planned_km == 34
    assert review.done_km == 33.2
    assert (review.sessions_done, review.sessions_planned) == (3, 4)
    assert review.missed_days == ["Fri"]
    assert review.verdict == "on_plan"


def test_week_review_verdicts():
    short = build_week_review(_week(), week_start=MONDAY, runs=[(MONDAY, 25.0)])
    assert short.verdict == "short" and short.line == "9 km short of plan."
    over = build_week_review(_week(), week_start=MONDAY, runs=[(MONDAY, 45.0)])
    assert over.verdict == "over"
    light = build_week_review(_week(), week_start=MONDAY, runs=[])
    assert light.verdict == "light"


def test_next_week_total_comes_from_the_plan():
    review = build_week_review(_week(), week_start=MONDAY, runs=[], next_week=_week(4))
    assert review.next_week_km == week_planned_km(_week(4)) == 34


def test_prefs_default_on_and_store_only_explicit_choices():
    assert all(prefs.resolve(None).values())
    merged = prefs.merge(None, {"morning_brief": False, "bogus": True})
    assert merged == {"morning_brief": False}
    assert prefs.wants(merged, prefs.MORNING_BRIEF) is False
    assert prefs.wants(merged, prefs.AFTER_RUN) is True
    assert prefs.wants(merged, "bogus") is False


def test_recovery_is_one_easy_day_per_mile_within_bounds():
    from app.core.race.recovery import recovery_guidance

    half = recovery_guidance(21.1, 48.0)
    assert half.easy_days == 13 and half.next_base_km == 34
    assert recovery_guidance(5.0, None).easy_days == 3
    assert recovery_guidance(160.0, 90.0).easy_days == 28
    assert recovery_guidance(None, 40.0) is None
