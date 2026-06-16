"""Tests for endurance calibration and VDOT outlier filtering."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.models import RunLog, User


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
    predicted_time_seconds: float | None = None,
    workout_type: str | None = None,
    effort_class: str | None = None,
    perceived_effort: int | None = None,
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
        predicted_time_seconds=predicted_time_seconds,
        workout_type=workout_type,
        effort_class=effort_class,
        perceived_effort=perceived_effort,
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
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=65 + i * 0.2,
                days_ago=i,
                vdot=30.0 + (i % 3) * 0.2,
            )
        # One absurd outlier
        _add_run(
            test_db,
            user.id,
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
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=65 + i * 0.2,
                days_ago=i + 5,
                vdot=30.0 + (i % 3) * 0.2,
            )
        # A genuine PR a few VDOT points above the cluster
        _add_run(
            test_db,
            user.id,
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
        _add_run(
            test_db,
            user.id,
            distance_km=5.0,
            duration_minutes=25.0,
            vdot=37.0,
            days_ago=2,
        )
        _add_run(
            test_db,
            user.id,
            distance_km=5.0,
            duration_minutes=27.0,
            vdot=35.0,
            days_ago=4,
        )
        _add_run(
            test_db,
            user.id,
            distance_km=5.0,
            duration_minutes=28.0,
            vdot=33.0,
            days_ago=6,
        )
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
                test_db,
                user.id,
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
                test_db,
                user.id,
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
                test_db,
                user.id,
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
                test_db,
                user.id,
                distance_km=5.0,
                duration_minutes=25.0,
                days_ago=i * 2 + 1,
                vdot=37.0,
            )
        # Three trail long runs (44m/km gain) + one flat long run roughly on-prediction
        for i in range(3):
            _add_run(
                test_db,
                user.id,
                distance_km=20.0,
                duration_minutes=200.0,  # very slow due to trail
                days_ago=i * 4 + 10,
                elevation_gain_m=900,  # 45 m/km -> trail
                vdot=22.0,
            )
        # Single flat run too few to trigger calibration on its own
        _add_run(
            test_db,
            user.id,
            distance_km=20.0,
            duration_minutes=120.0,
            days_ago=8,
            vdot=30.0,
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


class TestPureHelpers:
    def test_calculate_vdot_from_run_too_short(self):
        assert (
            RacePredictorService.calculate_vdot_from_run(
                RunLog(distance_km=1.0, duration_minutes=6.0)
            )
            is None
        )

    def test_calculate_vdot_from_run_valid(self):
        v = RacePredictorService.calculate_vdot_from_run(
            RunLog(distance_km=5.0, duration_minutes=25.0, elevation_gain_m=0)
        )
        assert v is not None and v > 0

    def test_vdot_trend(self):
        def hist(*vals):
            return [{"vdot": v, "date": None} for v in vals]

        # Fewer than 4 samples is too noisy to call — stable (audit B13).
        assert RacePredictorService.calculate_vdot_trend(hist(50)) == "stable"
        assert RacePredictorService.calculate_vdot_trend(hist(45, 48)) == "stable"
        assert RacePredictorService.calculate_vdot_trend(hist(50, 47, 49)) == "stable"

        # Genuine multi-run trends are detected.
        assert (
            RacePredictorService.calculate_vdot_trend(hist(45, 46, 47, 48, 49))
            == "improving"
        )
        assert (
            RacePredictorService.calculate_vdot_trend(hist(52, 51, 50.5, 50, 49))
            == "declining"
        )
        assert (
            RacePredictorService.calculate_vdot_trend(hist(50, 50.1, 49.9, 50, 50.2))
            == "stable"
        )

        # A single low-VDOT artifact at an endpoint must NOT flip the verdict.
        assert (
            RacePredictorService.calculate_vdot_trend(
                hist(50, 50.2, 49.8, 50.1, 50, 49.9, 42)
            )
            == "stable"
        )

    def test_closest_distance_name(self):
        assert RacePredictorService._closest_distance_name(5.0) == "5K"
        assert RacePredictorService._closest_distance_name(10.0) == "10K"
        assert RacePredictorService._closest_distance_name(21.1) == "Half Marathon"
        assert RacePredictorService._closest_distance_name(42.2) == "Marathon"
        assert "K" in RacePredictorService._closest_distance_name(7.3)


class TestVdotQueries:
    def test_history_returns_runs(self, test_db):
        user = _make_user(test_db)
        for i, v in enumerate([44, 45, 46, 47]):
            _add_run(
                test_db,
                user.id,
                distance_km=8.0,
                duration_minutes=44,
                days_ago=20 - i * 4,
                vdot=v,
            )
        test_db.flush()
        history = RacePredictorService.get_vdot_history(user.id, db=test_db)
        assert len(history) == 4

    def test_best_recent_none_without_runs(self, test_db):
        user = _make_user(test_db)
        assert RacePredictorService.get_best_recent_vdot(user.id, db=test_db) is None

    def test_best_effort(self, test_db):
        user = _make_user(test_db)
        for v in (44, 45, 46, 47, 48):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=50,
                days_ago=10,
                vdot=v,
            )
        test_db.flush()
        best = RacePredictorService.get_best_effort(user.id, test_db)
        assert best is not None and best["vdot"] > 0

    def test_best_effort_none(self, test_db):
        user = _make_user(test_db)
        assert RacePredictorService.get_best_effort(user.id, test_db) is None


class TestPredictionsAndGaps:
    def test_predictions_no_data(self, test_db):
        user = _make_user(test_db)
        result = RacePredictorService.get_predictions_for_user(user.id, test_db)
        assert result["has_sufficient_data"] is False
        assert result["predictions"] == {}

    def test_predictions_with_data(self, test_db):
        user = _make_user(test_db)
        for i in range(5):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=48,
                days_ago=20 - i * 3,
                vdot=47,
            )
        test_db.flush()
        result = RacePredictorService.get_predictions_for_user(user.id, test_db)
        assert result["has_sufficient_data"] is True
        assert result["current_vdot"] is not None
        assert result["predictions"]

    def test_analyze_gap_goal_faster_than_fitness(self, test_db):
        result = RacePredictorService.analyze_fitness_gap(45.0, 10.0, 1, test_db)
        assert result["feasible"] is True
        assert "faster than" in result["gap_label"]

    def test_analyze_gap_goal_slower_than_fitness(self, test_db):
        from app.core.training.vdot_calculator import VDOTCalculator

        predicted = VDOTCalculator.predict_time_for_distance(45.0, 10.0)
        # Goal slightly slower than predicted → current fitness already meets
        # it, so vdot_required resolves to ~current and the goal is feasible.
        result = RacePredictorService.analyze_fitness_gap(
            45.0, 10.0, int(predicted * 1.03), test_db
        )
        assert result["vdot_required"] is not None
        assert result["feasible"] is True
        assert "slower than predicted" in result["gap_label"]

    def test_trail_run_count(self, test_db):
        user = _make_user(test_db)
        _add_run(
            test_db,
            user.id,
            distance_km=10.0,
            duration_minutes=70,
            days_ago=5,
            vdot=42,
            elevation_gain_m=300,
        )
        _add_run(
            test_db,
            user.id,
            distance_km=10.0,
            duration_minutes=55,
            days_ago=4,
            vdot=46,
            elevation_gain_m=20,
        )
        test_db.flush()
        assert RacePredictorService.get_trail_runs_count(user.id, test_db) == 1

    def test_race_history_with_comparison(self, test_db):
        user = _make_user(test_db)
        for i in range(4):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=50,
                days_ago=40 - i * 5,
                vdot=46,
            )
        _add_run(
            test_db,
            user.id,
            distance_km=10.0,
            duration_minutes=49,
            days_ago=2,
            vdot=47,
        )
        test_db.flush()
        result = RacePredictorService.get_race_history(user.id, limit=10, db=test_db)
        assert result["total"] >= 1
        assert result["runs_with_predictions"] >= 1
        assert result["avg_prediction_accuracy"] is not None


class TestCalibrationFactorPure:
    """Pure (actual / predicted) ratio math, independent of the DB."""

    def test_no_samples_returns_neutral(self):
        from app.contexts.runner.fitness.race_predictor_service.vdot_math import (
            calibration_factor_from_samples,
        )

        assert calibration_factor_from_samples([]) == 1.0

    def test_optimistic_predictions_pull_factor_above_one(self):
        from app.contexts.runner.fitness.race_predictor_service.vdot_math import (
            calibration_factor_from_samples,
        )

        # Predicted 1:50:00 but actually finished 2:00:00 -> ~1.09 slower.
        factor = calibration_factor_from_samples([(6600.0, 7200.0), (3000.0, 3300.0)])
        assert factor > 1.0

    def test_factor_is_clamped(self):
        from app.contexts.runner.fitness.race_predictor_service.vdot_math import (
            calibration_factor_from_samples,
        )

        # Catastrophic blow-up (2x) must be clamped, not applied literally.
        assert calibration_factor_from_samples([(3600.0, 7200.0)]) <= 1.30
        # An impossibly fast result is clamped on the low side too.
        assert calibration_factor_from_samples([(7200.0, 3600.0)]) >= 0.95

    def test_garbage_pairs_ignored(self):
        from app.contexts.runner.fitness.race_predictor_service.vdot_math import (
            calibration_factor_from_samples,
        )

        assert calibration_factor_from_samples([(0.0, 3600.0), (3600.0, 0.0)]) == 1.0


class TestCalibrationFactorService:
    """Calibration learns only from genuine race efforts."""

    def test_no_race_efforts_is_neutral(self, test_db):
        user = _make_user(test_db)
        # Easy runs, much slower than their predictions -> must NOT calibrate.
        for i in range(4):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=70,
                days_ago=i * 5,
                predicted_time_seconds=3000.0,  # 50:00 predicted vs 70:00 easy
                workout_type="easy",
            )
        test_db.flush()
        factor = RacePredictorService.compute_calibration_factor(user.id, test_db)
        assert factor == 1.0

    def test_optimistic_race_results_raise_factor(self, test_db):
        user = _make_user(test_db)
        for i in range(2):
            _add_run(
                test_db,
                user.id,
                distance_km=21.1,
                duration_minutes=120,  # actual 2:00:00
                days_ago=30 * (i + 1),
                predicted_time_seconds=6600.0,  # predicted 1:50:00
                workout_type="race",
            )
        test_db.flush()
        factor = RacePredictorService.compute_calibration_factor(user.id, test_db)
        assert factor > 1.0

    def test_perceived_effort_marks_race_effort(self, test_db):
        user = _make_user(test_db)
        _add_run(
            test_db,
            user.id,
            distance_km=10.0,
            duration_minutes=55,  # actual 55:00
            days_ago=10,
            predicted_time_seconds=3000.0,  # predicted 50:00
            perceived_effort=10,
        )
        test_db.flush()
        factor = RacePredictorService.compute_calibration_factor(user.id, test_db)
        assert factor > 1.0

    def test_calibration_makes_predictions_slower(self, test_db):
        """A history of optimistic races slows the surfaced predictions."""
        user = _make_user(test_db)
        # A spread of efforts so get_best_recent_vdot has data to work with.
        for i in range(6):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=50 + i * 0.2,
                days_ago=i * 3,
                vdot=46.0 + (i % 2) * 0.2,
            )
        # Two races that came in slower than predicted.
        for i in range(2):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                duration_minutes=55,
                days_ago=20 + i * 10,
                vdot=46.0,
                predicted_time_seconds=3000.0,
                workout_type="race",
            )
        test_db.flush()

        factor = RacePredictorService.compute_calibration_factor(user.id, test_db)
        assert factor > 1.0

        data = RacePredictorService.get_predictions_for_user(user.id, test_db)
        assert data["calibration_factor"] == factor
        # The 10K prediction should be slower than the same VDOT predicts raw.
        from app.core.training.vdot_calculator import VDOTCalculator

        raw = VDOTCalculator.predict_time_for_distance(data["current_vdot"], 10.0)
        assert data["predictions"]["10K"]["seconds"] > raw
