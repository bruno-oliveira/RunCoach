"""Directional-invariant tests for the adaptation backtest harness.

These don't pin exact constants (those are expected to be re-tuned). They pin
the *direction* the engine moves for each runner archetype, so a tuning change
that flips a sign — telling an overreaching runner to do more, or a coping
runner to back off hard — fails loudly. They also lock in the harness's
observability output (e.g. that the readiness signal folds to zero weight when
no readiness logs exist), which is itself a finding worth guarding.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import backtest as bt
from app.contexts.plan.adaptation.tuning import (
    OVERREACH_OVERRIDE_CLAMP,
    STANDARD_MIN,
)
from app.models import Base

_ARCH = {a.name: a for a in bt.ARCHETYPES}


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


def _report(db, name):
    return bt.ArchetypeReport(_ARCH[name], bt.replay(db, _ARCH[name]))


# --------------------------------------------------------------------------- #
# Directional invariants
# --------------------------------------------------------------------------- #


def test_strong_adherent_is_not_pushed_into_a_reduction(db):
    """A runner hitting plan at low effort should hold/progress, never back off."""
    rep = _report(db, "strong_adherent")
    assert rep.multipliers, "expected at least one evaluated week"
    # No overreach, and the engine never slams them toward the floor.
    assert rep.overreach_rate == 0.0
    assert min(rep.multipliers) >= 0.95
    assert max(rep.multipliers) >= 1.0  # at least one hold-or-increase


def test_overreacher_trips_overreach_clamp_and_is_capped(db):
    """High volume + high effort must eventually force a reduce-or-hold."""
    rep = _report(db, "overreacher")
    evaluated = rep.evaluated
    assert any(o.overreach for o in evaluated), "overreach never detected"
    # Every week the overreach branch fires, the multiplier is forced down.
    for o in evaluated:
        if o.overreach:
            assert o.multiplier <= OVERREACH_OVERRIDE_CLAMP
    # The runner genuinely exceeds plan volume (drives the clamp).
    assert max(o.volume_ratio for o in evaluated) > 1.2


def test_under_performer_is_reduced(db):
    """Short, slow, skipped runs at high effort → clear reduction."""
    rep = _report(db, "under_performer")
    assert rep.multipliers
    assert max(rep.multipliers) <= 0.90
    assert min(o.volume_ratio for o in rep.evaluated) < 0.75
    assert rep.direction_counts()["increase"] == 0


def test_sporadic_logger_shows_low_completion(db):
    """Logging ~1 in 3 runs reads as low completion (or trips the data guard)."""
    rep = _report(db, "sporadic_logger")
    evaluated = rep.evaluated
    # Either some weeks were skipped for insufficient data, or completion is low.
    assert rep.skipped_count > 0 or all(
        o.completion_rate is not None and o.completion_rate < 0.5 for o in evaluated
    )
    # Never pushed to increase on thin, incomplete data.
    assert rep.direction_counts()["increase"] == 0


def test_hr_drifter_pulls_down_and_hr_signal_is_active(db):
    """Chronically hot HR with zones present should reduce, via an active HR signal."""
    rep = _report(db, "hr_drifter")
    evaluated = rep.evaluated
    assert evaluated
    # HR ran ~2 zones hot, so the HR factor is suppressive and HR overreach fires.
    assert all((o.hr_zone_factor or 1.0) <= 0.95 for o in evaluated)
    assert all((o.avg_zone_deviation or 0.0) >= 1.0 for o in evaluated)
    assert max(rep.multipliers) <= 0.90
    # The HR signal carries real weight here (unlike the no-HR archetypes).
    real, nom = rep.weight_realization()["hr_zone"]
    assert nom > 0 and real > 0


# --------------------------------------------------------------------------- #
# Observability invariants (the "6 signals but really 4" finding)
# --------------------------------------------------------------------------- #


def test_completion_ignores_distance_zero_recovery_days(db):
    """A near-perfect adherent reads high completion now that distance-0 days
    (uncompletable placeholders) are excluded from the denominator."""
    rep = _report(db, "strong_adherent")
    rates = [o.completion_rate for o in rep.evaluated if o.completion_rate is not None]
    assert rates and min(rates) > 0.85


def test_readiness_signal_folds_without_logs(db):
    """No readiness logs → the readiness weight folds onto other signals."""
    rep = _report(db, "strong_adherent")
    real, nom = rep.weight_realization()["readiness"]
    assert nom > 0.0, "readiness has a nominal phase weight"
    assert real == 0.0, "but contributes nothing without readiness logs"


def test_hr_weight_folds_when_no_zones_configured(db):
    """Archetypes without HR zones should see the HR signal contribute 0 weight."""
    rep = _report(db, "under_performer")  # with_hr_zones=False
    real, _nom = rep.weight_realization()["hr_zone"]
    assert real == 0.0


# --------------------------------------------------------------------------- #
# Harness plumbing
# --------------------------------------------------------------------------- #


def test_multipliers_respect_standard_clamp_floor(db):
    """With no adaptation history, the standard (non-expanded) floor holds."""
    rep = _report(db, "under_performer")
    assert min(rep.multipliers) >= STANDARD_MIN


def test_report_renders_for_all_archetypes(db):
    """run_all + format_report produce a non-trivial table without error."""
    factory = bt._in_memory_session_factory()
    reports = bt.run_all(factory, weeks=12)
    text = bt.format_report(reports)
    assert "ADAPTATION BACKTEST" in text
    for arch in bt.ARCHETYPES:
        assert arch.name in text
