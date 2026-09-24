"""Previous/next session links on the day page skip rest days and plan edges."""

from app.web.routers.plan_view import _neighbour_sessions

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _plan():
    return [
        {
            "week": 1,
            "daily_workouts": [
                {"id": "a", "day": 1, "type": "easy"},
                {"id": "r", "day": 2, "type": "rest"},
                {"id": "b", "day": 3, "type": "interval", "key_workout_name": "400s"},
            ],
        },
        {"week": 2, "daily_workouts": [{"id": "c", "day": 1, "type": "long"}]},
    ]


def test_neighbours_skip_rest_days():
    prev_day, next_day = _neighbour_sessions(_plan(), "b", DAYS)
    assert prev_day == {"id": "a", "label": "Easy", "when": "Week 1 · Mon"}
    assert next_day == {"id": "c", "label": "Long", "when": "Week 2 · Mon"}


def test_plan_edges_have_no_neighbour():
    assert _neighbour_sessions(_plan(), "a", DAYS)[0] is None
    assert _neighbour_sessions(_plan(), "c", DAYS)[1] is None


def test_unknown_workout_has_no_neighbours():
    assert _neighbour_sessions(_plan(), "zzz", DAYS) == (None, None)
