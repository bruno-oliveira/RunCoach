"""Canonical rep distances (Phase 2a of the quality-workout overhaul).

Rep sessions must prescribe round-number reps chosen from a canonical ladder
("4 × 1 km", "3 × 1.6 km") with the count filling the budget — never a
budget-divided rep ("4 × 1.7 km") and never a shrunken identity ("1000s"
rendered as "3 × 0.5 km"). The taper cruise variant degrades to a strides
sharpener instead of sub-800 m reps, and pyramid sessions carry their real
ladder shape in the steps.
"""

import re

import pytest

from app.core.training.key_workout_library.builders import build_key_workout_steps
from app.core.training.key_workout_library.rewrites import (
    _CANONICAL_REP_LADDERS,
    _CANONICAL_SPECS,
    _rewrite_key_workout_description,
    canonical_reps,
)
from app.core.training.key_workout_library.selection import (
    _KEY_WORKOUT_MIN_BUDGET_KM,
    KeyWorkoutLibrary,
    _filter_candidates,
)
from app.core.training.workout_steps import (
    build_tempo_steps,
    compute_distance_from_steps_checked,
    tempo_cruise_plan,
)

# Distances (km) exercised per converted session — at and above its selection
# budget floor, so every case is one the selector could actually assign.
_SAMPLE_OFFSETS = (0.0, 1.5, 4.0)


def _sample_distances(wid):
    floor = _KEY_WORKOUT_MIN_BUDGET_KM.get(wid, 5.0)
    return [round(floor + off, 1) for off in _SAMPLE_OFFSETS]


def _work_step(steps):
    return next(s for s in steps if s["kind"] == "run")


class TestCanonicalRepsHelper:
    def test_pinned_rep_is_honoured(self):
        rep, count = canonical_reps(3400, "vo2max", rep_m=1000, min_reps=3, max_reps=6)
        assert rep == 1000
        assert count == 3

    def test_count_fills_budget_up_to_max(self):
        rep, count = canonical_reps(9000, "vo2max", rep_m=1000, min_reps=3, max_reps=6)
        assert (rep, count) == (1000, 6)

    def test_unpinned_prefers_longest_canonical_rep(self):
        rep, count = canonical_reps(6000, "cruise", min_reps=3, max_reps=6)
        assert rep == 2000
        assert count == 3

    def test_fallback_below_ladder_uses_smallest_rep(self):
        rep, count = canonical_reps(1200, "cruise", min_reps=2, max_reps=6)
        assert rep == 800
        assert count == 2


class TestConvertedSessionsUseCanonicalReps:
    @pytest.mark.parametrize("wid", sorted(_CANONICAL_SPECS))
    def test_steps_use_canonical_rep_and_price_to_budget(self, wid):
        wk = KeyWorkoutLibrary.get_by_id(wid)
        spec = _CANONICAL_SPECS[wid]
        allowed = (
            {spec["rep_m"]}
            if "rep_m" in spec
            else set(_CANONICAL_REP_LADDERS[spec["family"]])
        )
        for d in _sample_distances(wid):
            steps = build_key_workout_steps(wk, wk["structure"], d, wk["type"], None)
            work = _work_step(steps)
            assert work["distance_m"] in allowed, (
                f"{wid} at {d}km: rep {work['distance_m']}m is not canonical "
                f"({sorted(allowed)})"
            )
            assert spec["min_reps"] <= work["repeat"] <= spec["max_reps"]
            km, priced = compute_distance_from_steps_checked(steps)
            assert priced, f"{wid} at {d}km: steps not fully priced"
            assert abs(km - d) <= 0.3, f"{wid} at {d}km: steps total {km:.2f} != budget"

    @pytest.mark.parametrize("wid", sorted(_CANONICAL_SPECS))
    def test_prose_cites_the_steps_rep_and_count(self, wid):
        wk = KeyWorkoutLibrary.get_by_id(wid)
        for d in _sample_distances(wid):
            steps = build_key_workout_steps(wk, wk["structure"], d, wk["type"], None)
            work = _work_step(steps)
            desc = _rewrite_key_workout_description(wk["description"], wid, d)
            assert f"{work['repeat']} " in desc and (
                f"{work['repeat']} x" in desc or f"{work['repeat']} broken" in desc
            ), f"{wid} at {d}km: prose does not cite {work['repeat']} reps: {desc}"
            rep_m = work["distance_m"]
            accepted = {f"{rep_m}m", f"{rep_m / 1000:.1f}km"}
            assert any(t in desc for t in accepted), (
                f"{wid} at {d}km: prose cites none of {accepted}: {desc}"
            )

    def test_named_1000s_sessions_never_shrink_their_rep(self):
        """A session named "1000s" prescribes 1000 m reps at any budget."""
        for wid in ("5k_vo2max_1000s", "10k_vo2max_1000s"):
            wk = KeyWorkoutLibrary.get_by_id(wid)
            for d in _sample_distances(wid):
                steps = build_key_workout_steps(
                    wk, wk["structure"], d, wk["type"], None
                )
                assert _work_step(steps)["distance_m"] == 1000

    def test_selector_skips_1000s_below_three_rep_budget(self):
        """Sub-floor slots must not select the session (then shrink it)."""
        candidates = _filter_candidates("interval", 5.0, "build", None, None, 5.0)
        assert "5k_vo2max_1000s" not in {w["id"] for w in candidates}
        candidates = _filter_candidates("interval", 5.0, "build", None, None, 6.0)
        assert "5k_vo2max_1000s" in {w["id"] for w in candidates}


