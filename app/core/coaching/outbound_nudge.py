"""Decides whether a runner is worth interrupting — and with what.

Every other coaching surface in RunCoach is computed on page load, which means
it can only speak to someone already looking at it. This one runs on a
schedule and reaches an inbox, so the bar is higher: an email that says nothing
the runner couldn't have worked out is worse than no email.

Three guards, checked in priority order:

    gone_quiet     – sessions scheduled, nothing logged, and the app unopened.
                     The only signal the app genuinely cannot deliver itself.
    low_readiness  – a run of rough mornings. Safety before opportunity, the
                     same rule the in-app proactive nudge follows.
    adaptation     – whatever the in-app nudge engine already found, forwarded
                     rather than re-derived.

Only the highest-priority firing guard is returned. Pure: no I/O, no ORM — the
caller resolves the counts and passes them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

# --- Thresholds --------------------------------------------------------------
# Deliberately slack. This is the one surface that can annoy someone who isn't
# asking to hear from us, so each guard wants a situation that is unambiguous
# from the outside.
#
#   _QUIET_DAYS         no logged run for this long reads as "drifted", not
#                       "rest day".
#   _QUIET_MIN_MISSED   …and only if the plan actually asked for something in
#                       that window. A quiet taper week is not a problem.
#   _LOW_READINESS_RUN  consecutive rough mornings before we say anything.
#   _LOW_READINESS_MAX  score at or below which a morning counts as rough.
#                       Matches ``readiness_checkin._LOW_THRESHOLD``.
_QUIET_DAYS = 5
_QUIET_MIN_MISSED = 2
_LOW_READINESS_RUN = 3
_LOW_READINESS_MAX = 45.0


@dataclass(frozen=True)
class OutboundNudge:
    """One thing worth putting in a runner's inbox."""

    kind: str
    signature: str
    subject: str
    headline: str
    body: str
    cta_label: str
    cta_path: str


def detect_outbound_nudge(
    *,
    plan_id: str,
    days_since_last_run: Optional[int],
    sessions_missed_recently: int,
    next_session_label: Optional[str] = None,
    recent_readiness_scores: Sequence[Optional[float]] = (),
    adaptation_headline: Optional[str] = None,
    adaptation_detail: Optional[str] = None,
    adaptation_signature: Optional[str] = None,
) -> Optional[OutboundNudge]:
    """The single highest-priority nudge for this runner, or ``None``.

    ``days_since_last_run`` is ``None`` when nothing has ever been logged.
    ``recent_readiness_scores`` is newest-first; ``None`` entries are mornings
    with no check-in and break a run rather than extending it.
    """
    path = f"/plan/{plan_id}"
    return (
        _gone_quiet(days_since_last_run, sessions_missed_recently, path)
        or _low_readiness(recent_readiness_scores, next_session_label, path)
        or _adaptation(
            adaptation_headline, adaptation_detail, adaptation_signature, path
        )
    )


def _gone_quiet(
    days_since_last_run: Optional[int],
    sessions_missed: int,
    path: str,
) -> Optional[OutboundNudge]:
    # ``None`` means nothing has *ever* been logged. That is far more likely to
    # be a runner who tracks nowhere than one who has drifted, and telling them
    # they've missed sessions they may well have run would be plain wrong.
    if days_since_last_run is None or days_since_last_run < _QUIET_DAYS:
        return None
    if sessions_missed < _QUIET_MIN_MISSED:
        return None

    sessions = _plural(sessions_missed, "session", "sessions")
    # Bucketed by week so a runner who stays away for a month hears from us
    # about once a week, not once a day.
    weeks_quiet = days_since_last_run // 7
    return OutboundNudge(
        kind="gone_quiet",
        signature=f"gone_quiet:{weeks_quiet}",
        subject="Your plan is still here",
        headline=f"{sessions} have gone by since your last run.",
        body=(
            f"It's been {days_since_last_run} days. That's not a problem to fix — "
            "it's just information. Tell RunCoach what happened and the plan "
            "reshapes around where you actually are, rather than where it "
            "assumed you'd be."
        ),
        cta_label="Pick the plan back up",
        cta_path=path,
    )


