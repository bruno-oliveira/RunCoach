"""Tests for the DB-aware workout-type classifier and its backfill."""

from datetime import datetime, timedelta, timezone

import pytest

from app.contexts.runner.fitness.workout_type_classifier import (
    backfill_inferred_workout_types,
    classify_workout_type,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.models.run_log import RunLog
from app.models.user import User

VDOT = 45.0
PZ = VDOTCalculator.get_pace_zones(VDOT)
TEMPO_PACE = PZ["T"]["pace_min_km"]  # ~4.72
EASY_PACE = PZ["E"]["pace_min_km_slow"] - 0.2  # comfortably inside easy
MAX_HR = 190


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def user(test_db):
    u = User(id="u1", email="u1@example.com")
    test_db.add(u)
    test_db.commit()
    return u


def _classify(test_db, **overrides):
    params = dict(
        distance_km=10.0,
        duration_minutes=50.0,
        avg_pace_min_km=5.0,
        avg_heart_rate=None,
        max_heart_rate=None,
        elevation_gain_m=None,
        perceived_effort=None,
        splits=None,
        vdot=VDOT,
        user_id="u1",
        db=test_db,
        exclude_run_id=None,
    )
    params.update(overrides)
    return classify_workout_type(**params)


class TestClassifyWorkoutType:
    def test_easy_run(self, test_db, user):
        wt, conf = _classify(
            test_db,
            avg_pace_min_km=EASY_PACE,
            avg_heart_rate=120,
            max_heart_rate=MAX_HR,
        )
        assert wt == "easy"
        assert conf > 0

    def test_tempo_steady_splits(self, test_db, user):
        steady = [{"pace_min_km": TEMPO_PACE + 0.02 * i} for i in range(8)]
        wt, _ = _classify(
            test_db,
            avg_pace_min_km=TEMPO_PACE,
            avg_heart_rate=165,
            max_heart_rate=MAX_HR,
            splits=steady,
        )
        assert wt == "tempo"

    def test_interval_surging_splits_same_averages(self, test_db, user):
        """Same average pace/HR as a tempo, but surging splits -> interval."""
        surging = [{"pace_min_km": p} for p in [3.9, 5.5, 3.8, 5.6, 3.9, 5.5, 3.8, 5.6]]
        wt, _ = _classify(
            test_db,
            avg_pace_min_km=TEMPO_PACE,
            avg_heart_rate=165,
            max_heart_rate=MAX_HR,
            splits=surging,
        )
        assert wt == "interval"

    def test_long_run_by_duration(self, test_db, user):
        wt, _ = _classify(
            test_db,
            distance_km=18.0,
            duration_minutes=95.0,
            avg_pace_min_km=EASY_PACE,
            avg_heart_rate=135,
            max_heart_rate=MAX_HR,
        )
        assert wt == "long"

    def test_hr_only_when_no_vdot(self, test_db, user):
        wt, _ = _classify(test_db, vdot=None, avg_heart_rate=180, max_heart_rate=MAX_HR)
        assert wt == "interval"

    def test_no_signal_returns_none(self, test_db, user):
        # No VDOT (and no history to resolve one) and no HR -> nothing to infer.
        assert _classify(test_db, vdot=None, avg_heart_rate=None) is None

    def test_resolves_vdot_from_history(self, test_db, user):
        for i in range(6):
            test_db.add(
                RunLog(
                    user_id="u1",
                    distance_km=10.0,
                    duration_minutes=50.0,
                    avg_pace_min_km=5.0,
                    vdot=VDOT,
                    date=_now() - timedelta(days=i + 1),
                )
            )
        test_db.commit()
        # vdot not passed; classifier should resolve it from the user's history.
        result = _classify(
            test_db,
            vdot=None,
            avg_pace_min_km=TEMPO_PACE,
            avg_heart_rate=165,
            max_heart_rate=MAX_HR,
        )
        assert result is not None
        assert result[0] == "tempo"


class TestBackfill:
    def test_populates_missing_inferred_types(self, test_db, user):
        for i in range(4):
            test_db.add(
                RunLog(
                    user_id="u1",
                    distance_km=10.0,
                    duration_minutes=50.0,
                    avg_pace_min_km=TEMPO_PACE if i % 2 else EASY_PACE,
                    avg_heart_rate=165 if i % 2 else 120,
                    max_heart_rate=MAX_HR,
                    vdot=VDOT,
                    date=_now() - timedelta(days=i + 1),
                )
            )
        test_db.commit()

        updated = backfill_inferred_workout_types(test_db)
        test_db.commit()

        assert updated >= 4
        runs = test_db.query(RunLog).filter(RunLog.user_id == "u1").all()
        assert all(r.inferred_workout_type is not None for r in runs)

    def test_skips_runs_that_already_have_a_type(self, test_db, user):
        run = RunLog(
            user_id="u1",
            distance_km=10.0,
            duration_minutes=50.0,
            avg_pace_min_km=EASY_PACE,
            avg_heart_rate=120,
            max_heart_rate=MAX_HR,
            vdot=VDOT,
            inferred_workout_type="tempo",
            date=_now(),
        )
        test_db.add(run)
        test_db.commit()

        backfill_inferred_workout_types(test_db)
        test_db.commit()

        # Pre-set value is left untouched (only None rows are filled).
        assert run.inferred_workout_type == "tempo"


class TestEffectiveWorkoutTypeProperty:
    def test_strava_untagged_prefers_inference(self, test_db, user):
        run = RunLog(
            user_id="u1",
            strava_activity_id="abc",
            workout_type="easy",
            inferred_workout_type="tempo",
            inferred_type_confidence=0.8,
        )
        assert run.effective_workout_type == "tempo"

    def test_manual_tag_is_respected(self, test_db, user):
        run = RunLog(
            user_id="u1",
            workout_type="recovery",
            inferred_workout_type="tempo",
            inferred_type_confidence=0.9,
        )
        assert run.effective_workout_type == "recovery"
