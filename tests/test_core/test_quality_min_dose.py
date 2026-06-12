"""Quality sessions must be worth running.

Locks in the session-sizing fixes: duration-step pricing must be complete
(no silent zero-priced reps collapsing sessions to warm-up + cool-down),
and build/peak quality slots must carry at least their minimum meaningful
dose. The original bug shipped 1.5 km "interval sessions" whose own
descriptions prescribed ~5 km of running, for 7 of 10 weeks of a 10K plan.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.workout_steps import compute_distance_from_steps_checked

_QUALITY_TYPES = ("tempo", "interval", "hill")

# Floors slightly under QUALITY_MIN_DOSE_KM to allow cap/rounding interplay;
# the point is that no real-volume plan ships token build/peak sessions.
_MIN_BUILD_PEAK_KM = {"tempo": 3.4, "interval": 2.8, "hill": 2.4}

_CONFIGS = [
    pytest.param(
        dict(
            current_km=50, target_distance=42.2, weeks=16, max_runs_per_week=5, vdot=48
        ),
        id="marathon-50km",
    ),
    pytest.param(
        dict(
            current_km=40, target_distance=21.1, weeks=12, max_runs_per_week=4, vdot=45
        ),
        id="half-40km-vdot",
    ),
    pytest.param(
        dict(current_km=40, target_distance=21.1, weeks=12, max_runs_per_week=4),
        id="half-40km-novdot",
    ),
    pytest.param(
        dict(current_km=30, target_distance=10.0, weeks=10, max_runs_per_week=4),
        id="10k-30km",
    ),
    pytest.param(
        dict(current_km=25, target_distance=5.0, weeks=8, max_runs_per_week=4),
        id="5k-25km",
    ),
    pytest.param(
        dict(
            current_km=45,
            target_distance=30.0,
            weeks=18,
            max_runs_per_week=4,
            terrain="hilly",
        ),
        id="trail-45km",
    ),
]


@pytest.fixture(params=_CONFIGS)
def plan(request):
    return TrainingPlanGenerator().generate_plan(**request.param)


class TestQualityMinimumDose:
    def test_build_peak_quality_meets_min_dose(self, plan):
        """No token quality sessions in build/peak at real training volumes."""
        for week in plan:
            if week.get("phase") not in ("build", "peak"):
                continue
            if week.get("is_recovery_week"):
                continue
            for w in week.get("daily_workouts", []):
                wtype = w.get("type")
                if wtype not in _QUALITY_TYPES:
                    continue
                d = w.get("distance", 0) or 0
                if d <= 0 or w.get("duration_min"):
                    continue
                floor = _MIN_BUILD_PEAK_KM[wtype]
                assert d >= floor, (
                    f"week {week['week']} ({week.get('phase')}): {wtype} is "
                    f"{d} km — below the {floor} km meaningful-dose floor"
                )

    def test_no_silent_zero_priced_steps_shrink_sessions(self, plan):
        """Where steps fully price, they must support the card distance.

        A fully priced step list summing far below the displayed distance
        means the reconcile failed; an *incomplete* one must never have been
        used to shrink the session (distance >= priced lower bound holds by
        construction, so only the fully-priced case is asserted).
        """
        for week in plan:
            for w in week.get("daily_workouts", []):
                steps = w.get("steps")
                d = w.get("distance", 0) or 0
                if not steps or d <= 0:
                    continue
                priced_km, complete = compute_distance_from_steps_checked(steps)
                if complete and priced_km > 0:
                    assert abs(d - priced_km) <= 0.2, (
                        f"week {week['week']} {w.get('type')}: card says {d} km "
                        f"but fully-priced steps deliver {priced_km:.2f} km"
                    )

    def test_base_road_tempo_is_a_real_threshold_dose(self, plan):
        """Base tempo slots carry >= ~2 km at T (4 km total), not 1.3 km."""
        for week in plan:
            if week.get("phase") != "base" or week.get("is_recovery_week"):
                continue
            for w in week.get("daily_workouts", []):
                if w.get("type") != "tempo":
                    continue
                d = w.get("distance", 0) or 0
                if d <= 0 or w.get("duration_min"):
                    continue
                assert d >= 3.4, (
                    f"week {week['week']} base tempo is {d} km — below the "
                    f"minimum threshold dose"
                )
