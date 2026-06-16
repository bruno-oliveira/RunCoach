"""Tests for HR-aware effort classification (pace + heart rate)."""

import uuid
from datetime import datetime, timedelta, timezone

from app.contexts.runner.fitness.effort_classifier import (
    EFFORT_EASY,
    EFFORT_RACE,
    EFFORT_TEMPO,
    backfill_effort_classes,
    classify_effort,
    estimate_max_hr,
    resolve_user_max_hr,
)
from app.models import RunLog, User


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db, *, max_hr=None, age=None) -> User:
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com", max_hr=max_hr, age=age)
    db.add(user)
    db.flush()
    return user


def _add_run(
    db,
    user_id,
    *,
    distance_km,
    duration_minutes=50.0,
    avg_pace_min_km=None,
    avg_heart_rate=None,
    effort_class=None,
    days_ago=0,
):
    run = RunLog(
        id=_uid(),
        user_id=user_id,
        date=_now() - timedelta(days=days_ago),
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        avg_pace_min_km=avg_pace_min_km,
        avg_heart_rate=avg_heart_rate,
        effort_class=effort_class,
    )
    db.add(run)
    return run


class TestEstimateMaxHr:
    def test_prefers_explicit_profile_value(self):
        assert estimate_max_hr(190, 40) == 190

    def test_age_estimate_when_no_profile_max(self):
        assert estimate_max_hr(None, 30) == 190  # 220 - 30

    def test_implausible_profile_max_falls_back_to_age(self):
        assert estimate_max_hr(40, 30) == 190

    def test_none_when_no_signal(self):
        assert estimate_max_hr(None, None) is None


class TestHrClassification:
    def test_near_max_hr_is_race_even_without_pace_history(self, test_db):
        """HR >= 92% of max flags a race on a first-ever distance (no pace pool)."""
        user = _make_user(test_db, max_hr=190)
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=5.5,
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
            avg_heart_rate=180,  # 94.7% of 190
            user_max_hr=190,
        )
        assert result == EFFORT_RACE

    def test_tempo_hr_promotes_when_pace_history_thin(self, test_db):
        user = _make_user(test_db, max_hr=190)
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=6.0,
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
            avg_heart_rate=165,  # 86.8% -> tempo
            user_max_hr=190,
        )
        assert result == EFFORT_TEMPO

    def test_low_hr_does_not_manufacture_effort(self, test_db):
        user = _make_user(test_db)
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=6.5,
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
            avg_heart_rate=130,  # ~68% of 190
            user_max_hr=190,
        )
        assert result is None

    def test_no_max_hr_skips_hr_signal(self, test_db):
        """Without a usable max HR the classifier behaves as if HR wasn't given."""
        user = _make_user(test_db)
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=5.5,
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
            avg_heart_rate=180,
            user_max_hr=None,
        )
        assert result is None


class TestNoHrPreservesPaceBehaviour:
    def test_top_decile_pace_is_race(self, test_db):
        user = _make_user(test_db)
        for i in range(10):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                avg_pace_min_km=6.0 + i * 0.1,
                days_ago=i + 1,
            )
        test_db.flush()
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=5.0,  # faster than the whole distribution
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
        )
        assert result == EFFORT_RACE

    def test_slow_pace_is_easy(self, test_db):
        user = _make_user(test_db)
        for i in range(10):
            _add_run(
                test_db,
                user.id,
                distance_km=10.0,
                avg_pace_min_km=5.5 + i * 0.05,
                days_ago=i + 1,
            )
        test_db.flush()
        result = classify_effort(
            distance_km=10.0,
            avg_pace_min_km=7.0,  # slower than everything
            perceived_effort=None,
            user_id=user.id,
            db=test_db,
        )
        assert result == EFFORT_EASY


class TestResolveUserMaxHr:
    def test_from_profile(self, test_db):
        user = _make_user(test_db, max_hr=185)
        assert resolve_user_max_hr(user.id, test_db) == 185

    def test_from_age(self, test_db):
        user = _make_user(test_db, age=25)
        assert resolve_user_max_hr(user.id, test_db) == 195


class TestBackfillHrPromotion:
    def test_promotes_prior_non_race_to_race_on_hr(self, test_db):
        """A run previously classified easy is promoted to race when HR maxes out."""
        user = _make_user(test_db, max_hr=190)
        _add_run(
            test_db,
            user.id,
            distance_km=22.0,
            avg_pace_min_km=7.5,  # slow trail pace, never top-decile
            avg_heart_rate=182,  # 95.8% of max -> race effort
            effort_class=EFFORT_EASY,
        )
        test_db.flush()

        backfill_effort_classes(test_db)

        run = test_db.query(RunLog).filter(RunLog.user_id == user.id).first()
        assert run.effort_class == EFFORT_RACE

    def test_does_not_demote_or_touch_low_hr(self, test_db):
        user = _make_user(test_db, max_hr=190)
        _add_run(
            test_db,
            user.id,
            distance_km=10.0,
            avg_pace_min_km=6.5,
            avg_heart_rate=130,  # easy HR
            effort_class=EFFORT_EASY,
        )
        test_db.flush()

        backfill_effort_classes(test_db)

        run = test_db.query(RunLog).filter(RunLog.user_id == user.id).first()
        assert run.effort_class == EFFORT_EASY
