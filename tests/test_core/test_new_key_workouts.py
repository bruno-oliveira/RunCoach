"""Tests for the newly added Runna-style key workouts.

Verifies each new session is fully wired (catalog entry + step builder +
distance-scaled prose), reachable through the selection rotation, and produces
steps that stay on the distance budget where the family is budget-pinned.
"""

import pytest

from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library.builders import (
    _KEY_WORKOUT_STEP_BUILDERS,
    build_key_workout_steps,
)
from app.core.training.key_workout_library.rewrites import (
    _DISTANCE_REWRITES,
    _rewrite_key_workout_description,
)
from app.core.training.key_workout_library.selection import KeyWorkoutLibrary
from app.core.training.workout_steps.metrics import _compute_distance_from_steps

NEW_IDS = [
    "5k_thirty_thirties",
    "10k_thirty_thirties",
    "10k_mile_repeats",
    "half_mile_repeats",
    "marathon_mp_blocks",
]

# Families whose step total is pinned to the distance budget (warm-up + reps +
# recovery fill the budget). The 30-30 family is coverage-driven like the other
# fartleks, so its total legitimately settles below the allocated distance.
BUDGET_PINNED = {
    "10k_mile_repeats",
    "half_mile_repeats",
    "marathon_mp_blocks",
}

_BY_ID = {w["id"]: w for w in WORKOUTS}


@pytest.mark.parametrize("wid", NEW_IDS)
def test_new_workout_is_fully_wired(wid):
    assert wid in _BY_ID, f"{wid} missing from catalog"
    assert wid in _KEY_WORKOUT_STEP_BUILDERS, f"{wid} missing a step builder"
    assert wid in _DISTANCE_REWRITES, f"{wid} missing a distance rewrite"
    w = _BY_ID[wid]
    for field in ("name", "structure", "description", "rationale", "pace_zone"):
        assert w.get(field), f"{wid} missing {field}"


@pytest.mark.parametrize("wid", NEW_IDS)
def test_new_workout_builds_scaled_steps(wid):
    w = _BY_ID[wid]
    base = w["distances"][0]
    # Exercise a couple of plausible assigned distances (a key workout is sized
    # to the day's allocation, not the race distance).
    for d in (round(base * 0.6, 1), round(min(base, 14) * 0.8, 1)):
        if d <= 0:
            continue
        steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
        assert steps, f"{wid} produced no steps at {d}km"
        steps_km = _compute_distance_from_steps(steps)
        assert steps_km > 0
        if wid in BUDGET_PINNED:
            assert abs(steps_km - d) <= 0.3, (
                f"{wid}: steps {steps_km:.2f} != budget {d} at {d}km"
            )


@pytest.mark.parametrize("wid", NEW_IDS)
def test_description_rep_count_matches_steps(wid):
    """The scaled prose must cite the same rep count the steps execute."""
    w = _BY_ID[wid]
    d = round(w["distances"][0] * 0.7, 1)
    steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
    desc = _rewrite_key_workout_description(w["description"], wid, d)
    work = next(s for s in steps if s["kind"] == "run")
    reps = work.get("repeat", 1)
    assert f"{reps} x" in desc or f"{reps} ×" in desc, (
        f"{wid}: prose '{desc}' does not cite {reps} reps"
    )


def test_new_workouts_reachable_in_rotation():
    cases = [
        (5.0, "interval", "5k_thirty_thirties"),
        (10.0, "interval", "10k_thirty_thirties"),
        (10.0, "tempo", "10k_mile_repeats"),
        (21.1, "interval", "half_mile_repeats"),
        (42.2, "tempo", "marathon_mp_blocks"),
    ]
    for dist, wtype, expected in cases:
        reachable = {
            w["id"]
            for wip in range(12)
            if (w := KeyWorkoutLibrary.get_for_phase(dist, "build", wip, wtype))
        }
        assert expected in reachable, f"{expected} never selected for {dist} {wtype}"
