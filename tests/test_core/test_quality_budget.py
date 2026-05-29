"""Fit-the-plan-around-the-session: under-dose quality slots are floored to a
meaningful dose when the week can afford it, otherwise demoted to easy — never
scheduled as a token thin-stimulus quality session.
"""

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.weekly_plan_builder import (
    resolve_low_budget_quality,
)
from app.core.training.quality_caps import QUALITY_MIN_DOSE_KM


def _is_duration_defined(workout: dict) -> bool:
    """A session whose work is time-based (e.g. 8×30 s hill sprints): its
    distance is intrinsic, not budget-driven, so it's legitimately short and
    exempt from the meaningful-distance dose floor.
    """
    for s in workout.get("steps", []):
        if s.get("kind") in ("warmup", "cooldown", "rest", "recovery"):
            continue
        if s.get("duration_s") and not s.get("distance_m"):
            return True
    return False


class TestResolveLowBudgetQuality:
    def test_floors_under_dose_slot_when_affordable(self):
        # Big easy budget → borrow the shortfall and keep the slot at its dose.
        distribution = {"easy": 2, "interval": 1, "long": 1}
        quality = {"interval": 1.6}
        resolve_low_budget_quality(
            distribution,
            quality,
            remaining_km=24.0,
            long_run_distance=15.0,
            target_distance=30.0,
            phase="build",
        )
        assert quality["interval"] >= QUALITY_MIN_DOSE_KM["interval"]
        assert distribution["interval"] == 1  # slot kept

    def test_demotes_token_sliver_when_unaffordable(self):
        # A true token sliver (< hard floor) that can't be grown → demote.
        distribution = {"easy": 1, "interval": 1, "long": 1}
        quality = {"interval": 1.2}
        resolve_low_budget_quality(
            distribution,
            quality,
            remaining_km=4.5,
            long_run_distance=8.0,
            target_distance=10.0,
            phase="build",
        )
        assert "interval" not in quality  # slot dropped
        assert distribution["interval"] == 0
        assert distribution["easy"] == 2  # flowed back to easy

    def test_keeps_modest_session_when_unaffordable(self):
        # Under-dose but above the token floor, with no easy budget to borrow:
        # keep the modest-but-real session rather than demote it.
        distribution = {"interval": 1, "long": 1}  # no easy runs to borrow from
        quality = {"interval": 2.5}
        resolve_low_budget_quality(
            distribution,
            quality,
            remaining_km=3.0,
            long_run_distance=6.0,
            target_distance=5.0,
            phase="build",
        )
        assert quality == {"interval": 2.5}  # kept at budget
        assert distribution["interval"] == 1

    def test_meaningful_slot_left_untouched(self):
        distribution = {"easy": 2, "interval": 1, "long": 1}
        quality = {"interval": 5.0}
        resolve_low_budget_quality(
            distribution,
            quality,
            remaining_km=24.0,
            long_run_distance=15.0,
            target_distance=30.0,
            phase="build",
        )
        assert quality == {"interval": 5.0}
        assert distribution == {"easy": 2, "interval": 1, "long": 1}


class TestGeneratedPlansHaveNoTokenQuality:
    """End-to-end: no scheduled quality session is below its meaningful dose,
    and the weekly total still equals the sum of its daily distances.
    """

    def test_no_thin_quality_and_totals_preserved(self):
        for current_km, target, weeks, runs in [
            (18.0, 10.0, 8, 4),  # low base → exercises demotion
            (35.0, 21.1, 12, 5),
            (45.0, 42.2, 16, 5),
        ]:
            plan = TrainingPlanGenerator().generate_plan(
                current_km=current_km,
                target_distance=target,
                weeks=weeks,
                max_runs_per_week=runs,
            )
            for week in plan:
                daily = week.get("daily_workouts", [])
                # The meaningful-dose floor applies in build/peak; base/taper
                # quality is intentionally light (strides, short hill sprints).
                if week.get("phase") in ("build", "peak"):
                    for w in daily:
                        if w.get("type") in ("tempo", "interval", "hill"):
                            dose = QUALITY_MIN_DOSE_KM.get(w["type"], 0)
                            dist = w.get("distance", 0) or 0
                            # Distance-based quality must hit a meaningful dose;
                            # duration-defined sessions (hill sprints, etc.) are
                            # intrinsically short and exempt.
                            assert (
                                dist == 0
                                or dist >= dose - 0.5
                                or _is_duration_defined(w)
                            ), (
                                f"{target}km wk{week['week']} {w['type']} "
                                f"dist={dist} < dose {dose}"
                            )
                summed = round(sum((w.get("distance") or 0) for w in daily), 1)
                assert abs(summed - round(week.get("total_km", 0) or 0, 1)) <= 0.1
