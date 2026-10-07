"""The fitness estimate reads held-back training through a measured LTHR."""

from datetime import datetime, timedelta

import pytest

from app.contexts.runner.fitness.aerobic_fitness_service import (
    aerobic_vdot_for,
    measured_threshold_hr,
)
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.core.training.physiology.submaximal_vdot import MAX_HEART_RATE_LIFT
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.models import RunLog, User

LTHR = 160
TRUE_VDOT = 40.0
ZONES = VDOTCalculator.get_pace_zones(TRUE_VDOT)


def _runner(db, **anchors) -> User:
    user = User(email="aerobic@example.com", **anchors)
    db.add(user)
    db.flush()
    return user


def _log(db, user, pace, hr, *, count=6, minutes=45.0) -> None:
    km = minutes / pace
    for i in range(count):
        db.add(
            RunLog(
                user_id=user.id,
                date=datetime.now() - timedelta(days=2 + i * 3),
                distance_km=km,
                duration_minutes=minutes,
                avg_pace_min_km=pace,
                avg_heart_rate=hr,
                elevation_gain_m=10,
                vdot=VDOTCalculator.calculate_vdot(km, int(minutes * 60)),
            )
        )
    db.flush()


def _estimates(db, user) -> tuple[float, float]:
    """``(best efforts alone, the estimate callers get)``."""
    return (
        RacePredictorService._best_efforts_vdot(user.id, db=db),
        RacePredictorService.get_best_recent_vdot(user.id, db=db),
    )


class TestMeasuredThreshold:
    def test_the_runner_s_entry_outranks_the_watch(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=160, intervals_lthr=165)
        assert measured_threshold_hr(user, test_db) == 160

    def test_the_watch_value_stands_in(self, test_db):
        user = _runner(test_db, max_hr=185, intervals_lthr=165)
        assert measured_threshold_hr(user, test_db) == 165

    def test_nothing_supplied_is_nothing_measured(self, test_db):
        """No estimate stands in: it is read off the VDOT this would feed."""
        user = _runner(test_db, max_hr=185)
        assert measured_threshold_hr(user, test_db) is None

    def test_an_implausible_threshold_is_ignored(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=110)
        assert measured_threshold_hr(user, test_db) is None


class TestEstimate:
    def test_a_runner_who_only_jogs_is_lifted_by_the_cap(self, test_db):
        """Jogs score nine points low as races; heart rate may give back four."""
        user = _runner(test_db, max_hr=185, threshold_hr=LTHR)
        _log(test_db, user, ZONES["E"]["pace_min_km_fast"], round(LTHR * 0.909))

        best_efforts, estimate = _estimates(test_db, user)

        assert best_efforts < TRUE_VDOT - 5
        assert aerobic_vdot_for(user.id, 12, test_db) == pytest.approx(
            TRUE_VDOT, abs=0.5
        )
        assert estimate == pytest.approx(best_efforts + MAX_HEART_RATE_LIFT, abs=0.05)

    def test_a_runner_who_trains_at_threshold_is_lifted_all_the_way(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=LTHR)
        _log(test_db, user, ZONES["T"]["pace_min_km"], LTHR, minutes=30.0)

        best_efforts, estimate = _estimates(test_db, user)

        assert best_efforts < estimate <= best_efforts + MAX_HEART_RATE_LIFT
        assert estimate == pytest.approx(TRUE_VDOT, abs=0.6)

    def test_without_a_measured_threshold_nothing_changes(self, test_db):
        user = _runner(test_db, max_hr=185)
        _log(test_db, user, ZONES["E"]["pace_min_km_fast"], 145)

        best_efforts, estimate = _estimates(test_db, user)

        assert aerobic_vdot_for(user.id, 12, test_db) is None
        assert estimate == best_efforts

    def test_heart_rate_never_lowers_what_pace_has_shown(self, test_db):
        """Hard efforts set the estimate; sluggish jogs beside them read lower."""
        user = _runner(test_db, max_hr=185, threshold_hr=LTHR)
        _log(test_db, user, ZONES["T"]["pace_min_km"] - 0.3, 175, minutes=40.0)
        _log(test_db, user, 7.0, LTHR - 2, count=12)

        best_efforts, estimate = _estimates(test_db, user)

        assert aerobic_vdot_for(user.id, 12, test_db) < best_efforts
        assert estimate == best_efforts

    def test_no_runs_no_estimate(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=LTHR)
        assert RacePredictorService.get_best_recent_vdot(user.id, db=test_db) is None

    def test_an_unknown_runner_has_no_reading(self, test_db):
        assert aerobic_vdot_for("nobody", 12, test_db) is None
