"""Safety guards shared across adaptation flows."""

from dataclasses import dataclass

from app.contexts.plan.adaptation.safety import enforce_future_growth_cap, enforce_week_structure


@dataclass
class _Workout:
    workout_type: str
    distance_km: float
    key_workout_id: str | None = None


@dataclass
class _Week:
    id: str
    total_km: float


def test_enforce_week_structure_caps_long_run_dominance():
    workouts = [
        _Workout("easy", 5.0),
        _Workout("easy", 5.0),
        _Workout("tempo", 6.0),
        _Workout("long", 20.0),
    ]

    changed = enforce_week_structure(workouts, target_distance=30.0, phase="build")
    assert changed

    total = sum(w.distance_km for w in workouts)
    long_d = next(w.distance_km for w in workouts if w.workout_type == "long")
    assert long_d / total <= 0.55 + 0.01


def test_enforce_week_structure_allows_higher_peak_ratio_for_flat_trail():
    workouts = [
        _Workout("easy", 5.0),
        _Workout("easy", 6.0),
        _Workout("tempo", 1.0),
        _Workout("long", 20.0),
    ]

    changed = enforce_week_structure(
        workouts,
        target_distance=28.0,
        phase="peak",
        is_trail=True,
        target_elevation_gain_m=1050.0,
        training_terrain="flat",
    )

    assert not changed
    total = sum(w.distance_km for w in workouts)
    long_d = next(w.distance_km for w in workouts if w.workout_type == "long")
    assert long_d / total <= 0.65 + 0.01


def test_enforce_future_growth_cap_holds_non_recovery_weeks_to_ten_percent():
    weeks = {
        5: _Week(id="w5", total_km=32.0),
        6: _Week(id="w6", total_km=38.0),
        7: _Week(id="w7", total_km=45.0),
    }
    workouts = {
        "w5": [_Workout("easy", 8.0), _Workout("tempo", 6.0), _Workout("long", 18.0)],
        "w6": [_Workout("easy", 10.0), _Workout("tempo", 7.0), _Workout("long", 21.0)],
        "w7": [_Workout("easy", 12.0), _Workout("tempo", 8.0), _Workout("long", 25.0)],
    }
    pd_week = {
        5: {"is_recovery": False, "total_km": 32.0},
        6: {"is_recovery": False, "total_km": 38.0},
        7: {"is_recovery": False, "total_km": 45.0},
    }

    enforce_future_growth_cap(
        [5, 6, 7],
        weeks,
        workouts,
        pd_week,
        high_water_seed=30.0,
    )

    high_water = 30.0
    for wk_num in (5, 6, 7):
        total = weeks[wk_num].total_km
        assert total <= high_water * 1.10 + 0.1
        if total > high_water:
            high_water = total
