"""End-to-end router test for the backyard ultra form path.

A backyard submission posts a loop count, not a distance. What matters here is
that the whole round trip survives it: the derived projection reaches the
generator, the runner's own numbers reach the stored row, and every surface
downstream still talks about loops.
"""

from app.models import TrainingPlan


def _post(client, **overrides):
    data = {
        "current_km": "70",
        "target_distance": "backyard",
        "weeks": "20",
        "max_runs_per_week": "5",
        "is_backyard": "on",
        "backyard_target_loops": "24",
        "backyard_loop_km": "6.706",
        "backyard_loop_elevation_gain_m": "0",
        "body_weight_kg": "70",
        "plan_mode": "distance",
    }
    data.update(overrides)
    return client.post("/generate-plan", data=data, follow_redirects=False)


class TestBackyardFormSubmission:
    def test_a_backyard_submission_creates_a_plan(self, client, test_db):
        response = _post(client)
        assert response.status_code == 303
        plan_url = response.headers.get("location")
        assert plan_url and plan_url.startswith("/plan/")

    def test_the_stored_row_keeps_the_loop_count_not_just_the_projection(
        self, client, test_db
    ):
        _post(client, backyard_target_loops="30", weeks="24", current_km="80")
        plan = (
            test_db.query(TrainingPlan).order_by(TrainingPlan.created_at.desc()).first()
        )
        assert plan.is_backyard is True
        assert plan.backyard_target_loops == 30
        assert plan.backyard_loop_km == 6.706
        # And the projection the engine trained against is still there.
        assert plan.is_trail is True
        assert plan.target_distance_km > 100

    def test_the_stored_row_can_rebuild_its_own_profile(self, client, test_db):
        _post(client, backyard_loop_elevation_gain_m="120")
        plan = (
            test_db.query(TrainingPlan).order_by(TrainingPlan.created_at.desc()).first()
        )
        profile = plan.backyard_profile()
        assert profile.target_loops == 24
        assert profile.loop_elevation_gain_m == 120
        assert profile.tier == "night"

    def test_the_plan_page_talks_in_loops_not_in_the_projection(self, client, test_db):
        response = _post(client)
        view = client.get(response.headers["location"])
        assert view.status_code == 200
        assert "24 loops" in view.text
        # The clamped 160.9 km projection is an implementation detail; it must
        # never be presented as the race the runner entered.
        assert "160.9 km Trail" not in view.text

    def test_the_plan_page_shows_the_rest_budget(self, client, test_db):
        response = _post(client)
        view = client.get(response.headers["location"])
        assert "The Hour" in view.text
        assert "Turnaround" in view.text
        assert "/km" in view.text

    def test_the_plan_page_carries_the_corral_routine(self, client, test_db):
        response = _post(client)
        view = client.get(response.headers["location"])
        assert "The Turnaround" in view.text
        assert "2 min whistle" in view.text
        assert "In the corral" in view.text

    def test_the_plan_page_carries_the_hourly_fuelling_schedule(self, client, test_db):
        response = _post(client)
        view = client.get(response.headers["location"])
        assert "Hourly Fuelling" in view.text
        assert "g/h" in view.text
        assert "Sodium" in view.text

    def test_the_race_protocol_is_stored_as_a_backyard_one(self, client, test_db):
        _post(client)
        plan = (
            test_db.query(TrainingPlan).order_by(TrainingPlan.created_at.desc()).first()
        )
        protocol = plan.race_protocol_data
        assert protocol["is_backyard"] is True
        assert protocol["corral_routine"]
        assert protocol["hourly_fuelling"]
        # No split table: every loop is the same distance at the same pace.
        assert protocol["pacing_splits"] == []

    def test_the_plan_page_surfaces_a_simulation_week(self, client, test_db):
        response = _post(client)
        view = client.get(response.headers["location"])
        assert "Simulation" in view.text
        assert "loops this week" in view.text

    def test_the_stored_plan_is_labelled_by_loop_count_not_distance(
        self, client, test_db
    ):
        from app.contexts.plan.plan_type_registry import display_label

        _post(client)
        plan = (
            test_db.query(TrainingPlan).order_by(TrainingPlan.created_at.desc()).first()
        )
        assert display_label(plan) == "24-Loop Backyard"

    def test_regenerating_the_same_goal_returns_the_same_plan(self, client, test_db):
        first = _post(client)
        second = _post(client)
        assert first.headers["location"] == second.headers["location"]

    def test_a_different_loop_count_is_a_different_plan(self, client, test_db):
        """36 and 48 loops project to the same clamped distance."""
        first = _post(client, backyard_target_loops="36", weeks="28", current_km="95")
        second = _post(
            client,
            backyard_target_loops="48",
            weeks="30",
            current_km="120",
            max_runs_per_week="6",
        )
        assert first.headers["location"] != second.headers["location"]


class TestBackyardFormRejections:
    def test_a_missing_loop_count_is_rejected(self, client, test_db):
        response = _post(client, backyard_target_loops="")
        assert response.status_code == 200
        assert "loops" in response.text.lower()

    def test_a_non_numeric_loop_count_is_rejected(self, client, test_db):
        response = _post(client, backyard_target_loops="lots")
        assert response.status_code == 200
        assert "whole number" in response.text.lower()

    def test_too_few_weeks_is_rejected_with_a_loop_count_message(self, client, test_db):
        response = _post(client, weeks="10")
        assert response.status_code == 200
        assert "24 loops" in response.text

    def test_too_little_base_is_rejected(self, client, test_db):
        response = _post(client, current_km="25")
        assert response.status_code == 200
        assert "24-loop" in response.text

    def test_too_few_runs_per_week_is_rejected(self, client, test_db):
        response = _post(client, max_runs_per_week="3")
        assert response.status_code == 200
        assert "runs per week" in response.text.lower()

    def test_an_absurd_loop_length_is_rejected(self, client, test_db):
        response = _post(client, backyard_loop_km="42.2")
        assert response.status_code == 200
        assert response.headers.get("location") is None
