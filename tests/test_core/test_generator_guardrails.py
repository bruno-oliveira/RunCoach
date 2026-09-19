"""Guardrail tests for the generator's engine-level input floors and the
trivial-session sweep.

``PlanRequest`` guards web traffic, but ``TrainingPlanGenerator.generate_plan``
is also called directly — backtests, scripts, future endpoints. A sweep over
the distance × frequency × base matrix showed that below-floor inputs don't
just make conservative plans, they *compose into broken ones*: a base the
schema would refuse produced a +21 % ramp breach and a 0.0 km easy card on a
loading week. These tests pin the engine's own refusals and the post-smoothing
sweep that renders drained cards as rest.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.profiles.backyard_profile import (
    backyard_min_weekly_km,
    backyard_min_weeks,
    classify_backyard,
)
from app.core.training.profiles.trail_profile import (
    classify_trail,
    trail_min_weekly_mileage,
    trail_min_weeks,
)
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ValidationException,
)

GEN = TrainingPlanGenerator()

# Card types that ask the runner to run — mirrors the generator's own set.
RUNNING_CARD_TYPES = ("easy", "medium_long", "tempo", "interval", "hill")


def _cards(week, types=RUNNING_CARD_TYPES):
    return [w for w in week.get("daily_workouts", []) if w.get("type") in types]


# ── Engine-level input floors ───────────────────────────────────────────────


class TestEngineRejectsInvalidInputs:
    """The engine must raise the schema's own domain exceptions, not compose
    a broken plan, when called without the schema in front of it."""

    @pytest.mark.parametrize("distance", [25.0, 35.0, 40.0])
    def test_unregistered_road_target_raises(self, distance):
        with pytest.raises(ValidationException):
            GEN.generate_plan(30, distance, 12, 4)

    def test_registered_road_targets_pass(self):
        for distance, weeks in [(5.0, 8), (10.0, 10), (21.1, 12), (42.2, 16)]:
            plan = GEN.generate_plan(30, distance, weeks, 4)
            assert len(plan) == weeks

    def test_below_floor_base_raises(self):
        # 15 km/week is under the marathon floor (25) — this exact input
        # used to generate a plan with a +21 % ramp breach.
        with pytest.raises(InadequateBaseException):
            GEN.generate_plan(15, 42.2, 12, 5)

    def test_thin_5k_base_raises(self):
        with pytest.raises(InadequateBaseException):
            GEN.generate_plan(3, 5.0, 8, 3)

    def test_weeks_below_registry_minimum_raises(self):
        with pytest.raises(InsufficientTimeException):
            GEN.generate_plan(30, 42.2, 10, 4)

    def test_weeks_above_registry_maximum_raises(self):
        with pytest.raises(ValidationException):
            GEN.generate_plan(30, 5.0, 18, 4)

    def test_below_schema_frequency_still_generates(self):
        """Runs-per-week floors are product policy and schema-only: the engine
        composes gracefully at 2-3 runs (the frequency composers and the
        physiological envelope grid both exercise that space), so it must not
        refuse what the schema would."""
        assert GEN.generate_plan(30, 21.1, 12, 2)
        assert GEN.generate_plan(30, 42.2, 16, 3)

    def test_beginner_path_still_reaches_zero_base(self):
        plan = GEN.generate_plan(0, 5.0, 8, 3)
        assert len(plan) == 8

    def test_legacy_30k_trail_promotion_still_works(self):
        # 30.0 without a trail profile is auto-promoted to trail before the
        # road-target rejection — the back-compat path must survive it.
        plan = GEN.generate_plan(20, 30.0, 12, 4)
        assert len(plan) == 12

    def test_trail_base_floor_enforced(self):
        profile = classify_trail(50.0, 2000.0)
        below = trail_min_weekly_mileage(profile) - 5
        with pytest.raises(InadequateBaseException):
            GEN.generate_plan(
                below, 50.0, trail_min_weeks(profile), 5, trail_profile=profile
            )

    def test_trail_weeks_floor_enforced(self):
        profile = classify_trail(50.0, 2000.0)
        with pytest.raises(InsufficientTimeException):
            GEN.generate_plan(
                trail_min_weekly_mileage(profile),
                50.0,
                trail_min_weeks(profile) - 1,
                5,
                trail_profile=profile,
            )

    def test_backyard_base_floor_enforced(self):
        profile = classify_backyard(12, loop_elevation_gain_m=0.0)
        below = backyard_min_weekly_km(profile) - 5
        with pytest.raises(InadequateBaseException):
            GEN.generate_plan(
                below, 0, backyard_min_weeks(profile), 5, backyard_profile=profile
            )


# ── Trivial-session sweep ───────────────────────────────────────────────────


class TestNoTrivialCards:
    """No week the runner executes may carry a card they cannot."""

    def test_race_week_has_no_drained_easy_cards(self):
        # 5K at base 30-40 with 5 runs used to render two 0.0 km "easy"
        # cards on the race-week calendar.
        for base in (30, 35, 40):
            plan = GEN.generate_plan(base, 5.0, 6, 5)
            for w in _cards(plan[-1]):
                assert (w.get("distance") or 0) > 0, (
                    f"base {base}: race week carries a {w.get('type')} card "
                    f"with distance {w.get('distance')}"
                )

    def test_10k_race_week_no_drained_easy_cards(self):
        plan = GEN.generate_plan(50, 10.0, 6, 5)
        for w in _cards(plan[-1]):
            assert (w.get("distance") or 0) > 0

    @pytest.mark.parametrize(
        "combo",
        [
            (10.0, 6, 15, 5),  # had a 0.3 km easy card in its peak week
            (5.0, 11, 15, 3),  # had a 2.2 km tempo in week 10
            (21.1, 8, 15, 3),  # had a 2.3 km tempo in week 7
            (5.0, 16, 15, 3),  # had a 2.2 km tempo in week 15
        ],
        ids=[
            "10k-6w-base15-5d",
            "5k-11w-base15-3d",
            "half-8w-base15-3d",
            "5k-16w-base15-3d",
        ],
    )
    def test_no_sub_viable_cards_on_executed_weeks(self, combo):
        distance, weeks, base, runs = combo
        plan = GEN.generate_plan(base, distance, weeks, runs)
        for week in plan[:-1]:
            for w in _cards(week):
                dist = w.get("distance") or 0
                if w.get("type") in ("tempo", "interval", "hill"):
                    assert dist >= 2.5, (
                        f"week {week['week']} day {w.get('day')}: token "
                        f"{w.get('type')} of {dist} km survived the sweep"
                    )
                else:
                    assert dist >= 1.0, (
                        f"week {week['week']} day {w.get('day')}: {w.get('type')} "
                        f"card of {dist} km is not a coherent run and was "
                        "not swept to rest"
                    )

    @pytest.mark.parametrize(
        "combo",
        [
            (10.0, 6, 15, 5),
            (5.0, 11, 15, 3),
            (21.1, 8, 15, 3),
        ],
    )
    def test_sweep_never_empties_a_week(self, combo):
        """The sweep converts trivial cards to rest — it must never leave a
        week with nothing runnable (that would fail the structure guard, but
        assert it here directly so the failure names this cause)."""
        distance, weeks, base, runs = combo
        plan = GEN.generate_plan(base, distance, weeks, runs)
        for week in plan:
            assert _cards(week), f"week {week['week']} has no runnable session"

    def test_token_quality_becomes_easy_not_rest(self):
        """A 2.2 km "tempo" was jogging duration all along: the sweep relabels
        it as the easy run it effectively was, keeping the runner's frequency."""
        distance, weeks, base, runs = 5.0, 11, 15, 3
        plan = GEN.generate_plan(base, distance, weeks, runs)
        for week in plan[:-1]:
            running = [
                w
                for w in week["daily_workouts"]
                if w.get("type") not in ("rest", "recovery")
            ]
            # Frequency is never eroded by the quality downgrade itself.
            assert len(running) >= 3, f"week {week['week']}: {len(running)} runs"
            for w in running:
                assert (
                    w.get("type") not in ("tempo", "interval", "hill")
                    or (w.get("distance") or 0) >= 2.5
                ), (
                    f"week {week['week']}: token {w.get('type')} of "
                    f"{w.get('distance')} km survived the sweep"
                )

    def test_micro_plan_keeps_its_templated_frequency(self):
        """A 5 km/week base split three ways is small *by design* — every run
        sits below the easy floor, and the sweep must not butcher it into a
        2-run week. The week's long anchor (~2.5 km) marks the honest dose."""
        plan = GEN.generate_plan(5, 5.0, 6, 3)
        for week in plan[:-1]:
            running = [
                w
                for w in week["daily_workouts"]
                if w.get("type") not in ("rest", "recovery")
            ]
            assert len(running) >= 3, (
                f"week {week['week']}: micro plan eroded to {len(running)} runs"
            )

    def test_long_runs_are_never_swept(self):
        """The long anchor is load-bearing: every executed week keeps exactly
        one long run even when the sweep is active."""
        for distance, weeks, base, runs in [
            (5.0, 6, 15, 2),
            (10.0, 6, 15, 5),
            (21.1, 8, 15, 3),
        ]:
            plan = GEN.generate_plan(base, distance, weeks, runs)
            for week in plan[:-1]:
                longs = [w for w in week["daily_workouts"] if w.get("type") == "long"]
                assert len(longs) == 1, (
                    f"{distance}km/{weeks}w: week {week['week']} has "
                    f"{len(longs)} long runs"
                )


# ── Sweep coherence with the rest of the pipeline ──────────────────────────


class TestSweepCoherence:
    """The sweep edits cards; the plan's own bookkeeping must follow."""

    @pytest.mark.parametrize(
        "combo",
        [(5.0, 6, 30, 5), (10.0, 6, 15, 5), (21.1, 8, 15, 3)],
    )
    def test_total_km_matches_summed_cards_after_sweep(self, combo):
        distance, weeks, base, runs = combo
        plan = GEN.generate_plan(base, distance, weeks, runs)
        for week in plan:
            summed = round(
                sum(w.get("distance", 0) or 0 for w in week["daily_workouts"]), 1
            )
            assert week["total_km"] == summed, (
                f"week {week['week']}: total_km {week['total_km']} != "
                f"summed {summed} — the sweep edited cards without re-totaling"
            )

    def test_extreme_valid_combo_still_generates(self):
        """The smallest legal base at the largest legal window and frequency
        sits exactly on every floor — the guards must not over-refuse it."""
        plan = GEN.generate_plan(5, 5.0, 16, 6)
        assert len(plan) == 16
