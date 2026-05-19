"""Tests for endurance calibration and VDOT outlier filtering."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import RunLog, User
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db) -> User:
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    return user


def _add_run(
    db,
    user_id: str,
    *,
    distance_km: float,
    duration_minutes: float,
    days_ago: int = 0,
    elevation_gain_m: int | None = None,
    vdot: float | None = None,
):
    run = RunLog(
        id=_uid(),
        user_id=user_id,
        date=_now() - timedelta(days=days_ago),
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        avg_pace_min_km=duration_minutes / distance_km if distance_km else None,
        elevation_gain_m=elevation_gain_m,
        vdot=vdot,
    )
    db.add(run)
    return run


class TestVDOTOutlierFilter:
    """An extreme VDOT (e.g. GPS glitch) is dropped from aggregation."""

    def test_extreme_outlier_dropped_from_best_recent_vdot(self, test_db):
        user = _make_user(test_db)
        # Ten realistic runs around VDOT 30
        for i in range(10):
            _add_run(
                test_db, user.id,
                distance_km=10.0,
                duration_minutes=65 + i * 0.2,
                days_ago=i,
                vdot=30.0 + (i % 3) * 0.2,
            )
        # One absurd outlier
        _add_run(
            test_db, user.id,
            distance_km=10.0,
            duration_minutes=33.0,
            days_ago=5,
            vdot=65.0,
        )
        test_db.flush()

        result = RacePredictorService.get_best_recent_vdot(user.id, db=test_db)
        assert result is not None
        # Outlier (65) must not dominate; aggregated VDOT stays near the realistic cluster
        assert result < 35.0

    def test_genuine_high_vdot_not_filtered(self, test_db):
        """A modestly higher VDOT (a real PR) should survive the filter."""
        user = _make_user(test_db)
        for i in range(8):
            _add_run(
                test_db, user.id,
                distance_km=10.0,
                duration_minutes=65 + i * 0.2,
                days_ago=i + 5,
                vdot=30.0 + (i % 3) * 0.2,
            )
        # A genuine PR a few VDOT points above the cluster
        _add_run(
            test_db, user.id,
            distance_km=10.0,
            duration_minutes=55.0,
            days_ago=1,
            vdot=34.0,
        )
        test_db.flush()

        result = RacePredictorService.get_best_recent_vdot(user.id, db=test_db)
        # The 34.0 PR should pull the weighted average above the cluster mean
        assert result is not None
        assert result >= 30.5

    def test_small_sample_skips_filter(self, test_db):
        """With <5 runs in the window, the IQR filter is bypassed."""
        user = _make_user(test_db)
        _add_run(test_db, user.id, distance_km=5.0, duration_minutes=25.0, vdot=37.0, days_ago=2)
        _add_run(test_db, user.id, distance_km=5.0, duration_minutes=27.0, vdot=35.0, days_ago=4)
        _add_run(test_db, user.id, distance_km=5.0, duration_minutes=28.0, vdot=33.0, days_ago=6)
        test_db.flush()

        result = RacePredictorService.get_best_recent_vdot(user.id, db=test_db)
        assert result is not None
        # No filtering applied -> uses all three
        assert 33.0 <= result <= 37.0


class TestEnduranceFactor:
    """Long-distance prediction calibration based on actual long-run history."""

    def test_short_distance_returns_one(self, test_db):
        user = _make_user(test_db)
        result = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=5.0, db=test_db
        )
        assert result == 1.0

    def test_no_data_returns_one(self, test_db):
        user = _make_user(test_db)
        result = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=21.1, db=test_db
        )
        assert result == 1.0

    def test_runner_slower_than_predicted_gets_factor(self, test_db):
        """When long runs are slower than the supplied VDOT predicts, factor > 1."""
        user = _make_user(test_db)
        # 4 long flat runs at 7:00/km. VDOT 37.5 predicts ~5:17/km -> actual is ~32% slower.
        for i in range(4):
            _add_run(
                test_db, user.id,
                distance_km=18.0,
                duration_minutes=126.0,  # 7:00/km
                days_ago=i * 5 + 10,
                elevation_gain_m=20,
            )
        test_db.flush()

        factor = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=21.1, db=test_db, current_vdot=37.5
        )
        assert factor > 1.05
        assert factor <= 1.5  # capped

    def test_factor_capped_at_max(self, test_db):
        """Even an extreme gap is clamped to MAX_FACTOR."""
        user = _make_user(test_db)
        # Extremely slow long runs vs. a high supplied VDOT
        for i in range(5):
            _add_run(
                test_db, user.id,
                distance_km=18.0,
                duration_minutes=240.0,  # ~13:20/km -> way slower than VDOT 50 predicts
                days_ago=i * 4 + 10,
            )
        test_db.flush()

        factor = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=21.1, db=test_db, current_vdot=50.0
        )
        assert factor == pytest.approx(1.5, rel=1e-3)

    def test_runner_on_pace_gets_no_correction(self, test_db):
        """Long runs roughly on VDOT prediction yield factor 1.0."""
        user = _make_user(test_db)
        # VDOT 37.5 predicts 18 km in ~1:35 (~95 min). Match it.
        for i in range(4):
            _add_run(
                test_db, user.id,
                distance_km=18.0,
                duration_minutes=95.0,
                days_ago=i * 5 + 10,
            )
        test_db.flush()

        factor = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=21.1, db=test_db, current_vdot=37.5
        )
        assert factor == 1.0

    def test_trail_runs_excluded_from_calibration(self, test_db):
        """Hilly long runs don't pollute the endurance calibration."""
        user = _make_user(test_db)
        for i in range(3):
            _add_run(
                test_db, user.id,
                distance_km=5.0,
                duration_minutes=25.0,
                days_ago=i * 2 + 1,
                vdot=37.0,
            )
        # Three trail long runs (44m/km gain) + one flat long run roughly on-prediction
        for i in range(3):
            _add_run(
                test_db, user.id,
                distance_km=20.0,
                duration_minutes=200.0,  # very slow due to trail
                days_ago=i * 4 + 10,
                elevation_gain_m=900,    # 45 m/km -> trail
                vdot=22.0,
            )
        # Single flat run too few to trigger calibration on its own
        _add_run(
            test_db, user.id,
            distance_km=20.0, duration_minutes=120.0,
            days_ago=8, vdot=30.0,
        )
        test_db.flush()

        factor = RacePredictorService.compute_endurance_factor(
            user.id, target_distance_km=21.1, db=test_db
        )
        # Only one flat long run -> below MIN_SAMPLE -> 1.0
        assert factor == 1.0


