"""Catalog invariants for the key-workout library.

The library is a hand-authored table, and its ``type`` field is load-bearing:
it decides which slot a session is offered for. A session filed under the
wrong type is not a cosmetic error — the weekly builder hands it that slot's
budget, and the distance-rewrite machinery then rewrites the session to fit.
That is how a 15 km "Cut-Down Long Run" (typed ``interval``) ended up on a
4 km interval slot, rewritten to "three 1.3 km segments", and how a 30 km
easy fuelling long run (typed ``tempo``) became an 8 km continuous easy run
occupying the week's only tempo session.

The tests here are catalog-level: they read the table directly, so they fail
on the authoring mistake itself rather than waiting for a particular
(distance, phase, week) combination to surface it in a generated plan.
"""

import re

import pytest

from app.core.training.key_workout_library import _WORKOUTS
from app.core.training.key_workout_library.selection import _filter_candidates

QUALITY_TYPES = ("tempo", "interval", "hill")

# Above this, a session is long-run scale and cannot be honestly executed in a
# quality slot — a road quality day is ~4-9 km, and the largest trail quality
# session is a hill/hike block well under this.
LONG_RUN_SCALE_KM = 14.0


def _cited_distances_km(workout: dict) -> list[float]:
    """Every "N km" figure the session's own prose commits to."""
    text = f"{workout['structure']} {workout['description']}"
    return [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*km", text)]


def _cites_hours(workout: dict) -> bool:
    text = f"{workout['structure']} {workout['description']}"
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?\s*)?hours?", text))


@pytest.mark.parametrize(
    "workout",
    [w for w in _WORKOUTS if w["type"] in QUALITY_TYPES],
    ids=lambda w: w["id"],
)
def test_quality_sessions_are_not_long_run_scale(workout):
    """A session in a quality slot must fit a quality slot.

    Sessions prescribing 14 km+ or "2.5-3 hours" belong on the ``long`` slot.
    Left typed as tempo/interval they are handed a quality budget and rewritten
    down to a quarter of their prescribed size, which discards the session's
    whole point (a 30 km fuelling rehearsal is not a rehearsal at 8 km).
    """
    cited = _cited_distances_km(workout)
    biggest = max(cited) if cited else 0.0
    assert biggest < LONG_RUN_SCALE_KM, (
        f"{workout['id']} is typed '{workout['type']}' but prescribes "
        f"{biggest} km — that is a long run, not a quality session"
    )
    assert not _cites_hours(workout), (
        f"{workout['id']} is typed '{workout['type']}' but is defined in hours "
        "— a time-on-feet session belongs on the long-run slot"
    )


@pytest.mark.parametrize("workout", _WORKOUTS, ids=lambda w: w["id"])
def test_every_session_declares_a_known_type(workout):
    assert workout["type"] in (*QUALITY_TYPES, "long")


class TestPoolsAreDeep:
    """Every slot the scheduler can fill needs somewhere to draw from.

    An empty pool silently falls back to the generic builders (losing the
    curated session entirely); a pool of one or two repeats the same session
    across a whole phase, which the no-repeat window then cannot prevent. The
    half-marathon interval pool sat at three sessions — with a 2-week no-repeat
    window and a peak that must not regress below build, that was too thin for
    the rotation to hold its own progression invariant.
    """

    # (distance, phase, type) combinations the workout distribution actually
    # schedules for road plans. Hill slots are excluded: road distributions
    # never emit them, and flat trail training converts them away.
    ROAD_SLOTS = [
        (5.0, "build", "interval"),
        (5.0, "peak", "interval"),
        (10.0, "build", "interval"),
        (10.0, "build", "tempo"),
        (10.0, "peak", "interval"),
        (10.0, "peak", "tempo"),
        (21.1, "build", "interval"),
        (21.1, "build", "tempo"),
        (21.1, "peak", "interval"),
        (21.1, "peak", "tempo"),
        (42.2, "build", "tempo"),
        (42.2, "build", "interval"),
        (42.2, "peak", "tempo"),
        (42.2, "peak", "interval"),
    ]

    @pytest.mark.parametrize("distance,phase,wtype", ROAD_SLOTS, ids=lambda v: str(v))
    def test_pool_has_room_to_rotate(self, distance, phase, wtype):
        pool = _filter_candidates(wtype, distance, phase, None, None)
        assert len(pool) >= 3, (
            f"{distance}km {phase} {wtype}: only {len(pool)} candidates "
            f"({[w['id'] for w in pool]}) — too thin to rotate without repeats"
        )

    @pytest.mark.parametrize("distance", [21.1, 42.2])
    @pytest.mark.parametrize("phase", ["build", "peak"])
    def test_long_run_variants_exist(self, distance, phase):
        """Half and marathon long runs should vary, not repeat one template."""
        pool = _filter_candidates("long", distance, phase, None, None)
        assert len(pool) >= 3, (
            f"{distance}km {phase} long: only {len(pool)} variants "
            f"({[w['id'] for w in pool]})"
        )
