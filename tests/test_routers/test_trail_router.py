"""End-to-end router test for the new trail/ultra form path."""


class TestTrailFormSubmission:
    """POST /generate-plan with is_trail + elevation produces a trail plan."""

    def test_custom_50km_trail_creates_trail_plan(self, client, test_db):
        # Numeric target_distance + is_trail=on is the legacy/transitional shape.
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "40",
                "target_distance": "50",
                "weeks": "16",
                "max_runs_per_week": "5",
                "is_trail": "on",
                "target_elevation_gain_m": "200",  # 4 m/km → flat
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        plan_url = response.headers.get("location")
        assert plan_url and plan_url.startswith("/plan/")

        view = client.get(plan_url)
        assert view.status_code == 200
        assert "50.0 km Trail" in view.text or "50 km Trail" in view.text
        assert "200 m vert" in view.text

    def test_custom_trail_sentinel_resolves_from_trail_distance_km(
        self, client, test_db
    ):
        # Current form shape: dropdown stays on "trail", actual km comes from
        # the trail_distance_km field. Server resolves the sentinel.
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "40",
                "target_distance": "trail",
                "trail_distance_km": "50",
                "weeks": "16",
                "max_runs_per_week": "5",
                "is_trail": "on",
                "target_elevation_gain_m": "1234",  # non-multiple-of-50
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        view = client.get(response.headers["location"])
        assert view.status_code == 200
        assert "50.0 km Trail" in view.text or "50 km Trail" in view.text
        assert "1234 m vert" in view.text or "1,234 m vert" in view.text

    def test_custom_100mi_trail_creates_long_ultra_plan(self, client, test_db):
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "80",
                "target_distance": "163",
                "weeks": "32",
                "max_runs_per_week": "6",
                "is_trail": "on",
                "target_elevation_gain_m": "6000",
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        view = client.get(response.headers["location"])
        assert "163" in view.text
        assert "6000 m vert" in view.text or "6,000 m vert" in view.text

    def test_legacy_30km_form_still_works(self, client, test_db):
        # The old form path (target=30, optional terrain) still goes through.
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "25",
                "target_distance": "30",
                "weeks": "12",
                "max_runs_per_week": "4",
                "terrain": "flat",
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        view = client.get(response.headers["location"])
        # Should render as a trail plan (auto-migrated by the schema shim).
        assert "Trail" in view.text

    def test_custom_trail_below_floor_rejected(self, client, test_db):
        # 7 km is below the 8 km trail floor.
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "20",
                "target_distance": "7",
                "weeks": "8",
                "max_runs_per_week": "4",
                "is_trail": "on",
                "target_elevation_gain_m": "200",
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        # Validation error → 200 with error message in the rendered home page.
        assert response.status_code in (200, 422)
        assert "trail" in response.text.lower() or "8" in response.text

    def test_road_5k_form_still_works(self, client, test_db):
        # The road path is unchanged by the trail mode addition.
        response = client.post(
            "/generate-plan",
            data={
                "current_km": "10",
                "target_distance": "5",
                "weeks": "8",
                "max_runs_per_week": "3",
                "body_weight_kg": "70",
                "plan_mode": "distance",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
