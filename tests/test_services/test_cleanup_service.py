"""Retention cleanup: what gets deleted, what is spared, and where it is filtered.

These two functions are the only thing standing between the database and
unbounded growth from anonymous visitors, and they run unattended on the boot
path. They were previously at 0% coverage — including the `coalesce` branch that
decides whether a timestamp-less anonymous row is old or simply unknown.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, update

from app.application.cleanup_service import (
    ANONYMOUS_RETENTION_DAYS,
    INACTIVE_MONTHS,
    cleanup_anonymous_users,
    cleanup_inactive_accounts,
)
from app.models import TrainingPlan, User

DAY = timedelta(days=1)


def _naive_utc(**delta) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(**delta)


def _anonymous(db, user_id: str, *, last_activity=None, created_at=None) -> User:
    user = User(
        id=user_id,
        google_id=None,
        email=None,
        last_activity=last_activity,
        created_at=created_at,
    )
    db.add(user)
    return user


def _named(db, user_id: str, *, last_activity=None) -> User:
    user = User(
        id=user_id,
        google_id=f"google-{user_id}",
        email=f"{user_id}@example.com",
        last_activity=last_activity,
        created_at=_naive_utc(days=1),
    )
    db.add(user)
    return user


def _ids(db) -> set[str]:
    return {row[0] for row in db.query(User.id).all()}


def _force_columns(db, user_id: str, **columns) -> None:
    """Set columns with a Core UPDATE, bypassing SQLAlchemy's column defaults.

    ``last_activity`` carries a Python-side ``default=utcnow_naive``, so
    inserting a row with ``last_activity=None`` gets "now" — SQLAlchemy treats
    an explicit None as absent where defaults are concerned. Rows real visitors
    leave behind (older than the column itself, or never stamped) are genuinely
    NULL, so the tests have to write them the way the database sees them.

    An ORM ``update()`` rather than ``text()`` so the ``DateTime`` columns go
    through SQLAlchemy's own bind processing; raw parameters would fall back to
    sqlite3's deprecated default datetime adapter.
    """
    db.execute(update(User).where(User.id == user_id).values(**columns))
    db.commit()
    # The identity map still holds the pre-UPDATE values.
    db.expire_all()


class TestAnonymousCleanup:
    def test_deletes_anonymous_users_past_the_retention_window(self, test_db):
        _anonymous(test_db, "stale", last_activity=_naive_utc(days=120))
        test_db.commit()

        assert cleanup_anonymous_users(test_db) == 1
        assert _ids(test_db) == set()

    def test_keeps_anonymous_users_within_the_window(self, test_db):
        _anonymous(test_db, "fresh", last_activity=_naive_utc(days=1))
        test_db.commit()

        assert cleanup_anonymous_users(test_db) == 0
        assert _ids(test_db) == {"fresh"}

    def test_falls_back_to_created_at_when_never_active(self, test_db):
        """A visitor who generated no plan has no last_activity at all."""
        _anonymous(test_db, "stale")
        test_db.commit()
        _force_columns(
            test_db, "stale", last_activity=None, created_at=_naive_utc(days=120)
        )

        assert cleanup_anonymous_users(test_db) == 1
        assert _ids(test_db) == set()

    def test_keeps_a_recent_created_at_when_never_active(self, test_db):
        _anonymous(test_db, "fresh")
        test_db.commit()
        _force_columns(
            test_db, "fresh", last_activity=None, created_at=_naive_utc(days=2)
        )

        assert cleanup_anonymous_users(test_db) == 0
        assert _ids(test_db) == {"fresh"}

    def test_keeps_a_row_with_no_timestamps_at_all(self, test_db):
        """Both null compares NULL, not "ancient" — never delete on unknown age."""
        _anonymous(test_db, "unknown")
        test_db.commit()
        _force_columns(test_db, "unknown", last_activity=None, created_at=None)

        assert cleanup_anonymous_users(test_db) == 0
        assert _ids(test_db) == {"unknown"}

    def test_a_recent_last_activity_shields_an_ancient_created_at(self, test_db):
        """Retention follows the most recent sign of life, not the first."""
        _anonymous(
            test_db,
            "active",
            last_activity=_naive_utc(days=1),
            created_at=_naive_utc(days=400),
        )
        test_db.commit()

        assert cleanup_anonymous_users(test_db) == 0
        assert _ids(test_db) == {"active"}

    def test_never_deletes_a_named_account(self, test_db):
        """Anonymous cleanup must not touch a signed-in runner."""
        _named(test_db, "runner", last_activity=_naive_utc(days=700))
        test_db.commit()

        assert cleanup_anonymous_users(test_db) == 0
        assert _ids(test_db) == {"runner"}

    def test_dry_run_counts_without_deleting(self, test_db):
        _anonymous(test_db, "stale", last_activity=_naive_utc(days=120))
        test_db.commit()

        assert cleanup_anonymous_users(test_db, dry_run=True) == 1
        assert _ids(test_db) == {"stale"}

    def test_cascades_to_the_plan_the_visitor_generated(self, test_db):
        """Otherwise anonymous plans leak forever behind their deleted owner."""
        user = _anonymous(test_db, "stale", last_activity=_naive_utc(days=120))
        test_db.add(
            TrainingPlan(
                id="plan-1",
                user_id=user.id,
                current_weekly_km=20,
                target_distance="10",
                weeks_duration=8,
            )
        )
        test_db.commit()

        cleanup_anonymous_users(test_db)

        assert test_db.query(TrainingPlan).count() == 0

    def test_the_cutoff_is_applied_by_the_database_not_in_python(self, test_db):
        """The whole point of the rewrite: do not materialise the table."""
        for i in range(50):
            _anonymous(test_db, f"fresh-{i}", last_activity=_naive_utc(days=1))
        _anonymous(test_db, "stale", last_activity=_naive_utc(days=120))
        test_db.commit()

        statements: list[str] = []

        def _record(_conn, _cursor, statement, _params, _ctx, _many):
            statements.append(statement)

        event.listen(test_db.get_bind(), "before_cursor_execute", _record)
        try:
            assert cleanup_anonymous_users(test_db, dry_run=True) == 1
        finally:
            event.remove(test_db.get_bind(), "before_cursor_execute", _record)

        selects = [s for s in statements if "FROM users" in s]
        assert selects, "expected the cleanup to query users"
        assert any("coalesce" in s.lower() for s in selects)


class TestInactiveAccountCleanup:
    def test_deletes_an_account_idle_past_the_window(self, test_db):
        _named(
            test_db, "gone", last_activity=_naive_utc(days=INACTIVE_MONTHS * 30 + 10)
        )
        test_db.commit()

        assert cleanup_inactive_accounts(test_db) == 1
        assert _ids(test_db) == set()

    def test_keeps_an_account_active_within_the_window(self, test_db):
        _named(test_db, "here", last_activity=_naive_utc(days=10))
        test_db.commit()

        assert cleanup_inactive_accounts(test_db) == 0
        assert _ids(test_db) == {"here"}

    def test_never_deletes_a_row_with_no_last_activity(self, test_db):
        """Rows predating the column are spared until a login stamps them —
        deleting them would be deleting on unknown age."""
        user = _named(test_db, "unknown")
        user.last_activity = None
        test_db.commit()

        assert cleanup_inactive_accounts(test_db) == 0
        assert _ids(test_db) == {"unknown"}

    def test_dry_run_counts_without_deleting(self, test_db):
        _named(
            test_db, "gone", last_activity=_naive_utc(days=INACTIVE_MONTHS * 30 + 10)
        )
        test_db.commit()

        assert cleanup_inactive_accounts(test_db, dry_run=True) == 1
        assert _ids(test_db) == {"gone"}


@pytest.mark.parametrize("retention_days", [ANONYMOUS_RETENTION_DAYS])
def test_anonymous_retention_is_shorter_than_account_retention(retention_days):
    """Visitors are not customers: 90 days, not 24 months."""
    assert retention_days < INACTIVE_MONTHS * 30
