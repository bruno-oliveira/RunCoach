"""Tests for treadmill prescriptions and weekly vertical actuals."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.core.training.trail_profile import classify_trail
from app.core.training.vertical_simulation import (
    attach_treadmill_prescriptions,
    compute_weekly_vertical_actuals,
)


def _sim(uphill_min=60, simulated_uphill_m=720, elevation_class="hilly"):
    return {
        "enabled": True,
        "race_elevation_class": elevation_class,
        "race_m_per_km": 40.0,
        "simulated_uphill_m": simulated_uphill_m,
        "uphill_effort_min": uphill_min,
        "downhill_eccentric_min": int(round(uphill_min * 0.6)),
        "hike_run_transition_reps": 6,
        "guidance": "Use stairs and incline treadmill.",
    }


def _workout(wtype, duration_min=45, distance=8.0):
    return {"type": wtype, "duration_min": duration_min, "distance": distance}


class TestTreadmillPrescription:
    def test_no_op_when_training_terrain_not_flat(self):
        profile = classify_trail(20.0, 1200.0)  # hilly mountainous-ish race
        workouts = [_workout("tempo")]
        attach_treadmill_prescriptions(workouts, _sim(), profile, "hilly")
        assert "treadmill_prescription" not in workouts[0]

    def test_no_op_when_race_profile_flat(self):
        profile = classify_trail(15.0, 50.0)  # flat trail
        workouts = [_workout("tempo")]
        attach_treadmill_prescriptions(workouts, _sim(elevation_class="flat"), profile, "flat")
        assert "treadmill_prescription" not in workouts[0]

    def test_no_op_when_simulation_disabled(self):
        profile = classify_trail(20.0, 1200.0)
        workouts = [_workout("tempo")]
        attach_treadmill_prescriptions(workouts, None, profile, "flat")
        assert "treadmill_prescription" not in workouts[0]

    def test_attaches_to_eligible_types_only(self):
        profile = classify_trail(20.0, 1200.0)  # hilly
        workouts = [
            _workout("easy"),
            _workout("tempo"),
            _workout("interval"),
            _workout("long", duration_min=150),
            _workout("rest", duration_min=0, distance=0),
        ]
        attach_treadmill_prescriptions(workouts, _sim(uphill_min=80), profile, "flat")
        assert "treadmill_prescription" not in workouts[0]  # easy
        assert "treadmill_prescription" in workouts[1]
        assert "treadmill_prescription" in workouts[2]
        assert "treadmill_prescription" in workouts[3]
        assert "treadmill_prescription" not in workouts[4]  # rest

    def test_steeper_grade_for_mountainous(self):
        hilly_profile = classify_trail(20.0, 900.0)  # 45 m/km -> hilly
        mountainous_profile = classify_trail(20.0, 1200.0)  # 60 m/km -> mountainous

        hilly_w = [_workout("interval")]
        mountainous_w = [_workout("interval")]
        attach_treadmill_prescriptions(hilly_w, _sim(), hilly_profile, "flat")
        attach_treadmill_prescriptions(
            mountainous_w, _sim(elevation_class="mountainous"), mountainous_profile, "flat",
        )
        assert mountainous_w[0]["treadmill_prescription"]["incline_pct"] > hilly_w[0]["treadmill_prescription"]["incline_pct"]

    def test_incline_minutes_capped_by_session_duration(self):
        profile = classify_trail(20.0, 1200.0)
        # Single short tempo session shouldn't consume the whole 200-min budget.
        workouts = [_workout("tempo", duration_min=30)]
        attach_treadmill_prescriptions(workouts, _sim(uphill_min=200), profile, "flat")
        rx = workouts[0]["treadmill_prescription"]
        assert rx["incline_minutes"] <= 18  # 60% of 30 min

    def test_total_simulated_m_within_budget_envelope(self):
        profile = classify_trail(25.0, 1250.0)  # hilly
        workouts = [
            _workout("tempo", duration_min=40),
            _workout("interval", duration_min=50),
            _workout("long", duration_min=120),
        ]
        sim = _sim(uphill_min=90, simulated_uphill_m=1080)
        attach_treadmill_prescriptions(workouts, sim, profile, "flat")
        total_m = sum(
            w.get("treadmill_prescription", {}).get("simulated_m", 0) for w in workouts
        )
        # Per-session caps and per-type weights can leave headroom; we just
        # confirm we don't massively overshoot the weekly target.
        assert total_m <= int(sim["simulated_uphill_m"] * 1.25)
        assert total_m > 0


def _run(
    *,
    when,
    duration_min,
    workout_type,
    plan_id="p1",
    effort=None,
    distance_km=10.0,
    elevation_gain_m=0.0,
):
    return SimpleNamespace(
        date=when,
        duration_minutes=duration_min,
        workout_type=workout_type,
        training_plan_id=plan_id,
        perceived_effort=effort,
        distance_km=distance_km,
        elevation_gain_m=elevation_gain_m,
    )


class TestWeeklyVerticalActuals:
    def test_empty_when_no_simulation_enabled(self):
        plan_data = [{"week": 1, "vertical_simulation": None}]
        result = compute_weekly_vertical_actuals(plan_data, [], date(2026, 1, 1))
        assert result == {}

    def test_returns_zeros_for_weeks_without_matching_runs(self):
        plan_data = [
            {"week": 1, "vertical_simulation": {"enabled": True}},
            {"week": 2, "vertical_simulation": {"enabled": True}},
        ]
        result = compute_weekly_vertical_actuals(plan_data, [], date(2026, 1, 1))
        assert result == {
            1: {"uphill_min": 0, "downhill_min": 0, "transitions": 0},
            2: {"uphill_min": 0, "downhill_min": 0, "transitions": 0},
        }

    def test_buckets_runs_by_week(self):
        start = date(2026, 1, 5)  # Monday
        plan_data = [
            {"week": 1, "vertical_simulation": {"enabled": True}},
            {"week": 2, "vertical_simulation": {"enabled": True}},
        ]
        runs = [
            _run(
                when=datetime.combine(start + timedelta(days=2), datetime.min.time()),
                duration_min=60,
                workout_type="interval",
                effort=8,
            ),
            _run(
                when=datetime.combine(start + timedelta(days=9), datetime.min.time()),
                duration_min=90,
                workout_type="long",
                effort=7,
            ),
        ]
        result = compute_weekly_vertical_actuals(plan_data, runs, start, training_plan_id="p1")
        assert result[1]["uphill_min"] > 0
        assert result[1]["transitions"] >= 2
        assert result[2]["uphill_min"] > 0
        # Week 1 interval session should produce more uphill minutes than the
        # easier long-effort week, despite the long run being longer.
        assert result[1]["transitions"] > result[2]["transitions"]

    def test_filters_by_plan_id(self):
        start = date(2026, 1, 5)
        plan_data = [{"week": 1, "vertical_simulation": {"enabled": True}}]
        runs = [
            _run(
                when=datetime.combine(start + timedelta(days=1), datetime.min.time()),
                duration_min=60,
                workout_type="interval",
                effort=8,
                plan_id="other-plan",
            ),
        ]
        result = compute_weekly_vertical_actuals(
            plan_data, runs, start, training_plan_id="p1",
        )
        assert result[1]["uphill_min"] == 0