def _low_readiness(
    scores: Sequence[Optional[float]],
    next_session_label: Optional[str],
    path: str,
) -> Optional[OutboundNudge]:
    run = _leading_low_run(scores)
    if run < _LOW_READINESS_RUN:
        return None

    session = f" {next_session_label} is coming up." if next_session_label else ""
    return OutboundNudge(
        kind="low_readiness",
        signature=f"low_readiness:{run}",
        subject="Three rough mornings in a row",
        headline=f"You've checked in run-down {run} mornings running.",
        body=(
            "One bad night is noise; a run of them is a signal."
            f"{session} Easing the next hard session — or moving it — costs you "
            "far less than pushing through and losing the week after it."
        ),
        cta_label="Adjust this week",
        cta_path=path,
    )


def _adaptation(
    headline: Optional[str],
    detail: Optional[str],
    signature: Optional[str],
    path: str,
) -> Optional[OutboundNudge]:
    if not headline:
        return None
    return OutboundNudge(
        kind="adaptation",
        signature=f"adaptation:{signature or headline}",
        subject="RunCoach noticed something in your training",
        headline=headline,
        body=detail or "Open your plan to see what changed and why.",
        cta_label="See the suggestion",
        cta_path=path,
    )


def _leading_low_run(scores: Sequence[Optional[float]]) -> int:
    """How many of the most recent mornings, unbroken, came in low.

    A missing check-in breaks the run: we can't claim someone felt rough on a
    day they never told us about.
    """
    run = 0
    for score in scores:
        if score is None or score > _LOW_READINESS_MAX:
            break
        run += 1
    return run


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def render_email(
    nudge: OutboundNudge, *, base_url: str, unsubscribe_url: str, name: Optional[str]
) -> tuple[str, str]:
    """``(text, html)`` for one nudge.

    Plain text is the real message and reads on its own; the HTML is the same
    words with a link styled as a button. Both carry the unsubscribe — an email
    the runner can't stop is not a coach, it's spam.
    """
    greeting = f"Hi {name}," if name else "Hi,"
    cta_url = f"{base_url.rstrip('/')}{nudge.cta_path}"

    text = "\n".join(
        [
            greeting,
            "",
            nudge.headline,
            "",
            nudge.body,
            "",
            f"{nudge.cta_label}: {cta_url}",
            "",
            "—",
            "RunCoach",
            f"Stop these emails: {unsubscribe_url}",
        ]
    )

    html = (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'max-width:520px;color:#1a1a1a;line-height:1.55">'
        f"<p>{_esc(greeting)}</p>"
        f'<p style="font-size:17px;font-weight:600">{_esc(nudge.headline)}</p>'
        f"<p>{_esc(nudge.body)}</p>"
        f'<p><a href="{_esc(cta_url)}" '
        'style="display:inline-block;padding:10px 18px;background:#0E7C5A;'
        'color:#fff;border-radius:8px;text-decoration:none;font-weight:600">'
        f"{_esc(nudge.cta_label)}</a></p>"
        '<hr style="border:none;border-top:1px solid #e5e5e5;margin:24px 0">'
        '<p style="font-size:12px;color:#6b6b6b">RunCoach &middot; '
        f'<a href="{_esc(unsubscribe_url)}" style="color:#6b6b6b">'
        "Stop these emails</a></p>"
        "</div>"
    )
    return text, html


def _esc(value: str) -> str:
    """Minimal HTML escaping for the interpolated copy."""
    out: List[str] = []
    for char in value:
        if char == "&":
            out.append("&amp;")
        elif char == "<":
            out.append("&lt;")
        elif char == ">":
            out.append("&gt;")
        elif char == '"':
            out.append("&quot;")
        else:
            out.append(char)
    return "".join(out)
