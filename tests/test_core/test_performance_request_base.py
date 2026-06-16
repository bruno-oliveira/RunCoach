"""Tests for PerformancePlanRequest base-mileage validation guidance.

Performance (time-goal) plans require an established aerobic base. When the
runner is below it the request is rejected, but the guidance should be
actionable: quantify the gap, estimate a safe bridge time, and route the
runner to the distance-goal plan they already qualify for.
"""

import pytest

from app.exceptions import InadequateBaseException
from app.schemas.performance_request import PerformancePlanRequest


def _make(current_weekly_km: float, target_distance: float = 21.1):
    return PerformancePlanRequest(
        target_distance=target_distance,
        current_pace=5.5,
        goal_pace=5.0,
        goal_time="1:45:00",
        weeks=12,
        current_weekly_km=current_weekly_km,
        runs_per_week=4,
    )


class TestPerformanceBaseGuidance:
    def test_accepts_at_or_above_perf_min(self):
        # Half perf_min is 35 km/week.
        req = _make(35)
        assert req.current_weekly_km == 35

    def test_below_perf_min_rejected_with_quantified_gap(self):
        with pytest.raises(InadequateBaseException) as exc:
            _make(30)
        msg = exc.value.user_message
        assert "35" in msg  # required
        assert "30" in msg  # current
        assert "5" in msg  # shortfall

    def test_guidance_estimates_bridge_weeks(self):
        with pytest.raises(InadequateBaseException) as exc:
            _make(30)
        # 30 -> 35 under 10%/week is ~2 weeks.
        assert "2 week" in exc.value.suggestion

    def test_guidance_routes_to_distance_plan_when_eligible(self):
        # 30 km/week clears the Half *distance* floor (15 km) but not perf (35).
        with pytest.raises(InadequateBaseException) as exc:
            _make(30)
        suggestion = exc.value.suggestion
        assert "distance plan" in suggestion
        assert "15" in suggestion  # distance-plan floor surfaced

    def test_guidance_when_below_distance_floor_too(self):
        # 10 km/week is below even the Half distance floor (15 km).
        with pytest.raises(InadequateBaseException) as exc:
            _make(10)
        suggestion = exc.value.suggestion
        assert "distance plan" not in suggestion
        assert "aerobic running" in suggestion or "shorter race" in suggestion
