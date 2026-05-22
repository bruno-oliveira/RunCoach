"""Tests for API endpoints."""

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestHomeEndpoint:
    """Tests for home page endpoint."""

    def test_home_page(self, client: TestClient):
        """Test home page returns HTML."""
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestPlanGeneration:
    """Tests for plan generation endpoint."""

    def test_generate_5k_plan(self, client: TestClient):
        """Test generating a 5K training plan."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 20.0,
                "target_distance": 5,
                "weeks": 8,
            },
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should show plan page, not error
        assert "Week 1" in response.text or "week" in response.text.lower()

    def test_generate_10k_plan(self, client: TestClient):
        """Test generating a 10K training plan."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 25.0,
                "target_distance": 10,
                "weeks": 10,
            },
        )

        assert response.status_code == 200

    def test_generate_half_marathon_plan(self, client: TestClient):
        """Test generating a half marathon training plan."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 35.0,
                "target_distance": 21.1,
                "weeks": 12,
            },
        )

        assert response.status_code == 200

    def test_generate_marathon_plan(self, client: TestClient):
        """Test generating a marathon training plan."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 50.0,
                "target_distance": 42.2,
                "weeks": 16,
            },
        )

        assert response.status_code == 200

    def test_insufficient_weeks_error(self, client: TestClient):
        """Test error when weeks are insufficient for distance."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 30.0,
                "target_distance": 42.2,  # Marathon
                "weeks": 4,  # Too few weeks
            },
        )

        assert response.status_code == 200  # Returns HTML with error
        # Should show specific error message about insufficient time
        html = response.text.lower()
        assert "week" in html
        assert "error" in html or "insufficient" in html or "minimum" in html

    def test_inadequate_base_mileage_error(self, client: TestClient):
        """Test error when base mileage is too low."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 5.0,  # Very low mileage
                "target_distance": 42.2,  # Marathon
                "weeks": 16,
            },
        )

        assert response.status_code == 200  # Returns HTML with error
        # Should show error about mileage
        html = response.text.lower()
        assert "error" in html or "mileage" in html or "base" in html

    def test_invalid_current_km(self, client: TestClient):
        """Test error with invalid current km."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": -10,  # Invalid
                "target_distance": 5,
                "weeks": 8,
            },
        )

        # Should handle gracefully
        assert response.status_code in [200, 422]


class TestPlanViewing:
    """Tests for viewing existing plans."""

    def test_view_nonexistent_plan(self, client: TestClient):
        """Test viewing a plan that doesn't exist."""
        response = client.get("/plan/nonexistent-plan-id")

        assert response.status_code == 404


class TestPDFDownload:
    """Tests for PDF download endpoint."""

    def test_download_nonexistent_plan(self, client: TestClient):
        """Test downloading PDF for nonexistent plan."""
        response = client.get("/download-pdf/nonexistent-plan-id")

        assert response.status_code == 404


class TestNutritionEndpoints:
    """Tests for nutrition-related endpoints."""

    def test_randomize_meals_nonexistent_plan(self, client: TestClient):
        """Test randomizing meals for nonexistent plan."""
        response = client.post(
            "/randomize-meals",
            data={"plan_id": "nonexistent-plan-id"},
        )

        assert response.status_code == 404

    def test_nutrition_plan_nonexistent(self, client: TestClient):
        """Test getting nutrition plan for nonexistent plan."""
        response = client.get("/nutrition-plan/nonexistent-plan-id")

        assert response.status_code == 404


class TestPlanCreationAndWorkflow:
    """Integration tests for full plan workflow."""

    def test_create_and_view_plan(self, client: TestClient):
        """Test creating a plan and then viewing it."""
        # Create a plan
        create_response = client.post(
            "/generate-plan",
            data={
                "current_km": 25.0,
                "target_distance": 10,
                "weeks": 8,
            },
        )

        assert create_response.status_code == 200

        # Extract plan_id from response if possible
        # This is a basic integration test - in real tests we'd parse the HTML
        # to get the plan_id and then view it

    def test_plan_has_nutrition_info(self, client: TestClient):
        """Test that generated plan includes nutrition information."""
        response = client.post(
            "/generate-plan",
            data={
                "current_km": 30.0,
                "target_distance": 21.1,
                "weeks": 12,
            },
        )

        assert response.status_code == 200
        html = response.text.lower()
        # Should include actual nutrition data, not just nav references
        assert "calorie" in html or "protein" in html, (
            "Response should contain actual nutrition data (calories or protein)"
        )
        assert "meal" in html, "Response should contain meal suggestions"

    def test_anonymous_fitness_plan_no_limit(self, client: TestClient):
        """Anonymous users should not hit the 3-plan limit on fitness plans."""
        for i in range(4):
            response = client.post(
                "/generate-fitness-plan",
                data={
                    "current_km": 20.0,
                    "weeks": 4,
                    "runs_per_week": 3,
                    "focus_area": "vo2max",
                },
            )
            assert response.status_code == 200, (
                f"Fitness plan #{i + 1} failed with status {response.status_code}. "
                "Anonymous users must not be limited to 3 plans."
            )
            assert (
                "error" not in response.text.lower()
                or "plan_limit" not in response.text.lower()
            ), (
                f"Fitness plan #{i + 1} returned a plan-limit error for an anonymous user."
            )
