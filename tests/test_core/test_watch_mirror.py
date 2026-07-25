"""Unit tests for the pure watch-mirror decisions.

The reconciler's integration tests live in
``tests/test_services/test_watch_sync_service.py``. These exercise the same
decisions one layer down, where the safety property — never touch an event we
don't own — can be asserted without any calendar simulation in the way.
"""

from datetime import date, datetime, timedelta

from app.core.training.watch_mirror import (
    diff_window,
    event_hash,
    sessions_behind,
    synced_day_keys,
)


class _Plan:
    """The handful of attributes the mirror actually reads off a plan."""

    def __init__(self, plan_data, hashes=None, enabled=True, start=None):
        self.id = "p1"
        self.plan_data = plan_data
        self.watch_event_hashes = hashes
        self.watch_sync_enabled = enabled
        self.start_date = datetime.combine(start or date.today(), datetime.min.time())


def _plan(hashes=None, enabled=True, start=None) -> _Plan:
    return _Plan(
        [
            {
                "week": 1,
                "daily_workouts": [
                    {"day": 1, "type": "rest", "distance": 0},
                    {"day": 2, "type": "easy", "distance": 8.0},
                    {"day": 3, "type": "easy", "distance": 5.0},
                ],
            }
        ],
        hashes=hashes,
        enabled=enabled,
        start=start,
    )


def _event(external_id, description="- 8km", start="2026-08-01T00:00:00"):
    return {
        "external_id": external_id,
        "name": "Easy",
        "description": description,
        "moving_time": 2640,
        "start_date_local": start,
    }


# ---------------------------------------------------------------------------
# diff_window
# ---------------------------------------------------------------------------


def test_diff_creates_everything_against_an_empty_calendar():
    desired = [_event("runcoach-p1-1-2"), _event("runcoach-p1-1-3")]
    diff = diff_window("p1", desired, [], {})

    assert len(diff.to_create) == 2
    assert diff.to_delete_ids == []
    assert diff.unchanged == 0
    assert set(diff.next_hashes) == {"runcoach-p1-1-2", "runcoach-p1-1-3"}


def test_diff_leaves_unchanged_days_alone():
    event = _event("runcoach-p1-1-2")
    remote = [{"id": 11, "external_id": "runcoach-p1-1-2"}]
    diff = diff_window("p1", [event], remote, {"runcoach-p1-1-2": event_hash(event)})

    assert diff.to_create == []
    assert diff.to_delete_ids == []
    assert diff.unchanged == 1


def test_diff_rewrites_a_changed_day():
    event = _event("runcoach-p1-1-2", description="- 3km")
    remote = [{"id": 11, "external_id": "runcoach-p1-1-2"}]
    diff = diff_window("p1", [event], remote, {"runcoach-p1-1-2": "stale-hash"})

    # Delete then create, because Intervals only re-triggers the watch export on
    # create — an in-place update leaves the old session on the wrist.
    assert diff.to_delete_ids == [11]
    assert [e["external_id"] for e in diff.to_create] == ["runcoach-p1-1-2"]


def test_diff_recreates_a_day_missing_from_the_calendar():
    event = _event("runcoach-p1-1-2")
    # Stored hash matches, but the event is gone: the runner deleted it inside
    # Intervals. "Keep my watch in sync" means putting it back.
    diff = diff_window("p1", [event], [], {"runcoach-p1-1-2": event_hash(event)})

    assert [e["external_id"] for e in diff.to_create] == ["runcoach-p1-1-2"]
    assert diff.unchanged == 0


def test_diff_deletes_our_ghosts():
    remote = [{"id": 11, "external_id": "runcoach-p1-1-9"}]
    diff = diff_window("p1", [], remote, {"runcoach-p1-1-9": "whatever"})

    assert diff.to_delete_ids == [11]
    assert "runcoach-p1-1-9" not in diff.next_hashes


