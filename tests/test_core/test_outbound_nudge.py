"""Tests for what earns a place in a runner's inbox.

This is the only surface that can interrupt someone who isn't asking to hear
from us, so most of these tests are about *not* firing. The guards have to stay
quiet on ordinary weeks, and the copy has to carry an unsubscribe every time.
"""

from app.core.coaching.outbound_nudge import detect_outbound_nudge, render_email

PLAN_ID = "plan-123"


def _detect(**overrides):
    kwargs = {
        "plan_id": PLAN_ID,
        "days_since_last_run": 1,
        "sessions_missed_recently": 0,
    }
    kwargs.update(overrides)
    return detect_outbound_nudge(**kwargs)


# ---------------------------------------------------------------------------
# Silence
# ---------------------------------------------------------------------------


def test_a_runner_on_track_hears_nothing():
    assert _detect() is None


def test_a_rest_week_is_not_a_missed_week():
    # Six quiet days, but the plan asked for nothing — a taper, not a drift.
    assert _detect(days_since_last_run=6, sessions_missed_recently=0) is None


def test_four_quiet_days_is_still_within_a_normal_week():
    assert _detect(days_since_last_run=4, sessions_missed_recently=3) is None


def test_one_missed_session_is_not_worth_an_email():
    assert _detect(days_since_last_run=6, sessions_missed_recently=1) is None


def test_a_runner_who_has_never_logged_is_never_told_they_went_quiet():
    # Far more likely they track nowhere than that they stopped running, and
    # telling them they missed sessions they may have run would be wrong.
    assert _detect(days_since_last_run=None, sessions_missed_recently=5) is None


# ---------------------------------------------------------------------------
# gone_quiet
# ---------------------------------------------------------------------------


def test_gone_quiet_fires_once_the_plan_has_actually_been_missed():
    nudge = _detect(days_since_last_run=6, sessions_missed_recently=3)
    assert nudge is not None
    assert nudge.kind == "gone_quiet"
    assert "3 sessions" in nudge.headline
    assert nudge.cta_path == f"/plan/{PLAN_ID}"


def test_gone_quiet_signature_buckets_by_week_so_it_repeats_at_most_weekly():
    # Same week away → same signature → the repeat guard suppresses it.
    week_one = _detect(days_since_last_run=8, sessions_missed_recently=4)
    still_week_one = _detect(days_since_last_run=12, sessions_missed_recently=6)
    week_three = _detect(days_since_last_run=21, sessions_missed_recently=12)
    assert week_one is not None and still_week_one is not None
    assert week_one.signature == still_week_one.signature
    assert week_three is not None
    assert week_three.signature != week_one.signature


def test_gone_quiet_headline_agrees_with_itself_on_a_single_session():
    nudge = _detect(days_since_last_run=9, sessions_missed_recently=2)
    assert nudge is not None and "2 sessions" in nudge.headline


# ---------------------------------------------------------------------------
# low_readiness
# ---------------------------------------------------------------------------


def test_two_rough_mornings_are_not_yet_a_pattern():
    assert _detect(recent_readiness_scores=[30.0, 40.0, 70.0]) is None


def test_three_rough_mornings_running_earn_a_word():
    nudge = _detect(recent_readiness_scores=[30.0, 41.0, 44.0, 80.0])
    assert nudge is not None
    assert nudge.kind == "low_readiness"
    assert "3 mornings" in nudge.headline


def test_a_missing_check_in_breaks_the_run_rather_than_extending_it():
    # We can't claim someone felt rough on a day they never told us about.
    assert _detect(recent_readiness_scores=[30.0, None, 20.0, 25.0]) is None


def test_a_good_morning_in_the_middle_breaks_the_run():
    assert _detect(recent_readiness_scores=[30.0, 90.0, 20.0, 25.0]) is None


def test_the_next_hard_session_is_named_when_one_is_close():
    nudge = _detect(
        recent_readiness_scores=[20.0, 20.0, 20.0],
        next_session_label="Thursday's tempo",
    )
    assert nudge is not None and "Thursday's tempo" in nudge.body


def test_the_body_reads_without_a_session_label():
    nudge = _detect(recent_readiness_scores=[20.0, 20.0, 20.0])
    assert nudge is not None
    assert "None" not in nudge.body
    assert nudge.body.startswith("One bad night")


# ---------------------------------------------------------------------------
# adaptation passthrough
# ---------------------------------------------------------------------------


def test_the_in_app_nudge_is_forwarded_verbatim_not_re_derived():
    nudge = _detect(
        adaptation_headline="Your easy runs are getting cheaper",
        adaptation_detail="VDOT is up 1.5 over four weeks.",
        adaptation_signature="fitness_jump:4",
    )
    assert nudge is not None
    assert nudge.kind == "adaptation"
    assert nudge.headline == "Your easy runs are getting cheaper"
    assert nudge.body == "VDOT is up 1.5 over four weeks."
    assert "fitness_jump:4" in nudge.signature


def test_an_adaptation_signal_with_no_headline_is_nothing():
    assert _detect(adaptation_detail="orphaned detail") is None


# ---------------------------------------------------------------------------
# Priority — safety before opportunity, and reach before both
# ---------------------------------------------------------------------------


def test_gone_quiet_outranks_everything_else():
    nudge = _detect(
        days_since_last_run=9,
        sessions_missed_recently=4,
        recent_readiness_scores=[10.0, 10.0, 10.0],
        adaptation_headline="You're getting fitter",
    )
    assert nudge is not None and nudge.kind == "gone_quiet"


def test_low_readiness_outranks_the_opportunistic_bump():
    # A tired runner is never told to push harder.
    nudge = _detect(
        recent_readiness_scores=[10.0, 10.0, 10.0],
        adaptation_headline="You're getting fitter",
    )
    assert nudge is not None and nudge.kind == "low_readiness"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_both_bodies_carry_the_unsubscribe_and_an_absolute_link():
    nudge = _detect(days_since_last_run=6, sessions_missed_recently=3)
    assert nudge is not None
    text, html = render_email(
        nudge,
        base_url="https://runcoach.example/",
        unsubscribe_url="https://runcoach.example/unsubscribe?u=1&t=abc",
        name="Sam",
    )

    assert "https://runcoach.example/unsubscribe?u=1&t=abc" in text
    # The same URL in an href, with the ampersand properly entity-encoded.
    assert "https://runcoach.example/unsubscribe?u=1&amp;t=abc" in html

    for body in (text, html):
        # Trailing slash on base_url must not double up into "//plan/".
        assert f"https://runcoach.example/plan/{PLAN_ID}" in body
        assert "//plan/" not in body
        assert "Sam" in body


def test_a_nameless_runner_still_gets_a_greeting():
    nudge = _detect(days_since_last_run=6, sessions_missed_recently=3)
    assert nudge is not None
    text, html = render_email(
        nudge, base_url="https://x.test", unsubscribe_url="https://x.test/u", name=None
    )
    assert text.startswith("Hi,")
    assert "None" not in text
    assert "Hi," in html


def test_interpolated_copy_is_escaped_in_the_html_body():
    nudge = _detect(
        adaptation_headline="<script>alert(1)</script>",
        adaptation_detail="a & b",
    )
    assert nudge is not None
    _, html = render_email(
        nudge, base_url="https://x.test", unsubscribe_url="https://x.test/u", name=None
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html
