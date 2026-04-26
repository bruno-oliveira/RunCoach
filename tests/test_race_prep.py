"""Smoke tests for the Race Prep feature.

Covers page rendering, GPX analysis, blueprint generation, and GPX download.
Mostly smoke tests since full integration would require mocking GPX parsing,
VDOT calculation, and database runs.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
from app.models.user import User
from app.routers.race_prep import _blueprint_store
from app.services.fit_service import FITService
from app.services.gpx_service import GPXService
from app.services.race_pacing_service import RacePacingService


@pytest.fixture
def race_user(test_db: Session) -> User:
    user = User(
        id="race-user-1",
        email="race@example.com",
        name="Race Test",
        google_id="google-race-1",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def _override_db(test_db: Session):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _set_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override


def _set_optional_user(user: User):
    async def override():
        return user

    app.dependency_overrides[get_optional_user] = override


def _clear_user():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_user, None)


SAMPLE_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test">
  <trk>
    <name>Test Race</name>
    <trkseg>
      <trkpt lat="40.0" lon="-3.0"><ele>600.0</ele></trkpt>
      <trkpt lat="40.001" lon="-2.999"><ele>610.0</ele></trkpt>
      <trkpt lat="40.002" lon="-2.998"><ele>620.0</ele></trkpt>
      <trkpt lat="40.003" lon="-2.997"><ele>615.0</ele></trkpt>
      <trkpt lat="40.004" lon="-2.996"><ele>625.0</ele></trkpt>
      <trkpt lat="40.005" lon="-2.995"><ele>630.0</ele></trkpt>
      <trkpt lat="40.006" lon="-2.994"><ele>635.0</ele></trkpt>
      <trkpt lat="40.007" lon="-2.993"><ele>640.0</ele></trkpt>
      <trkpt lat="40.008" lon="-2.992"><ele>645.0</ele></trkpt>
      <trkpt lat="40.009" lon="-2.991"><ele>650.0</ele></trkpt>
      <trkpt lat="40.010" lon="-2.990"><ele>655.0</ele></trkpt>
      <trkpt lat="40.011" lon="-2.989"><ele>660.0</ele></trkpt>
      <trkpt lat="40.012" lon="-2.988"><ele>665.0</ele></trkpt>
      <trkpt lat="40.013" lon="-2.987"><ele>670.0</ele></trkpt>
      <trkpt lat="40.014" lon="-2.986"><ele>675.0</ele></trkpt>
      <trkpt lat="40.015" lon="-2.985"><ele>680.0</ele></trkpt>
      <trkpt lat="40.016" lon="-2.984"><ele>685.0</ele></trkpt>
      <trkpt lat="40.017" lon="-2.983"><ele>690.0</ele></trkpt>
      <trkpt lat="40.018" lon="-2.982"><ele>695.0</ele></trkpt>
      <trkpt lat="40.019" lon="-2.981"><ele>700.0</ele></trkpt>
    </trkseg>
  </trk>
</gpx>"""