def test_diff_never_touches_events_belonging_to_anyone_else():
    """The property the whole delete branch rests on.

    Every one of these is in the window and absent from the plan, which is
    exactly the shape of a ghost — the only thing separating them is ownership.
    """
    remote = [
        {"id": 1, "external_id": "runcoach-a-different-plan-1-2"},
        {"id": 2, "external_id": "some-other-app-42"},
        {"id": 3, "external_id": None},
        {"id": 4},
        {"id": 5, "external_id": "runcoach-p1extra-1-2"},  # prefix-adjacent
        "not even a dict",
    ]
    diff = diff_window("p1", [], remote, {})

    assert diff.to_delete_ids == []
    assert diff.to_create == []


def test_diff_deletes_duplicate_copies_of_our_own_event():
    # Two events under one id means a previous delete didn't land. Rewriting
    # both back to a single copy is how the mirror self-heals.
    event = _event("runcoach-p1-1-2")
    remote = [
        {"id": 11, "external_id": "runcoach-p1-1-2"},
        {"id": 12, "external_id": "runcoach-p1-1-2"},
    ]
    diff = diff_window("p1", [event], remote, {"runcoach-p1-1-2": event_hash(event)})

    assert sorted(diff.to_delete_ids) == [11, 12]
    assert len(diff.to_create) == 1


def test_diff_keeps_hashes_for_days_outside_the_window():
    # The window rolls forward; a day we mirrored last week must not lose its
    # record just because it is no longer in range.
    event = _event("runcoach-p1-1-2")
    stored = {"runcoach-p1-1-2": event_hash(event), "runcoach-p1-9-3": "older"}
    diff = diff_window(
        "p1", [event], [{"id": 11, "external_id": "runcoach-p1-1-2"}], stored
    )

    assert diff.next_hashes["runcoach-p1-9-3"] == "older"


# ---------------------------------------------------------------------------
# Derived UI state
# ---------------------------------------------------------------------------


def test_sessions_behind_counts_unmirrored_days():
    assert sessions_behind(_plan(hashes={})) == 2


def test_sessions_behind_is_zero_once_everything_is_mirrored():
    plan = _plan(hashes={})
    from app.core.training.watch_mirror import events_in_window

    plan.watch_event_hashes = {
        e["external_id"]: event_hash(e) for e in events_in_window(plan)
    }
    assert sessions_behind(plan) == 0


def test_sessions_behind_is_zero_when_sync_is_off():
    # Nothing is "behind" if the runner never asked us to mirror it.
    assert sessions_behind(_plan(hashes={}, enabled=False)) == 0


def test_synced_day_keys_is_empty_without_stored_hashes():
    assert synced_day_keys(_plan()) == set()


def test_synced_day_keys_marks_only_days_matching_what_we_pushed():
    from app.core.training.watch_mirror import build_event

    plan = _plan()
    day_two = plan.plan_data[0]["daily_workouts"][1]
    event = build_event(plan, 1, 2, day_two)
    plan.watch_event_hashes = {event["external_id"]: event_hash(event)}

    assert synced_day_keys(plan) == {(1, 2)}


def test_synced_day_keys_drops_a_day_once_the_plan_changes():
    from app.core.training.watch_mirror import build_event

    plan = _plan()
    day_two = plan.plan_data[0]["daily_workouts"][1]
    event = build_event(plan, 1, 2, day_two)
    plan.watch_event_hashes = {event["external_id"]: event_hash(event)}

    # Shorten the session: the watch still holds the old one, so the card must
    # stop claiming this day is on the wrist.
    day_two["distance"] = 3.0
    assert synced_day_keys(plan) == set()


def test_synced_day_keys_spans_weeks_beyond_the_mirror_window():
    from app.core.training.watch_mirror import build_event

    plan = _Plan(
        [
            {
                "week": 6,
                "daily_workouts": [{"day": 2, "type": "easy", "distance": 8.0}],
            }
        ],
        start=date.today() - timedelta(days=7),
    )
    event = build_event(plan, 6, 2, plan.plan_data[0]["daily_workouts"][0])
    plan.watch_event_hashes = {event["external_id"]: event_hash(event)}

    # Manually pushed days outside the rolling window still show as sent.
    assert synced_day_keys(plan) == {(6, 2)}
