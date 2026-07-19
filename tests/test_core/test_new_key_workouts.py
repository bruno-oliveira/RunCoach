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


# ---------------------------------------------------------------------------
# Runna-inspired tranche: on-off ks, rolling 400s, 2-1-1 ladder, compound
# sets, 5K time trial, race-practice long.
# ---------------------------------------------------------------------------

RUNNA_IDS = [
    "half_on_off_ks",
    "rolling_400s",
    "tempo_2_1_1",
    "intervals_400s_into_200s",
    "intervals_800s_into_400s",
    "time_trial_5k",
    "race_practice_long",
]

# Meter-rep, ladder-with-floats, and split families fill the budget exactly;
# the compound sets and the fixed-distance time trial are prescription-driven.
RUNNA_BUDGET_PINNED = {"half_on_off_ks", "rolling_400s", "race_practice_long"}


@pytest.mark.parametrize("wid", RUNNA_IDS)
def test_runna_workout_is_fully_wired(wid):
    assert wid in _BY_ID, f"{wid} missing from catalog"
    assert wid in _KEY_WORKOUT_STEP_BUILDERS, f"{wid} missing a step builder"
    assert wid in _DISTANCE_REWRITES, f"{wid} missing a distance rewrite"
    w = _BY_ID[wid]
    for field in ("name", "structure", "description", "rationale", "pace_zone"):
        assert w.get(field), f"{wid} missing {field}"


@pytest.mark.parametrize("wid", RUNNA_IDS)
def test_runna_workout_builds_bounded_steps(wid):
    w = _BY_ID[wid]
    for d in (6.0, 8.0, 12.0):
        steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
        assert steps, f"{wid} produced no steps at {d}km"
        steps_km = _compute_distance_from_steps(steps)
        assert steps_km > 0
        if wid in RUNNA_BUDGET_PINNED:
            assert abs(steps_km - d) <= 0.3, (
                f"{wid}: steps {steps_km:.2f} != budget {d} at {d}km"
            )
        elif wid == "tempo_2_1_1":
            # The ladder scales down to fit but never overruns the budget.
            assert steps_km <= d + 0.3, (
                f"{wid}: steps {steps_km:.2f} overrun budget {d}"
            )


def test_on_off_ks_prose_cites_step_rep_count():
    w = _BY_ID["half_on_off_ks"]
    for d in (6.0, 9.8, 12.0):
        steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
        desc = _rewrite_key_workout_description(w["description"], w["id"], d)
        work = next(s for s in steps if s["kind"] == "run")
        assert f"{work['repeat']} x" in desc


def test_compound_sets_prose_cites_both_block_counts():
    for wid, rep_ms in (
        ("intervals_400s_into_200s", (400, 200)),
        ("intervals_800s_into_400s", (800, 400)),
    ):
        w = _BY_ID[wid]
        d = 6.0
        steps = build_key_workout_steps(w, w["structure"], d, w["type"], None)
        desc = _rewrite_key_workout_description(w["description"], wid, d)
        runs = [s for s in steps if s["kind"] == "run"]
        assert [s["distance_m"] for s in runs] == list(rep_ms)
        for s, rep_m in zip(runs, rep_ms):
            assert f"{s['repeat']} x {rep_m}m" in desc, (
                f"{wid}: prose does not cite {s['repeat']} x {rep_m}m: {desc}"
            )


def test_time_trial_holds_5k_literally():
    w = _BY_ID["time_trial_5k"]
    steps = build_key_workout_steps(w, w["structure"], 7.0, w["type"], None)
    tt = next(s for s in steps if s["kind"] == "run")
    assert tt["distance_m"] == 5000


@pytest.mark.parametrize(
    "dist,phase,wtype,wid",
    [
        (21.1, "build", "tempo", "half_on_off_ks"),
        (10.0, "build", "tempo", "rolling_400s"),
        (42.2, "peak", "tempo", "tempo_2_1_1"),
        (5.0, "build", "interval", "intervals_400s_into_200s"),
        (10.0, "peak", "interval", "intervals_800s_into_400s"),
        (21.1, "build", "tempo", "time_trial_5k"),
        (21.1, "peak", "long", "race_practice_long"),
    ],
)
def test_runna_workouts_reachable_in_rotation(dist, phase, wtype, wid):
    reachable = {
        w["id"]
        for wip in range(16)
        for slot in (0, 1)
        if (
            w := KeyWorkoutLibrary.get_for_phase(
                dist, phase, wip, wtype, slot_index=slot
            )
        )
    }
    assert wid in reachable, f"{wid} never selected for {dist} {phase} {wtype}"


class TestRoadDistanceBucketing:
    """Non-canonical road distances draw their band's catalog."""

    def test_28km_road_draws_the_marathon_catalog(self):
        w = KeyWorkoutLibrary.get_for_phase(28.0, "build", 0, "tempo")
        assert w is not None
        assert 42.2 in w["distances"]

    def test_intermediate_road_distance_draws_its_band(self):
        w = KeyWorkoutLibrary.get_for_phase(15.0, "build", 0, "tempo")
        assert w is not None
        assert 21.1 in w["distances"]

    def test_canonical_distances_are_unchanged(self):
        for dist in (5.0, 10.0, 21.1, 42.2):
            w = KeyWorkoutLibrary.get_for_phase(dist, "build", 0, "interval")
            assert w is not None
            assert dist in w["distances"]

    def test_legacy_trail_sentinel_does_not_leak_road_sessions(self):
        reachable = {
            w["id"]
            for wip in range(16)
            if (w := KeyWorkoutLibrary.get_for_phase(30.0, "build", wip, "tempo"))
        }
        road_only = {"half_on_off_ks", "tempo_2_1_1", "marathon_mp_blocks"}
        assert not (reachable & road_only), (
            f"road sessions leaked into the 30km trail sentinel: "
            f"{reachable & road_only}"
        )