@pytest.mark.usefixtures("_override_db")
class TestRacePrepPage:
    def test_page_renders_without_auth(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.get("/race-prep")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_page_renders_with_auth(self, race_user):
        _set_optional_user(race_user)
        try:
            with TestClient(app) as c:
                resp = c.get("/race-prep")
            assert resp.status_code == 200
            assert "Race Prep" in resp.text
        finally:
            _clear_user()


class TestGPXService:
    def test_parse_gpx(self):
        result = GPXService.parse_gpx(SAMPLE_GPX)
        assert result["distance_km"] > 0
        assert result["elevation_gain"] > 0
        assert result["point_count"] == 20
        assert len(result["trackpoints"]) == 20

    def test_parse_invalid_gpx(self):
        with pytest.raises(ValueError, match="Invalid GPX"):
            GPXService.parse_gpx(b"not xml")

    def test_parse_empty_gpx(self):
        empty_gpx = b'<?xml version="1.0"?><gpx version="1.1"></gpx>'
        with pytest.raises(ValueError, match="no tracks"):
            GPXService.parse_gpx(empty_gpx)

    def test_build_elevation_profile(self):
        parsed = GPXService.parse_gpx(SAMPLE_GPX)
        profile = GPXService.build_elevation_profile(parsed["trackpoints"])
        assert len(profile) > 0
        assert "segment_number" in profile[0]
        assert "grade_pct" in profile[0]
        assert "avg_elevation" in profile[0]

    def test_generate_planned_gpx(self):
        parsed = GPXService.parse_gpx(SAMPLE_GPX)
        profile = GPXService.build_elevation_profile(parsed["trackpoints"])

        pace_plan = []
        for seg in profile:
            pace_plan.append({
                "end_km": seg["end_km"],
                "target_pace_str": "5:30",
                "cumulative_time_str": "10:00",
            })

        gpx_bytes = GPXService.generate_planned_gpx(
            original_trackpoints=parsed["trackpoints"],
            pace_plan=pace_plan,
            target_time_seconds=3600,
            race_name="Test Plan",
        )
        assert b"<gpx" in gpx_bytes
        assert b"Test Plan" in gpx_bytes


class TestRacePacingService:
    def test_predict_flat_time(self):
        seconds = RacePacingService.predict_flat_time(42.0, 10.0)
        assert seconds > 0

    def test_predict_elevation_adjusted_time(self):
        profile = [
            {"start_km": 0, "end_km": 1, "avg_elevation": 100, "grade_pct": 2.0},
            {"start_km": 1, "end_km": 2, "avg_elevation": 110, "grade_pct": 1.0},
            {"start_km": 2, "end_km": 3, "avg_elevation": 105, "grade_pct": -0.5},
        ]
        result = RacePacingService.predict_elevation_adjusted_time(42.0, 3.0, profile)
        assert result["flat_time"] > 0
        assert result["elevation_adjusted"] >= result["flat_time"]

    def test_validate_feasibility_realistic(self):
        result = RacePacingService.validate_feasibility(2400, 2400, 2500)
        assert result.label == "Realistic"

    def test_validate_feasibility_aggressive(self):
        result = RacePacingService.validate_feasibility(2000, 2400, 2500)
        assert result.label == "Aggressive"

    def test_validate_feasibility_conservative(self):
        result = RacePacingService.validate_feasibility(3000, 2400, 2500)
        assert result.label == "Conservative"

    def test_generate_pace_blueprint(self):
        profile = [
            {"segment_number": 1, "start_km": 0, "end_km": 1, "avg_elevation": 100, "grade_pct": 1.0},
            {"segment_number": 2, "start_km": 1, "end_km": 2, "avg_elevation": 105, "grade_pct": 0.5},
            {"segment_number": 3, "start_km": 2, "end_km": 3, "avg_elevation": 102, "grade_pct": -0.5},
        ]
        blueprint = RacePacingService.generate_pace_blueprint(
            elevation_profile=profile,
            target_time_seconds=1500,
            user_vdot=42.0,
            distance_km=3.0,
        )
        assert len(blueprint.segments) == 3
        assert blueprint.total_distance_km == 3.0
        assert blueprint.target_time_seconds == 1500


@pytest.mark.usefixtures("_override_db")
class TestRacePrepAPI:
    def test_analyze_gpx_success(self, race_user):
        _set_user(race_user)
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/race-prep/analyze",
                    files={"file": ("race.gpx", SAMPLE_GPX, "application/gpx+xml")},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["distance_km"] > 0
            assert data["total_elevation_gain"] > 0
            assert "elevation_profile" in data
            assert "trackpoints" in data
        finally:
            _clear_user()

    def test_analyze_gpx_invalid_file(self, race_user):
        _set_user(race_user)
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/race-prep/analyze",
                    files={"file": ("race.txt", b"not a gpx", "text/plain")},
                )
            assert resp.status_code == 400
        finally:
            _clear_user()

    def test_analyze_gpx_unauthenticated(self):
        _clear_user()
        with TestClient(app) as c:
            resp = c.post(
                "/api/race-prep/analyze",
                files={"file": ("race.gpx", SAMPLE_GPX, "application/gpx+xml")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_vdot"] == 0.0

    def test_blueprint_requires_vdot(self, race_user):
        _set_user(race_user)
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/race-prep/blueprint",
                    json={
                        "target_time_seconds": 2400,
                        "distance_km": 5.0,
                        "elevation_profile": [
                            {"start_km": 0, "end_km": 1, "avg_elevation": 100, "grade_pct": 1.0},
                            {"start_km": 1, "end_km": 2, "avg_elevation": 105, "grade_pct": 0.5},
                            {"start_km": 2, "end_km": 3, "avg_elevation": 102, "grade_pct": -0.5},
                            {"start_km": 3, "end_km": 4, "avg_elevation": 100, "grade_pct": 0.0},
                            {"start_km": 4, "end_km": 5, "avg_elevation": 98, "grade_pct": -0.5},
                        ],
                    },
                )
            assert resp.status_code == 400
            assert "VDOT" in resp.json()["detail"]
        finally:
            _clear_user()

    def test_blueprint_empty_profile(self, race_user):
        _set_user(race_user)
        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/race-prep/blueprint",
                    json={
                        "target_time_seconds": 2400,
                        "distance_km": 5.0,
                        "elevation_profile": [],
                    },
                )
            assert resp.status_code == 400
        finally:
            _clear_user()

    def test_download_gpx_not_found(self):
        with TestClient(app) as c:
            resp = c.get("/api/race-prep/download-gpx/nonexistent-session")
        assert resp.status_code == 404

    def test_attach_route_not_found(self):
        with TestClient(app) as c:
            resp = c.post(
                "/api/race-prep/blueprint/nonexistent/attach-route",
                json=[{"lat": 0, "lon": 0}],
            )
        assert resp.status_code == 404


class TestFITService:
    def test_generate_race_workout(self):
        segments = [
            {
                "start_km": 0, "end_km": 1, "target_pace_min_km": 5.5,
                "grade_pct": 1.0,
            },
            {
                "start_km": 1, "end_km": 2, "target_pace_min_km": 5.3,
                "grade_pct": 0.0,
            },
            {
                "start_km": 2, "end_km": 3, "target_pace_min_km": 5.0,
                "grade_pct": -0.5,
            },
        ]
        fit_bytes = FITService.generate_race_workout(
            segments=segments,
            target_time_seconds=960,
            target_time_str="16:00",
            race_name="Test Race",
        )
        assert len(fit_bytes) > 50
        assert b".FIT" in fit_bytes or fit_bytes[4:8] == b".FIT"

    def test_pace_conversion(self):
        from app.services.fit_service import _pace_min_km_to_speed_ms
        speed = _pace_min_km_to_speed_ms(5.0)
        assert abs(speed - 1000.0 / 300.0) < 0.01
        speed = _pace_min_km_to_speed_ms(0)
        assert speed == 0.0


@pytest.mark.usefixtures("_override_db")
class TestFITDownloadAPI:
    def test_download_fit_not_found(self):
        with TestClient(app) as c:
            resp = c.get("/api/race-prep/download-fit/nonexistent-session")
        assert resp.status_code == 404