class TestTaperCruiseSharpener:
    def test_small_budget_becomes_strides_sharpener(self):
        for d in (2.5, 3.5, 4.0):
            assert tempo_cruise_plan(d)["sharpener"]
            steps = build_tempo_steps(d, None, variant=1)
            kinds = [s["kind"] for s in steps]
            assert "strides" in kinds, f"no strides step at {d}km: {kinds}"
            assert all(s.get("pace_zone") != "T" for s in steps), (
                f"sharpener at {d}km still contains threshold work"
            )

    def test_real_budget_keeps_cruise_reps_at_800m_plus(self):
        for d in (6.0, 8.0, 10.0):
            plan = tempo_cruise_plan(d)
            assert not plan["sharpener"]
            assert plan["rep_m"] >= 800
            steps = build_tempo_steps(d, None, variant=1)
            work = _work_step(steps)
            assert work["distance_m"] == plan["rep_m"]


class TestPyramidShapes:
    def _run_values(self, steps, key):
        return [s[key] for s in steps if s["kind"] == "run"]

    def _assert_pyramid(self, values, wid):
        peak = values.index(max(values))
        assert 0 < peak < len(values) - 1, f"{wid}: no interior peak in {values}"
        assert values[: peak + 1] == sorted(values[: peak + 1]), values
        assert values[peak:] == sorted(values[peak:], reverse=True), values

    def test_10k_pyramid_steps_carry_the_ladder(self):
        wk = KeyWorkoutLibrary.get_by_id("10k_pyramid_intervals")
        for d in (7.0, 9.0, 12.0):
            steps = build_key_workout_steps(wk, wk["structure"], d, wk["type"], None)
            rungs = self._run_values(steps, "distance_m")
            self._assert_pyramid(rungs, "10k_pyramid_intervals")
            desc = _rewrite_key_workout_description(wk["description"], wk["id"], d)
            cited = [int(m) for m in re.findall(r"(\d+)m", desc)]
            assert cited == rungs, (
                f"prose pattern {cited} != step rungs {rungs} at {d}km"
            )

    @pytest.mark.parametrize("wid", ["trail_hill_pyramid", "trail_flat_pyramid"])
    def test_duration_pyramids_carry_the_ladder(self, wid):
        wk = KeyWorkoutLibrary.get_by_id(wid)
        for d in (6.5, 8.0, 11.0):
            steps = build_key_workout_steps(wk, wk["structure"], d, wk["type"], None)
            rungs = self._run_values(steps, "duration_s")
            self._assert_pyramid(rungs, wid)
            desc = _rewrite_key_workout_description(wk["description"], wid, d)
            cited = re.search(r"((?:\d+, )+\d+) minutes", desc)
            assert cited, f"{wid}: prose cites no minute pattern: {desc}"
            assert [int(x) * 60 for x in cited.group(1).split(", ")] == rungs
