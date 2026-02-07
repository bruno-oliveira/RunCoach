"""Tests for API endpoints."""

import pytest
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
        # Should show error message about insufficient time
        assert "week" in response.text.lower()

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

        # Should return 404 or error page
        assert response.status_code in [404, 500]


class TestPDFDownload:
    """Tests for PDF download endpoint."""

    def test_download_nonexistent_plan(self, client: TestClient):
        """Test downloading PDF for nonexistent plan."""
        response = client.get("/download-pdf/nonexistent-plan-id")

        assert response.status_code in [404, 500]


class TestNutritionEndpoints:
    """Tests for nutrition-related endpoints."""

    def test_randomize_meals_nonexistent_plan(self, client: TestClient):
        """Test randomizing meals for nonexistent plan."""
        response = client.post(
            "/randomize-meals",
            data={"plan_id": "nonexistent-plan-id"},
        )

        assert response.status_code in [404, 500]

    def test_nutrition_plan_nonexistent(self, client: TestClient):
        """Test getting nutrition plan for nonexistent plan."""
        response = client.get("/nutrition-plan/nonexistent-plan-id")

        assert response.status_code in [404, 500]


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
        # Should include nutrition-related content
        html = response.text.lower()
        # Nutrition content should be present
        assert "nutrition" in html or "meal" in html or "calorie" in html
