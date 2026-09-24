"""The words on a lock screen — pure composition of every push RunCoach sends.

A push is read in two seconds on a lock screen, so each message obeys three
rules: the title carries the number (distance, week total, today's session),
the body carries the *one* thing to know or do, and every figure comes from
the caller's data — nothing here invents a claim.

One run that also moved the plan is **one** notification, not two: a phone
that buzzes twice for the same act is a feed, and a coach is not a feed.

No I/O, no ORM. The application layer resolves the facts and hands them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.domain.notifications import PushMessage

# Lock screens truncate around here; iOS shows ~4 lines of ~40 chars.
_BODY_LIMIT = 170


@dataclass(frozen=True)
class RunFacts:
    distance_km: float
    duration_minutes: Optional[float] = None
    pace_min_km: Optional[float] = None
    # The one feedback sentence worth reading (already written by the
    # feedback engine), if any.
    feedback: Optional[str] = None


def fmt_pace(pace_min_km: Optional[float]) -> Optional[str]:
    """``5.25`` → ``"5:15/km"``; ``None`` for missing or absurd values."""
    if pace_min_km is None or not (2.0 <= pace_min_km <= 20.0):
        return None
    minutes = int(pace_min_km)
    seconds = int(round((pace_min_km - minutes) * 60))
    if seconds == 60:
        minutes, seconds = minutes + 1, 0
    return f"{minutes}:{seconds:02d}/km"


def fmt_km(km: float) -> str:
    """``8.0`` → ``"8 km"``, ``8.24`` → ``"8.2 km"``."""
    rounded = round(km, 1)
    return f"{int(rounded)} km" if rounded == int(rounded) else f"{rounded} km"


def _clip(text: str, limit: int = _BODY_LIMIT) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def after_sync_message(
    run: RunFacts,
    *,
    plan_id: Optional[str],
    adaptation_headline: Optional[str] = None,
    extra_runs: int = 0,
) -> PushMessage:
    """The note after a sync: the run, and the plan change if there was one."""
    title = f"{fmt_km(run.distance_km)} logged"
    pace = fmt_pace(run.pace_min_km)
    if pace:
        title += f" · {pace}"
    if extra_runs:
        title += f" (+{extra_runs} more)"

    if adaptation_headline:
        title += " — plan adjusted"
        body = adaptation_headline
    elif run.feedback:
        body = run.feedback
    else:
        body = "It's on your plan. Tap to see how it fits the week."

    url = f"/plan/{plan_id}#today-card" if plan_id else "/analytics"
    tag = f"plan-{plan_id}" if plan_id else "run"
    return PushMessage(title=title, body=_clip(body), url=url, tag=tag)


def morning_brief_message(
    *,
    plan_id: str,
    session_title: str,
    session_detail: Optional[str],
    readiness_label: Optional[str],
    drivers: Sequence[str] = (),
    advisory: Optional[str] = None,
) -> PushMessage:
    """Today's session, and whether the body agrees with the plan."""
    title = f"Today: {session_title}"
    if session_detail:
        title += f" · {session_detail}"

    if advisory:
        body = advisory
    elif drivers:
        body = (
            f"{_sentence(drivers)} — keep it controlled, "
            "or open the plan to ease today."
        )
    elif readiness_label:
        body = f"Recovery looks {readiness_label.lower()}. Enjoy it."
    else:
        body = "Check in to tell the plan how you feel."
    return PushMessage(
        title=title,
        body=_clip(body),
        url=f"/plan/{plan_id}#today-card",
        tag=f"today-{plan_id}",
    )


def week_review_message(
    *,
    plan_id: str,
    week_number: int,
    planned_km: float,
    done_km: float,
    sessions_done: int,
    sessions_planned: int,
    next_week_km: Optional[float] = None,
    change_headline: Optional[str] = None,
) -> PushMessage:
    """Sunday evening: how the week went against the plan, and what's next."""
    title = f"Week {week_number}: {fmt_km(done_km)} of {fmt_km(planned_km)}"
    parts = [f"{sessions_done} of {sessions_planned} sessions done."]
    if change_headline:
        parts.append(change_headline)
    elif next_week_km is not None:
        parts.append(f"Next week: {fmt_km(next_week_km)}.")
    return PushMessage(
        title=title,
        body=_clip(" ".join(parts)),
        url=f"/plan/{plan_id}#week-review",
        tag=f"review-{plan_id}",
    )


def _sentence(fragments: Sequence[str]) -> str:
    """``["you slept 5h", "your HRV is low"]`` → ``"You slept 5h and your HRV is low"``."""
    items = [f for f in fragments if f]
    if not items:
        return ""
    joined = (
        items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    )
    return joined[0].upper() + joined[1:]
