"""Daniels intensity-volume caps: no session overdoses I/R/T work.

Guards the tuning constants (``MAX_WORK_SHARE_BY_ZONE`` etc.), the step-level
enforcement (``fit_steps_to_intensity_caps``), and — end to end — that
generated road and performance plans keep every quality session's work set
and day total inside the weekly-share ceilings.
"""

import pytest

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.key_workout_library.rewrites import (
    _rolling_400_reps,
    _thirty_thirty_reps,
)
from app.core.training.tuning import (
    MAX_QUALITY_DAY_SHARE,
    MAX_WORK_ABS_KM_BY_ZONE,
    MAX_WORK_SHARE_BY_ZONE,
    MIN_CAPPED_WORK_KM,
    MIN_QUALITY_DAY_CAP_KM,
)
from app.core.training.workout_steps.metrics import (
    exempt_work_km,
    fit_steps_to_intensity_caps,
    work_km_by_group,
)
from app.core.training.workout_steps.primitives import _step

QUALITY_TYPES = {"tempo", "interval", "hill", "vo2max", "race_pace", "fartlek"}

# Grid snapping / one-decimal rounding slack on top of each cap.
_SLACK_KM = 0.35


def _allowed_work(group: str, weekly_km: float) -> float:
    return max(
        MIN_CAPPED_WORK_KM,
        min(
            weekly_km * MAX_WORK_SHARE_BY_ZONE[group],
            MAX_WORK_ABS_KM_BY_ZONE[group],
        ),
    )


def _assert_week_within_caps(week: dict, label: str) -> None:
    weekly_km = week.get("total_km") or 0
    if weekly_km <= 0:
        return
    for wo in week.get("daily_workouts", []):
        if wo.get("type") not in QUALITY_TYPES:
            continue
        steps = wo.get("steps") or []
        if not steps:
            continue
        groups = work_km_by_group(steps)
        for group, km in groups.items():
            assert km <= _allowed_work(group, weekly_km) + _SLACK_KM, (
                f"{label} wk{week['week']} {wo['type']} "
                f"({wo.get('key_workout_id') or 'generic'}): {group}-work "
                f"{km:.1f}km exceeds cap for {weekly_km}km week"
            )
        # Day-share cap applies to intensity-led key-workout sessions (the
        # enforcement point); M/E-dominated sessions are exempt by design.
        if wo.get("key_workout_id") and sum(groups.values()) > exempt_work_km(steps):
            day_cap = max(MIN_QUALITY_DAY_CAP_KM, weekly_km * MAX_QUALITY_DAY_SHARE)
            assert (wo.get("distance") or 0) <= day_cap + 0.5, (
                f"{label} wk{week['week']} {wo['type']} "
                f"({wo.get('key_workout_id')}): day {wo.get('distance')}km "
                f"exceeds {MAX_QUALITY_DAY_SHARE:.0%} of {weekly_km}km week"
            )


class TestFitStepsToIntensityCaps:
    def _interval_steps(self, reps: int):
        return [
            _step("warmup", "wu", distance_m=1500),
            _step("run", f"{reps} × 1000 m", distance_m=1000, repeat=reps,
                  pace_zone="I", effort="hard"),
            _step("recovery", "jog", distance_m=400, repeat=reps - 1,
                  pace_zone="E"),
            _step("cooldown", "cd", distance_m=1500),
        ]

    def test_caps_interval_work_to_weekly_share(self):
        steps = fit_steps_to_intensity_caps(self._interval_steps(8), 40.0)
        # 8% of 40 km = 3.2 km of I-work allowed.
        assert sum(work_km_by_group(steps).values()) <= 3.2 + _SLACK_KM

    def test_leaves_compliant_session_untouched(self):
        steps = self._interval_steps(3)
        assert fit_steps_to_intensity_caps(steps, 60.0) == steps

    def test_never_caps_below_minimal_stimulus(self):
        # Tiny weekly volume: the floor keeps a minimal complete session.
        steps = fit_steps_to_intensity_caps(self._interval_steps(3), 12.0)
        assert sum(work_km_by_group(steps).values()) >= MIN_CAPPED_WORK_KM - 1.1

    def test_zero_weekly_km_is_a_no_op(self):
        steps = self._interval_steps(8)
        assert fit_steps_to_intensity_caps(steps, 0) == steps


class TestRepCeilings:
    def test_thirty_thirties_capped(self):
        for d in (5.0, 8.0, 12.0, 20.0):
            assert _thirty_thirty_reps(d) <= 16

    def test_rolling_400s_capped(self):
        for d in (5.0, 8.0, 12.0, 20.0):
            assert _rolling_400_reps(d) <= 8


class TestGeneratedPlansRespectCaps:
    @pytest.mark.parametrize(
        "current_km,target,weeks,runs",
        [
            (25.0, 5.0, 8, 4),
            (30.0, 10.0, 10, 5),
            (45.0, 21.1, 12, 5),
            (55.0, 42.2, 16, 5),
        ],
    )
    def test_road_plans(self, current_km, target, weeks, runs):
        plan = TrainingPlanGenerator().generate_plan(
            current_km=current_km,
            target_distance=target,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        for week in plan:
            _assert_week_within_caps(week, f"road-{target}")

    @pytest.mark.parametrize(
        "target,cur_pace,goal_pace,weeks,weekly",
        [
            (10.0, 5.5, 5.0, 10, 40.0),
            (21.1, 5.8, 5.4, 12, 45.0),
        ],
    )
    def test_performance_plans(self, target, cur_pace, goal_pace, weeks, weekly):
        plan = PerformancePlanGenerator().generate_plan(
            target, cur_pace, goal_pace, weeks, weekly, 5
        )
        for week in plan["weekly_plans"]:
            _assert_week_within_caps(week, f"perf-{target}")
