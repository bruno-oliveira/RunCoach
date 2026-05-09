from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.services.fitness.readiness_scoring import score_mountain_simulation


def _run(
    *,
    when: datetime,
    duration_min: float,
    workout_type: str,
    plan_id: str = "p1",
    effort: int | None = None,
    distance_km: float = 10.0,
    elevation_gain_m: float = 0.0,
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


def test_mountain_simulation_none_when_not_flat_training():
    result = score_mountain_simulation(
        plan_data=[],
        runs=[],
        start_date=date(2026, 1, 1),
        current_week=2,
        is_trail=True,
        training_terrain="hilly",
        target_elevation_gain_m=1800,
        plan_id="p1",
    )
    assert result is None


def test_mountain_simulation_scores_execution_from_runs():
    start = date(2026, 1, 1)
    plan_data = [
        {
            "week": 1,
            "vertical_simulation": {
                "uphill_effort_min": 40,
                "downhill_eccentric_min": 25,
                "hike_run_transition_reps": 6,
            },
        },
        {
            "week": 2,
            "vertical_simulation": {
                "uphill_effort_min": 45,
                "downhill_eccentric_min": 28,
                "hike_run_transition_reps": 7,
            },
        },
    ]
    runs = [
        _run(
            when=datetime.combine(start + timedelta(days=2), datetime.min.time()),
            duration_min=60,
            workout_type="interval",
            effort=8,
        ),
        _run(
            when=datetime.combine(start + timedelta(days=6), datetime.min.time()),
            duration_min=90,
            workout_type="long",
            effort=7,
        ),
        _run(
            when=datetime.combine(start + timedelta(days=10), datetime.min.time()),
            duration_min=55,
            workout_type="tempo",
            effort=7,
        ),
    ]

    result = score_mountain_simulation(
        plan_data=plan_data,
        runs=runs,
        start_date=start,
        current_week=2,
        is_trail=True,
        training_terrain="flat",
        target_elevation_gain_m=2200,
        plan_id="p1",
    )

    assert result is not None
    assert result["score"] > 0
    assert result["planned"]["uphill_effort_min"] == 85
    assert result["completion_pct"]["uphill"] > 0


def test_mountain_simulation_filters_other_plan_runs():
    start = date(2026, 1, 1)
    plan_data = [{
        "week": 1,
        "vertical_simulation": {
            "uphill_effort_min": 30,
            "downhill_eccentric_min": 20,
            "hike_run_transition_reps": 4,
        },
    }]
    runs = [
        _run(
            when=datetime.combine(start + timedelta(days=1), datetime.min.time()),
            duration_min=60,
            workout_type="tempo",
            plan_id="other",
            effort=8,
        ),
    ]

    result = score_mountain_simulation(
        plan_data=plan_data,
        runs=runs,
        start_date=start,
        current_week=1,
        is_trail=True,
        training_terrain="flat",
        target_elevation_gain_m=1200,
        plan_id="p1",
    )

    assert result is not None
    assert result["actual"]["uphill_effort_min"] == 0
    assert result["actual"]["hike_run_transition_reps"] == 0
