"""Smoke tests for the Race Prep feature.

Covers page rendering, GPX analysis, and blueprint generation.
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
from app.services.integrations.gpx_service import GPXService
from app.services.fitness.race_pacing_service import RacePacingService


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

    def test_trail_inexperience_slows_estimate(self):
        # 30km / 1500m gain = 50 m/km, well above the 20 m/km trail threshold.
        profile = [
            {
                "start_km": float(i),
                "end_km": float(i + 1),
                "avg_elevation": 500.0 + i * 5,
                "grade_pct": 5.0,
                "net_grade_pct": 5.0,
                "elevation_gain": 50.0,
                "elevation_loss": 0.0,
            }
            for i in range(30)
        ]
        novice = RacePacingService.predict_elevation_adjusted_time(
            50.0, 30.0, profile, trail_runs_count=0
        )
        veteran = RacePacingService.predict_elevation_adjusted_time(
            50.0, 30.0, profile, trail_runs_count=10
        )
        # Novice penalty should be ~30%+ on top of the slope-only number.
        assert novice["elevation_adjusted"] >= veteran["elevation_adjusted"] * 1.30

    def test_no_trail_factor_on_flat_course(self):
        # Pure flat course (0 elevation gain) — trail factor must not fire even
        # for a runner with no logged trail runs.
        profile = [
            {
                "start_km": float(i),
                "end_km": float(i + 1),
                "avg_elevation": 100.0,
                "grade_pct": 0.0,
                "net_grade_pct": 0.0,
                "elevation_gain": 0.0,
                "elevation_loss": 0.0,
            }
            for i in range(10)
        ]
        result = RacePacingService.predict_elevation_adjusted_time(
            50.0, 10.0, profile, trail_runs_count=0
        )
        assert result["elevation_adjusted"] == result["flat_time"]

    def test_steep_grade_uses_piecewise_rate(self):
        # A 10% grade should cost more sec/km/% than a 2% grade because the
        # piecewise tier kicks in at 8%+. Compare the per-km penalty implied
        # by a single steep segment vs. a single shallow one.
        steep_profile = [
            {
                "start_km": 0.0, "end_km": 1.0, "avg_elevation": 200.0,
                "grade_pct": 10.0, "net_grade_pct": 10.0,
                "elevation_gain": 100.0, "elevation_loss": 0.0,
            }
        ]
        shallow_profile = [
            {
                "start_km": 0.0, "end_km": 1.0, "avg_elevation": 200.0,
                "grade_pct": 2.0, "net_grade_pct": 2.0,
                "elevation_gain": 20.0, "elevation_loss": 0.0,
            }
        ]
        steep = RacePacingService.predict_elevation_adjusted_time(50.0, 1.0, steep_profile)
        shallow = RacePacingService.predict_elevation_adjusted_time(50.0, 1.0, shallow_profile)
        # Linear-12 would give 10*12=120s vs 2*12=24s (5x). Piecewise gives
        # 10*24=240s vs 2*12=24s (10x). Just verify ratio exceeds the linear
        # 5x to confirm piecewise is in effect.
        steep_pen = steep["elevation_penalty"]
        shallow_pen = shallow["elevation_penalty"]
        assert steep_pen > shallow_pen * 5

    def test_blueprint_segment_sum_matches_target(self):
        profile = [
            {
                "segment_number": i + 1,
                "start_km": float(i),
                "end_km": float(i + 1),
                "avg_elevation": 100.0 + i * 10,
                "grade_pct": float(i % 5),
                "net_grade_pct": float(i % 5) - 1.0,
                "elevation_gain": 10.0,
                "elevation_loss": 0.0,
            }
            for i in range(10)
        ]
        target = 3000
        blueprint = RacePacingService.generate_pace_blueprint(
            elevation_profile=profile,
            target_time_seconds=target,
            user_vdot=50.0,
            distance_km=10.0,
            trail_runs_count=2,
        )
        total = sum(seg.target_time_seconds for seg in blueprint.segments)
        # Per-segment rounding may drift up to 1 second per segment.
        assert abs(total - target) <= len(profile)
        assert blueprint.segments[-1].cumulative_time_seconds == total


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


class TestFITValidationLocal:
    def test_validate_generated_fit(self):
        from app.services.integrations.fit_service import FITService
        from app.services.integrations.fit_validation_local import validate_fit_bytes
        segments = [
            {"start_km": 0, "end_km": 1, "target_pace_min_km": 5.0, "grade_pct": 0.0},
        ]
        fit_bytes = FITService.generate_race_workout(
            segments=segments,
            target_time_seconds=300,
            target_time_str="5:00",
        )
        result = validate_fit_bytes(fit_bytes)
        assert result.valid, f"Validation failed: {result.errors}"

    def test_validate_invalid_fit(self):
        from app.services.integrations.fit_validation_local import validate_fit_bytes
        result = validate_fit_bytes(b"not a fit file")
        assert not result.valid

