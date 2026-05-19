from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.contexts.plan.plan_data_enricher import enrich_plan_data_with_ids


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


def test_enricher_surfaces_baseline_for_adjusted_easy_run_without_steps(test_db):
    """Regression: easy runs have no `steps`, but the auto-adjuster does
    touch them. The "adjusted from X km" chip in workout_item.html depends
    on `baseline_distance` being on the view-context workout dict. Before
    the fix, the no-steps early-continue skipped that assignment for
    exactly the rows the adjuster touched."""
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=1,
        workout_type="easy",
        distance_km=4.4,
        intensity="low",
        baseline_distance_km=5.2,
    )
    test_db.add(dw)
    test_db.commit()

    plan_data = [{
        "week": 1,
        "daily_workouts": [{
            "day": 1,
            "type": "easy",
            "distance": 4.4,
            # No `steps` — the typical easy-run shape.
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    assert workout["id"] == dw.id
    assert workout.get("baseline_distance") == 5.2


def test_enricher_omits_baseline_when_unchanged(test_db):
    """If baseline matches current distance, no chip should appear — so
    the enricher must not surface a baseline_distance field at all."""
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=1,
        workout_type="easy",
        distance_km=5.0,
        intensity="low",
        baseline_distance_km=5.0,
    )
    test_db.add(dw)
    test_db.commit()

    plan_data = [{
        "week": 1,
        "daily_workouts": [{
            "day": 1,
            "type": "easy",
            "distance": 5.0,
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    assert "baseline_distance" not in workout


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


def test_enricher_reconciles_total_km_to_daily_sum(test_db):
    """The week chip (`total_km`) must equal the sum of the per-workout
    `distance` values the template will render. The enricher can rewrite
    per-workout distances (steps-derived recompute, key-workout minimum
    bump) without touching the stored chip, so the reconciliation has to
    happen at the end of the enricher pass."""
    plan, week = _seed_plan(test_db)
    # No DailyWorkout rows needed — the test exercises the in-memory
    # reconciliation path, not the DB-id lookup.
    plan_data = [
        {
            "week": 1,
            # Stored total is deliberately wrong: matches NEITHER the
            # pre-render distances NOR the post-render distances.
            "total_km": 99.9,
            "daily_workouts": [
                {"day": 1, "type": "easy", "distance": 8.5},
                {"day": 2, "type": "easy", "distance": 6.0},
                {"day": 3, "type": "long", "distance": 12.0},
                {"day": 4, "type": "rest", "distance": 0},
            ],
        },
        {
            "week": 2,
            "total_km": 0.0,
            "daily_workouts": [
                {"day": 1, "type": "easy", "distance": 5.0},
                {"day": 2, "type": "tempo", "distance": 7.0},
            ],
        },
    ]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)

    assert enriched[0]["total_km"] == round(8.5 + 6.0 + 12.0 + 0.0, 1)
    assert enriched[1]["total_km"] == round(5.0 + 7.0, 1)
    # The reconciliation must not undo the per-workout distances.
    assert [wo["distance"] for wo in enriched[0]["daily_workouts"]] == [
        8.5, 6.0, 12.0, 0,
    ]


def test_enricher_total_km_follows_steps_distance_overwrite(test_db):
    """When the enricher rewrites a workout's `distance` from its `steps`,
    the new `total_km` reflects the rewritten value, not the original."""
    plan, week = _seed_plan(test_db)
    dw = DailyWorkout(
        weekly_plan_id=week.id,
        day_of_week=1,
        workout_type="interval",
        distance_km=2.0,
        intensity="high",
        baseline_distance_km=2.0,
    )
    test_db.add(dw)
    test_db.commit()

    # `steps` imply ~3 km (500m warmup + 3x500m intervals + 500m cooldown
    # = 2.5 km of distance steps, plus duration steps). The stored
    # `distance` is 2.0 km, which differs by more than the 0.2 km
    # tolerance — so the enricher will overwrite it.
    plan_data = [{
        "week": 1,
        "total_km": 2.0,
        "daily_workouts": [{
            "day": 1,
            "type": "interval",
            "distance": 2.0,
            "steps": [
                {"kind": "warmup", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
                {"kind": "run", "distance_m": 500, "repeat": 3, "pace_zone": "I"},
                {"kind": "cooldown", "distance_m": 500, "repeat": 1, "pace_zone": "E"},
            ],
        }],
    }]

    enriched = enrich_plan_data_with_ids(plan_data, plan.id, test_db)
    workout = enriched[0]["daily_workouts"][0]

    # Enricher must have rewritten the distance from steps (single workout).
    assert workout["distance"] != 2.0
    # Chip must match the rewritten distance.
    assert enriched[0]["total_km"] == round(workout["distance"], 1)