class TestPredictTimeWithEnduranceFactor:
    """The endurance_factor parameter on predict_time_for_distance."""

    def test_factor_one_is_noop(self):
        from app.core.training.vdot_calculator import VDOTCalculator
        plain = VDOTCalculator.predict_time_for_distance(40.0, 21.1)
        with_factor = VDOTCalculator.predict_time_for_distance(
            40.0, 21.1, endurance_factor=1.0
        )
        assert plain == with_factor

    def test_factor_above_one_lengthens_prediction(self):
        from app.core.training.vdot_calculator import VDOTCalculator
        plain = VDOTCalculator.predict_time_for_distance(40.0, 21.1)
        slower = VDOTCalculator.predict_time_for_distance(
            40.0, 21.1, endurance_factor=1.2
        )
        assert slower > plain
        # Roughly +20%
        ratio = slower / plain
        assert 1.18 < ratio < 1.22

    def test_factor_applies_after_elevation(self):
        from app.core.training.vdot_calculator import VDOTCalculator
        elev_only = VDOTCalculator.predict_time_for_distance(
            40.0, 21.1, elevation_gain_m=500
        )
        with_endurance = VDOTCalculator.predict_time_for_distance(
            40.0, 21.1, elevation_gain_m=500, endurance_factor=1.2
        )
        # endurance multiplies elevation-adjusted time
        assert with_endurance == int(round(elev_only * 1.2))
