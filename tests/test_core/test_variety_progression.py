"""Phase-3 variety & progression invariants (P5).

A plan's key workouts must read as a coached progression, not a template on
repeat: no session in consecutive weeks while the pool has alternatives, a
per-plan reuse cap, peak interval work that never regresses below late build,
and a taper sharpener specific to the race distance.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training import workout_steps
from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.key_workout_library.selection import (
    KeyWorkoutRotationState,
    _apply_variety_filter,
    _filter_candidates,
)

QUALITY_TYPES = ("tempo", "interval", "hill")

# Generously-resourced plans: budgets never gate the candidate pools, so the
# variety guarantees genuinely apply.
PLAN_CONFIGS = {
    "5k": dict(current_km=30, target_distance=5.0, weeks=10, max_runs_per_week=4),
    "10k": dict(current_km=40, target_distance=10.0, weeks=12, max_runs_per_week=5),
    "half": dict(current_km=45, target_distance=21.1, weeks=14, max_runs_per_week=5),
    "marathon": dict(
        current_km=50, target_distance=42.2, weeks=16, max_runs_per_week=5
    ),
}


@pytest.fixture(scope="module")
def plans():
    gen = TrainingPlanGenerator()
    return {
        name: gen.generate_plan(vdot=45, **cfg) for name, cfg in PLAN_CONFIGS.items()
    }


def _quality_selections(plan):
    """[(week_number, phase, workout_type, key_workout_id), ...]"""
    out = []
    for week in plan:
        for w in week["daily_workouts"]:
            if w.get("type") in QUALITY_TYPES and w.get("key_workout_id"):
                out.append(
                    (week["week"], week["phase"], w["type"], w["key_workout_id"])
                )
    return out


def _pool_size(workout_type, target_distance, phase):
    return len(_filter_candidates(workout_type, target_distance, phase, None, None))


class TestNoRepeatWindow:
    @pytest.mark.parametrize("name", sorted(PLAN_CONFIGS))
    def test_no_id_in_consecutive_weeks_when_pool_allows(self, plans, name):
        distance = PLAN_CONFIGS[name]["target_distance"]
        selections = _quality_selections(plans[name])
        last_week_for_id = {}
        for week, phase, wtype, wid in selections:
            prev = last_week_for_id.get(wid)
            if prev is not None and week - prev == 1:
                # A pool of one is allowed to repeat — variety can't be
                # conjured from a catalog that has a single eligible session.
                assert _pool_size(wtype, distance, phase) <= 1, (
                    f"{name}: {wid} selected in consecutive weeks "
                    f"{prev} and {week} despite a multi-candidate pool"
                )
            last_week_for_id[wid] = week


class TestPerPlanUseCap:
    @pytest.mark.parametrize("name", sorted(PLAN_CONFIGS))
    def test_loading_phase_ids_used_at_most_twice(self, plans, name):
        """Build/peak pools are deep (>= 4 ids per type), so the cap binds."""
        counts = {}
        for _week, phase, _wtype, wid in _quality_selections(plans[name]):
            if phase in ("build", "peak"):
                counts[wid] = counts.get(wid, 0) + 1
        over = {wid: n for wid, n in counts.items() if n > 2}
        assert not over, f"{name}: sessions over the 2-use cap: {over}"


class TestBuildToPeakProgression:
    @pytest.mark.parametrize("name", ["5k", "10k", "half"])
    def test_peak_interval_work_never_below_last_build_week(self, plans, name):
        """The 4x400 -> 3x500 class of regression: peak must not shrink.

        Marathon is excluded — its peak intentionally drops intervals for
        MP-focused tempo work, so there is no peak interval slot to compare.
        """

        def work_km(w):
            return sum(workout_steps.work_km_by_group(w.get("steps") or []).values())

        build_by_week: dict = {}
        peak_by_week: dict = {}
        for week in plans[name]:
            for w in week["daily_workouts"]:
                if w.get("type") != "interval" or not w.get("key_workout_id"):
                    continue
                if week["phase"] == "build" and not week["is_recovery"]:
                    build_by_week.setdefault(week["week"], []).append(work_km(w))
                elif week["phase"] == "peak":
                    peak_by_week.setdefault(week["week"], []).append(work_km(w))
        assert build_by_week and peak_by_week, f"{name}: expected interval weeks"
        last_build = max(build_by_week[max(build_by_week)])
        for week, works in peak_by_week.items():
            assert max(works) >= last_build - 0.15, (
                f"{name} week {week}: peak interval work set {max(works):.2f} km "
                f"regressed below last build week's {last_build:.2f} km"
            )


class TestTaperVariants:
    EXPECTED = {
        "5k": "taper_5k10k_sharpener",
        "10k": "taper_5k10k_sharpener",
        "half": "taper_half_sharpener",
        "marathon": "taper_marathon_sharpener",
    }

    @pytest.mark.parametrize("name", sorted(PLAN_CONFIGS))
    def test_taper_gets_the_race_specific_sharpener(self, plans, name):
        taper_ids = {
            wid
            for _week, phase, _wtype, wid in _quality_selections(plans[name])
            if phase == "taper"
        }
        assert taper_ids == {self.EXPECTED[name]}, (
            f"{name}: taper sessions {taper_ids} != expected sharpener"
        )

    def test_taper_content_differs_by_race_distance(self, plans):
        assert len(set(self.EXPECTED.values())) == 3

    @pytest.mark.parametrize(
        "distance,expected",
        [
            (5.0, "taper_5k10k_sharpener"),
            (10.0, "taper_5k10k_sharpener"),
            (21.1, "taper_half_sharpener"),
            (42.2, "taper_marathon_sharpener"),
        ],
    )
    def test_selection_serves_taper_tempo_directly(self, distance, expected):
        picked = KeyWorkoutLibrary.get_for_phase(distance, "taper", 0, "tempo")
        assert picked and picked["id"] == expected

    def test_taper_serves_no_interval_sessions(self):
        assert KeyWorkoutLibrary.get_for_phase(5.0, "taper", 0, "interval") is None


class TestVarietyFilterUnit:
    def _pool(self, *ids):
        return [{"id": i} for i in ids]

    def test_recently_used_candidate_is_skipped(self):
        state = KeyWorkoutRotationState()
        state.record_use("a", 5)
        result = _apply_variety_filter(self._pool("a", "b"), state, 6)
        assert [w["id"] for w in result] == ["b"]

    def test_window_expires_after_three_weeks(self):
        state = KeyWorkoutRotationState()
        state.record_use("a", 5)
        result = _apply_variety_filter(self._pool("a", "b"), state, 9)
        assert [w["id"] for w in result] == ["a", "b"]

    def test_single_candidate_pool_is_never_filtered(self):
        state = KeyWorkoutRotationState()
        state.record_use("a", 5)
        result = _apply_variety_filter(self._pool("a"), state, 6)
        assert [w["id"] for w in result] == ["a"]

    def test_use_cap_prefers_fresh_candidates(self):
        state = KeyWorkoutRotationState()
        state.record_use("a", 1)
        state.record_use("a", 5)
        result = _apply_variety_filter(self._pool("a", "b"), state, 10)
        assert [w["id"] for w in result] == ["b"]

    def test_cap_relaxes_when_every_candidate_is_exhausted(self):
        state = KeyWorkoutRotationState()
        for wid in ("a", "b"):
            state.record_use(wid, 1)
            state.record_use(wid, 5)
        result = _apply_variety_filter(self._pool("a", "b"), state, 10)
        assert [w["id"] for w in result] == ["a", "b"]
