"""Phase 7: trail signals threaded through coaching/readiness/gap-analysis."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.coaching.training_tips import get_tips_for_week
from app.core.training.trail_profile import classify_trail
from app.models import RunLog, TrainingPlan, User
from app.contexts.runner.fitness.gap_analysis_service import _compute_elevation_gap
from app.contexts.runner.fitness.readiness_scoring import build_scenarios


# --- Coaching tips ----------------------------------------------------------

class TestBracketAwareTrainingTips:
    def test_short_bracket_emits_short_specific_tip(self):
        profile = classify_trail(15.0, 500.0)
        tips = get_tips_for_week(1, 15.0, trail_profile=profile)
        assert any("Trail isn't road" in t or "descent" in t.lower() for t in tips)

    def test_standard_bracket_includes_gut_training(self):
        profile = classify_trail(30.0, 1000.0)
        # Cycle through a few weeks to hit the 'eat your first gel' tip.
        joined = " ".join(
            tip for week in range(1, 5)
            for tip in get_tips_for_week(week, 30.0, trail_profile=profile)
        )
        assert "gel" in joined.lower() or "gut" in joined.lower()

    def test_flat_training_tips_avoid_hilly_course_assumptions(self):
        profile = classify_trail(30.0, 1000.0)
        joined = " ".join(
            tip for week in range(1, 5)
            for tip in get_tips_for_week(
                week,
                30.0,
                trail_profile=profile,
                training_terrain="flat",
            )
        ).lower()
        assert "actual race terrain" not in joined
        assert "incline" in joined or "stairs" in joined or "bridge" in joined

    def test_ultra_bracket_introduces_back_to_back(self):
        profile = classify_trail(50.0, 1500.0)
        joined = " ".join(
            tip for week in range(1, 6)
            for tip in get_tips_for_week(week, 50.0, trail_profile=profile)
        )
        assert "back-to-back" in joined.lower()

    def test_long_ultra_introduces_night_running_and_pacers(self):
        profile = classify_trail(163.0, 6000.0)
        joined = " ".join(
            tip for week in range(1, 6)
            for tip in get_tips_for_week(week, 163.0, trail_profile=profile)
        )
        # The long_ultra-only tip vocabulary.
        assert "night" in joined.lower() or "headlamp" in joined.lower()
        assert "crew" in joined.lower() or "abort" in joined.lower()

    def test_road_path_unchanged(self):
        # No trail_profile → falls through to legacy distance tips.
        tips_5k = get_tips_for_week(1, 5.0)
        # Should not surface trail-specific vocabulary.
        joined = " ".join(tips_5k).lower()
        assert "back-to-back" not in joined
        assert "headlamp" not in joined


# --- Race scenarios ---------------------------------------------------------

class TestTrailScenarios:
    def test_scenarios_account_for_elevation(self):
        vdot_data = {"current": 50.0}
        flat = build_scenarios(
            vdot_data, "50.0", target_elevation_gain_m=200.0, trail_runs_count=20,
        )
        mountain = build_scenarios(
            vdot_data, "50.0", target_elevation_gain_m=3000.0, trail_runs_count=20,
        )
        assert flat and mountain
        flat_solid = next(s for s in flat if s["name"] == "Solid")
        mountain_solid = next(s for s in mountain if s["name"] == "Solid")
        # Same VDOT, more vert → slower predicted finish.
        assert mountain_solid["time"] >= flat_solid["time"]

    def test_road_path_unchanged(self):
        vdot_data = {"current": 50.0}
        scenarios = build_scenarios(vdot_data, "42.2")
        assert len(scenarios) == 4
        assert {s["name"] for s in scenarios} == {"Dream", "Solid", "Tough", "Survival"}


# --- Gap analysis: elevation gap --------------------------------------------

class TestElevationGap:
    def _make_plan(self, *, is_trail, target_elev=None):
        plan = TrainingPlan()
        plan.target_distance = "50.0"
        plan.weeks_duration = 16
        plan.is_trail = is_trail
        plan.target_elevation_gain_m = target_elev
        plan.user_id = "u1"
        return plan

    def _runs(self, elevs):
        out = []
        for i, e in enumerate(elevs):
            r = RunLog()
            r.distance_km = 10.0
            r.elevation_gain_m = e
            r.run_date = datetime.now(timezone.utc) - timedelta(days=i)
            out.append(r)
        return out

    def _plan_data(self, week_kms):
        return [{"week": i + 1, "total_km": km} for i, km in enumerate(week_kms)]

    def test_returns_none_for_road_plan(self):
        plan = self._make_plan(is_trail=False)
        result = _compute_elevation_gap(plan, self._plan_data([40, 45]), self._runs([100, 200]), 2)
        assert result is None

    def test_returns_none_when_target_elevation_missing(self):
        plan = self._make_plan(is_trail=True, target_elev=None)
        result = _compute_elevation_gap(plan, self._plan_data([40, 45]), self._runs([100]), 2)
        assert result is None

    def test_on_track_when_actual_matches_apportioned_target(self):
        # 4-week plan, 200 km total, race target 1000 m. Through week 2 (90 km
        # done out of 200) the share is 90/200 = 0.45 → expected = 450 m.
        plan = self._make_plan(is_trail=True, target_elev=1000.0)
        plan_data = self._plan_data([40, 50, 55, 55])
        runs = self._runs([200, 250])  # actual = 450 → on_track
        result = _compute_elevation_gap(plan, plan_data, runs, current_week=2)
        assert result is not None
        assert result["expected_so_far_m"] == 450
        assert result["actual_so_far_m"] == 450
        assert result["verdict"] == "on_track"

    def test_far_behind_when_actual_dwarfed_by_target(self):
        plan = self._make_plan(is_trail=True, target_elev=5000.0)
        plan_data = self._plan_data([40, 50, 55, 55])
        runs = self._runs([100])  # tiny vs ~2250 m expected after 2 weeks
        result = _compute_elevation_gap(plan, plan_data, runs, current_week=2)
        assert result is not None
        assert result["verdict"] == "far_behind"
        assert result["deficit_pct"] > 50
