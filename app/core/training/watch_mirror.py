"""Pure logic for mirroring a plan onto a watch calendar.

The decisions — which days belong in the window, which calendar events are ours,
what changed since we last pushed, and what therefore has to be created or
deleted — are all computable without touching the network or the database. They
live here so they can be unit-tested directly and read by any layer.

The I/O half (fetching the window, issuing the writes, recording the outcome)
is :mod:`app.application.watch_sync_service`.

Everything here takes the training plan as a duck-typed object and only reads
attributes off it, so this module stays free of ORM and infrastructure imports
as ``app/core`` requires.
"""

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple, Optional

from app.core.time_utils import local_today
from app.core.training.workout_steps.intervals_export import build_intervals_workout

# How far ahead we mirror. Intervals.icu only forwards about the next week to
# the device, so a longer window costs nothing on the wrist — but it covers a
# runner who opens the app fortnightly, and it means a session is already in
# place well before it becomes the one they're about to run.
WINDOW_DAYS = 21


def external_id_prefix(plan_id: str) -> str:
    """The ``external_id`` prefix that marks a calendar event as this plan's."""
    return f"runcoach-{plan_id}-"


def owns_event(plan_id: str, external_id: Any) -> bool:
    """Whether a calendar event is one this plan created.

    The single guard on every delete. The runner's calendar also holds their own
    workouts, their coach's, and events from every other app they have
    connected, so nothing may be removed without passing through here. The
    trailing hyphen in the prefix matters: without it, plan ``abc`` would claim
    plan ``abcdef``'s events.
    """
    return isinstance(external_id, str) and external_id.startswith(
        external_id_prefix(plan_id)
    )


