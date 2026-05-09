from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.services.plans.plan_data_enricher import enrich_plan_data_with_ids


def _seed_plan(test_db):
    user = User(email="enricher@example.com", name="Enricher")
    test_db.add(user)
    test_db.flush()

    plan = TrainingPlan(
        user_id=user.id,
        current_weekly_km=30.0,
        target_distance="30.0",
        weeks_duration=12,
        plan_data=[],
    )
    test_db.add(plan)
    test_db.flush()

    week = WeeklyPlan(training_plan_id=plan.id, week_number=1, total_km=20.0, workout_types={})
    test_db.add(week)
    test_db.flush()

    return plan, week


def test_enricher_repairs_hill_key_workout_distance_floor(test_db):
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=2,
        workout_type="hill",
        distance_km=2.6,
        intensity="high",
        baseline_distance_km=2.6,
        key_workout_id="trail_elevation_repeats",
    )
    test_db.add(dw)
    test_db.commit()

    plan_data = [{
        "week": 1,
        "daily_workouts": [{
            "day": 2,
            "type": "hill",
            "distance": 2.6,
            "key_workout_id": "trail_elevation_repeats",
            "structure": "6 x 3min uphill at hard effort with jog-back recovery",
            "steps": [
                {"kind": "warmup", "distance_m": 650, "repeat": 1, "pace_zone": "E"},
                {"kind": "run", "duration_s": 180, "repeat": 6, "pace_zone": "I"},
                {"kind": "cooldown", "distance_m": 650, "repeat": 1, "pace_zone": "E"},
            ],
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    assert workout["id"] == dw.id
    assert workout["distance"] >= 4.5
    assert "duration_min" not in workout
    assert workout.get("baseline_distance") == 2.6


def test_enricher_sets_short_workout_duration_hint_from_steps(test_db):
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=4,
        workout_type="interval",
        distance_km=2.0,
        intensity="high",
        baseline_distance_km=2.0,
    )
    test_db.add(dw)
    test_db.commit()

    plan_data = [{
        "week": 1,
        "daily_workouts": [{
            "day": 4,
            "type": "interval",
            "distance": 2.0,
            "steps": [
                {"kind": "warmup", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
                {"kind": "run", "duration_s": 180, "repeat": 3, "pace_zone": "I"},
                {"kind": "cooldown", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
            ],
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    assert workout["duration_min"] >= 15


def test_enricher_rebuilds_technical_workout_steps_with_distance(test_db):
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=3,
        workout_type="interval",
        distance_km=2.0,
        intensity="medium",
        baseline_distance_km=2.0,
        key_workout_id="trail_technical_terrain",
    )
    test_db.add(dw)
    test_db.commit()

    plan_data = [{
        "week": 1,
        "daily_workouts": [{
            "day": 3,
            "type": "interval",
            "distance": 2.0,
            "key_workout_id": "trail_technical_terrain",
            "structure": "Run 1.6km at moderate effort, focusing on foot placement",
            "steps": [
                {"kind": "warmup", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
                {"kind": "run", "label": "Find a technical trail", "repeat": 1, "pace_zone": "E"},
                {"kind": "cooldown", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
            ],
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    run_steps = [s for s in workout["steps"] if s.get("kind") == "run"]
    assert any(s.get("distance_m") for s in run_steps)
    assert workout["distance"] >= 4.5
    assert "duration_min" not in workout
