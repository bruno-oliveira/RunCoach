"""Tests for the multi-day wellness strain nudge.

The gap this guard closes is reach, not emphasis. ``_detect_low_readiness``
reads one morning and only the one the runner reported, so a runner who never
checks in gets nothing however badly their watch has read all week. These tests
pin that it fires on a *pattern* without any check-in, stays silent below the
streak bar, and never outranks the immediate morning.

Stubbing style mirrors ``test_proactive_nudge_readiness``: ``gather_signals`` is
stubbed so the test exercises the nudge decision, not the full pipeline.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import proactive_nudge
from app.models import Base, DailyWorkout, TrainingPlan, User, WeeklyPlan, WellnessDay

TODAY = date(2026, 6, 19)  # a Friday → isoweekday 5
CURRENT_WEEK = 3

NORMAL_HRV = 60.0
NORMAL_RHR = 50.0
# ratio 0.90 → the first negative HRV band: off, but only just.
MILD_HRV = 54.0
# ratio 0.80 → the third band, and deep enough to carry a driver sentence.
SEVERE_HRV = 48.0


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def freeze_today(monkeypatch):
    monkeypatch.setattr(
        "app.contexts.plan.adaptation.proactive_nudge.today_date", lambda: TODAY
    )


@pytest.fixture()
def plan(db: Session) -> TrainingPlan:
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    tp = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        target_distance="10K",
        weeks_duration=8,
        start_date=datetime.combine(
            TODAY - timedelta(weeks=CURRENT_WEEK - 1), datetime.min.time()
        ),
    )
    db.add(tp)
    db.commit()
    return tp


def _gathered():
    return {
        "signals": {
            "multiplier": 1.0,
            "overreach_detected": False,
            "completion_rate": 0.9,
            "vdot_trend": "stable",
            "avg_zone_deviation": 0.0,
        },
        "current_week": CURRENT_WEEK,
        "current_day_of_week": TODAY.isoweekday(),
        "adjustable_weeks": [WeeklyPlan(week_number=CURRENT_WEEK + 1)],
    }


def _stub_gather(monkeypatch):
    monkeypatch.setattr(proactive_nudge, "gather_signals", lambda *a, **k: _gathered())


def _add_current_week_with_hard_session(db, plan):
    """A current-week plan with an interval session still ahead today."""
    wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=CURRENT_WEEK)
    db.add(wp)
    db.flush()
    db.add(
        DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=TODAY.isoweekday(),
            workout_type="interval",
            distance_km=8.0,
        )
    )
    db.commit()


def _add_current_week_easy_only(db, plan):
    wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=CURRENT_WEEK)
    db.add(wp)
    db.flush()
    db.add(
        DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=TODAY.isoweekday(),
            workout_type="easy",
            distance_km=5.0,
        )
    )
    db.commit()


def _seed_watch(db, plan, *, tail_days: int, tail_hrv: float = MILD_HRV):
    """24 unremarkable mornings, then ``tail_days`` off ones ending today."""
    user_id = plan.user_id
    start = TODAY - timedelta(days=24 + tail_days - 1)
    for i in range(24):
        db.add(
            WellnessDay(
                id=_uid(),
                user_id=user_id,
                date=start + timedelta(days=i),
                hrv=NORMAL_HRV,
                resting_hr=NORMAL_RHR,
            )
        )
    for i in range(tail_days):
        db.add(
            WellnessDay(
                id=_uid(),
                user_id=user_id,
                date=TODAY - timedelta(days=tail_days - 1 - i),
                hrv=tail_hrv,
                resting_hr=NORMAL_RHR,
            )
        )
    db.commit()


def _log_low_readiness(db, plan):
    from app.contexts.runner.wellness.checkin_service import CheckInService

    CheckInService(db).record(
        plan.user_id, sleep_hours=5, soreness=5, energy=1, on_date=TODAY
    )


def test_fires_on_a_strain_run_with_no_check_in(db, plan, freeze_today, monkeypatch):
    """The case the low-readiness guard structurally cannot see: a suppressed
    watch across several mornings, and the runner never filled in a card."""
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=3)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is not None
    assert nudge["kind"] == "wellness_strain"
    assert nudge["intent"] == "feeling_tired"
    assert nudge["evidence"]["strain_days"] == 3


def test_silent_below_the_streak_bar(db, plan, freeze_today, monkeypatch):
    """Two off-mornings is not a pattern, and acting on it is how a nudge
    starts crying wolf."""
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=2)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is None or nudge["kind"] != "wellness_strain"


def test_silent_on_a_normal_week(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=0)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is None or nudge["kind"] != "wellness_strain"


def test_silent_with_no_watch_data_at_all(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is None or nudge["kind"] != "wellness_strain"


def test_silent_when_nothing_hard_is_left_to_ease(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch)
    _add_current_week_easy_only(db, plan)
    _seed_watch(db, plan, tail_days=3)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is None or nudge["kind"] != "wellness_strain"


def test_the_immediate_morning_outranks_the_pattern(
    db, plan, freeze_today, monkeypatch
):
    """Both guards would fire; the session-specific one the runner just reported
    is the more actionable, so it keeps its place."""
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=3)
    _log_low_readiness(db, plan)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is not None
    assert nudge["kind"] == "low_readiness"


def test_a_deep_run_carries_the_shared_reason(db, plan, freeze_today, monkeypatch):
    """A run deep enough for the shared vocabulary to name a driver should say
    so, rather than falling back to the generic sentence."""
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=3, tail_hrv=SEVERE_HRV)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is not None
    assert nudge["kind"] == "wellness_strain"
    assert "HRV" in nudge["detail"]


def test_a_mild_run_still_speaks_from_the_run_itself(
    db, plan, freeze_today, monkeypatch
):
    """A mild run has no driver phrasing to borrow, so the sentence must stand
    on the run's own length."""
    _stub_gather(monkeypatch)
    _add_current_week_with_hard_session(db, plan)
    _seed_watch(db, plan, tail_days=3, tail_hrv=MILD_HRV)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)

    assert nudge is not None
    assert nudge["kind"] == "wellness_strain"
    assert "3 mornings running" in nudge["detail"]