def event_hash(event: dict[str, Any]) -> str:
    """Stable short hash of the parts of an event the watch actually shows.

    ``external_id`` is excluded because it is the key this hash is stored under.
    Comparing hashes is what keeps re-mirroring free: an unchanged plan issues
    no writes, so API volume tracks real change rather than page loads.
    """
    body = {
        key: event.get(key)
        for key in ("name", "description", "moving_time", "start_date_local")
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def plan_start_date(training_plan) -> Optional[date]:
    """The plan's start date as a plain ``date``, or None when unset."""
    start = training_plan.start_date
    if isinstance(start, datetime):
        return start.date()
    if isinstance(start, date):
        return start
    return None


def workout_date(training_plan, week: int, day: int) -> date:
    """Calendar date of the (week, day) workout.

    Falls back to today as the week-1 anchor when the plan has no start date, so
    a dateless plan still produces sensible relative days rather than failing.
    """
    base = plan_start_date(training_plan) or local_today()
    return base + timedelta(weeks=week - 1, days=day - 1)


def workout_start_date_local(training_plan, week: int, day: int) -> str:
    """ISO ``start_date_local`` for the (week, day) workout on the plan calendar."""
    return f"{workout_date(training_plan, week, day).isoformat()}T00:00:00"


def build_event(
    training_plan, week: int, day: int, day_data: dict[str, Any]
) -> dict[str, Any]:
    """Build the Intervals.icu calendar event for one planned workout.

    Raises:
        ValueError: The day has nothing sendable (a rest day, or a day with
            neither structured steps nor a distance) — callers decide whether
            that is an error or a skip.
    """
    workout = build_intervals_workout(day_data)
    return {
        "category": "WORKOUT",
        "type": "Run",
        "start_date_local": workout_start_date_local(training_plan, week, day),
        "name": workout["name"],
        "description": workout["description"],
        "moving_time": workout["moving_time"],
        "external_id": f"{external_id_prefix(training_plan.id)}{week}-{day}",
    }


def _plan_days(training_plan):
    """Yield ``(week, day, day_data)`` for every well-formed day in the plan."""
    for week_data in training_plan.plan_data or []:
        week = week_data.get("week")
        if not isinstance(week, int):
            continue
        for day_data in week_data.get("daily_workouts", []):
            day = day_data.get("day")
            if isinstance(day, int):
                yield week, day, day_data


def events_in_window(
    training_plan,
    today: Optional[date] = None,
    forward_days: int = WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Sendable events for the plan days between today and the window edge.

    Days outside the window, rest days, and days with nothing structured to send
    are all left out — the first because they are not due yet, the rest because
    there is no workout to run.
    """
    anchor = today or local_today()
    horizon = anchor + timedelta(days=forward_days)
    events: list[dict[str, Any]] = []

    for week, day, day_data in _plan_days(training_plan):
        when = workout_date(training_plan, week, day)
        if when < anchor or when > horizon:
            continue
        try:
            events.append(build_event(training_plan, week, day, day_data))
        except ValueError:
            continue
    return events


class WatchDiff(NamedTuple):
    """What a reconcile has to do to bring the calendar back in line."""

    to_create: list[dict[str, Any]]
    to_delete_ids: list[Any]
    next_hashes: dict[str, str]
    unchanged: int


def diff_window(
    plan_id: str,
    desired: list[dict[str, Any]],
    remote: list[dict[str, Any]],
    stored: dict[str, str],
) -> WatchDiff:
    """Work out the create/delete set for one window. Pure — no I/O.

    Args:
        plan_id: Used to decide which remote events are ours to touch.
        desired: The events the plan says should be on the calendar.
        remote: Everything Intervals.icu currently has in the window, including
            events belonging to the runner and to other apps.
        stored: ``external_id`` -> hash of what we last pushed.

    Returns:
        The work to do, plus the hash map to persist once it succeeds.
    """
    desired_by_id = {
        str(e["external_id"]): e for e in desired if e.get("external_id") is not None
    }

    # Ours only. Everything else in `remote` belongs to somebody else and is now
    # out of scope for the rest of this function — which is the whole safety
    # story: no later branch can reach an event that did not pass this filter.
    ours: dict[str, list[dict[str, Any]]] = {}
    for event in remote:
        if not isinstance(event, dict):
            continue
        external_id = event.get("external_id")
        if owns_event(plan_id, external_id):
            ours.setdefault(str(external_id), []).append(event)

    to_create: list[dict[str, Any]] = []
    to_delete_ids: list[Any] = []
    next_hashes = dict(stored)
    unchanged = 0

    for external_id, event in desired_by_id.items():
        current = event_hash(event)
        existing = ours.get(external_id, [])
        # Present exactly once, and identical to what we last sent: leave it
        # alone. Checking presence before the hash matters — a session the
        # runner deleted inside Intervals still has a matching stored hash, and
        # "keep my watch in sync" means we put it back.
        if len(existing) == 1 and stored.get(external_id) == current:
            unchanged += 1
            continue
        to_delete_ids.extend(e["id"] for e in existing if e.get("id") is not None)
        to_create.append(event)
        next_hashes[external_id] = current

    # Ghosts: events we own, still on the calendar, no longer in the plan — a
    # day that became rest, or a session that moved to another weekday. Before
    # this, nothing was ever deleted and they stayed on the watch forever.
    for external_id, events in ours.items():
        if external_id in desired_by_id:
            continue
        to_delete_ids.extend(e["id"] for e in events if e.get("id") is not None)
        next_hashes.pop(external_id, None)

    return WatchDiff(to_create, to_delete_ids, next_hashes, unchanged)


def sessions_behind(training_plan, today: Optional[date] = None) -> int:
    """How many upcoming sessions the watch has not been told about.

    Derived from the stored hashes rather than a counter, so it is self-healing:
    a successful mirror drives it to zero without anything having to remember to
    reset it. This is what the "your watch is N sessions behind" banner counts.
    """
    if not training_plan.watch_sync_enabled:
        return 0
    stored = training_plan.watch_event_hashes or {}
    return sum(
        1
        for event in events_in_window(training_plan, today=today)
        if stored.get(str(event.get("external_id"))) != event_hash(event)
    )


def synced_day_keys(training_plan) -> set[tuple[int, int]]:
    """``(week, day)`` pairs whose current session is the one on the calendar.

    Drives the per-card "on your watch" state. Derived from the stored hashes
    rather than a browser flag, so it survives a reload — and it stops being
    true the moment the plan changes, which is the honest answer: the card must
    not claim the watch holds a session we have since rewritten.
    """
    stored = training_plan.watch_event_hashes or {}
    if not stored:
        return set()

    keys: set[tuple[int, int]] = set()
    for week, day, day_data in _plan_days(training_plan):
        try:
            event = build_event(training_plan, week, day, day_data)
        except ValueError:
            continue
        if stored.get(event["external_id"]) == event_hash(event):
            keys.add((week, day))
    return keys
