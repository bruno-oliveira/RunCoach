"""Tests for the pre-submit long-run adequacy endpoint (/assess-long-run).

The endpoint is a pure calculator that mirrors the post-generation banner, so
the live form hint and the plan view stay consistent.
"""

from fastapi.testclient import TestClient


class TestAssessLongRun:
    def test_warns_for_underbuilt_marathon(self, client: TestClient):
        r = client.get(
            "/assess-long-run",
            params={
                "current_km": 25,
                "target_distance": 42.2,
                "weeks": 12,
                "max_runs_per_week": 4,
            },
        )
        assert r.status_code == 200
        warning = r.json()["long_run_warning"]
        assert warning is not None
        assert warning["pct_of_recommended"] < 85
        assert "42.2 km race" in warning["message"]
        assert warning["suggestion"]

    def test_warns_when_frequency_capacity_limits_the_long_run(
        self, client: TestClient
    ):
        """A 4-run marathon week cannot fund the static long-run aim.

        Since the reachability gate (plan_generator), this plan's peak week
        caps at 4 runs x typical session, and its long run tops out around
        72% of the static ~36 km aim. The banner is now *honest* about that
        trade-off instead of silent: the old quiet expectation encoded the
        pre-cap model, whose 76 km peak week was exactly the over-prescription
        the envelope census flagged (road-42.2km long_over 24 -> 12). The
        banner pairs with the frequency advisory ("add a training day"), which
        is the lever that actually buys the long run back.
        """
        r = client.get(
            "/assess-long-run",
            params={
                "current_km": 40,
                "target_distance": 42.2,
                "weeks": 18,
                "max_runs_per_week": 4,
            },
        )
        assert r.status_code == 200
        warning = r.json()["long_run_warning"]
        assert warning is not None
        assert warning["pct_of_recommended"] < 85
        assert warning["suggestion"]

    def test_warns_for_short_trail_runway(self, client: TestClient):
        r = client.get(
            "/assess-long-run",
            params={
                "current_km": 20,
                "target_distance": 28,
                "weeks": 8,
                "max_runs_per_week": 4,
                "is_trail": "true",
                "target_elevation_gain_m": 1000,
            },
        )
        assert r.status_code == 200
        warning = r.json()["long_run_warning"]
        assert warning is not None
        assert "trail race" in warning["message"]

    def test_quiet_for_short_road_races(self, client: TestClient):
        for dist in (10.0, 21.1):
            r = client.get(
                "/assess-long-run",
                params={"current_km": 30, "target_distance": dist, "weeks": 12},
            )
            assert r.status_code == 200
            assert r.json()["long_run_warning"] is None

    def test_bad_input_returns_null_not_error(self, client: TestClient):
        r = client.get(
            "/assess-long-run",
            params={"current_km": 0, "target_distance": 42.2, "weeks": 12},
        )
        assert r.status_code == 200
        assert r.json() == {"long_run_warning": None}
