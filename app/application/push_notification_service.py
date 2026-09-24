"""Delivers pushes to a runner's devices — once, to the ones that want them.

Everything that can buzz a phone goes through :meth:`PushNotifier.notify`, so
three rules hold everywhere instead of being re-implemented per feature:

* **Consent per category.** ``notification_prefs`` (see
  :mod:`app.core.coaching.notification_prefs`) is checked before anything else.
* **Exactly once.** The ``(user, kind, key)`` row in ``notification_log`` is
  claimed *before* sending, under a unique constraint, so a retried webhook or
  a double-fired cron finds it taken. If no device accepted the message the
  claim is released, so the next attempt may still deliver it.
* **Dead devices are pruned.** A 404/410 from the push service deletes the
  subscription on the spot; repeated transient failures do too, eventually.

The composition of *what* to say is pure (:mod:`app.core.coaching.push_messages`);
this module resolves the facts and does the I/O.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.coaching import notification_prefs as prefs
from app.core.coaching.push_messages import RunFacts, after_sync_message
from app.domain.notifications import (
    PushMessage,
    PushOutcome,
    PushSender,
    PushTarget,
)
from app.models import NotificationLog, PushSubscription, RunLog, TrainingPlan, User

if TYPE_CHECKING:
    from app.application.ambient_sync_service import RunnerSync

logger = logging.getLogger(__name__)

# A subscription that has failed this many sends in a row (without the push
# service ever saying "gone") is a wiped phone or a revoked permission.
_MAX_CONSECUTIVE_FAILURES = 5
# An import this large is a backfill (first connect, a long gap), not "the run
# you just did" — nobody wants a lock-screen note about March.
_LIVE_IMPORT_MAX = 3
# ...and the newest run must be recent for the note to read as live.
_LIVE_RUN_MAX_AGE = timedelta(hours=48)

# Ledger kinds (the ``kind`` column). Categories are the runner-facing switch;
# kinds are the idempotency namespace.
KIND_AFTER_SYNC = "after_sync"
KIND_MORNING_BRIEF = "morning_brief"
KIND_WEEK_REVIEW = "week_review"
KIND_NUDGE = "nudge"
KIND_TEST = "test"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PushNotifier:
    """Sends pushes for one database session."""

    def __init__(self, db: Session, sender: PushSender) -> None:
        self.db = db
        self.sender = sender

    # ---- the one path to a phone ------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.sender.configured)

    def reachable(self, user: User) -> bool:
        """Whether this runner has any device we could push to."""
        return self.configured and bool(self._subscriptions(user))

    def notify(
        self,
        user: User,
        message: PushMessage,
        *,
        category: Optional[str],
        kind: str,
        key: str,
    ) -> bool:
        """Push ``message`` to every device ``user`` has, at most once per key.

        ``category=None`` bypasses the preference check — only for the explicit
        "send me a test" button, which the runner is pressing right now.
        Returns True when at least one device accepted it.
        """
        if category is not None and not prefs.wants(user.notification_prefs, category):
            return False
        if not self.configured:
            return False
        subscriptions = self._subscriptions(user)
        if not subscriptions:
            return False

        claim = self._claim(user, kind, key)
        if claim is None:
            return False

        delivered = False
        for subscription in subscriptions:
            outcome = self.sender.send(
                PushTarget(
                    endpoint=subscription.endpoint,
                    p256dh=subscription.p256dh,
                    auth=subscription.auth,
                ),
                message,
            )
            if outcome == PushOutcome.DELIVERED:
                delivered = True
                subscription.last_success_at = _utcnow()
                subscription.failure_count = 0
            elif outcome == PushOutcome.GONE:
                self.db.delete(subscription)
            else:
                subscription.failure_count = (subscription.failure_count or 0) + 1
                if subscription.failure_count >= _MAX_CONSECUTIVE_FAILURES:
                    self.db.delete(subscription)

        if not delivered:
            self.db.delete(claim)
        self.db.flush()
        return delivered

    def _subscriptions(self, user: User) -> List[PushSubscription]:
        return (
            self.db.query(PushSubscription)
            .filter(PushSubscription.user_id == user.id)
            .all()
        )

    def _claim(self, user: User, kind: str, key: str) -> Optional[NotificationLog]:
        entry = NotificationLog(user_id=user.id, kind=kind, key=key[:120])
        try:
            with self.db.begin_nested():
                self.db.add(entry)
                self.db.flush()
        except IntegrityError:
            return None
        return entry

    def already_sent(self, user: User, kind: str, key: str) -> bool:
        return (
            self.db.query(NotificationLog.id)
            .filter(
                NotificationLog.user_id == user.id,
                NotificationLog.kind == kind,
                NotificationLog.key == key[:120],
            )
            .first()
            is not None
        )

    # ---- after a sync ------------------------------------------------------

    def after_sync(self, user: User, result: "RunnerSync") -> bool:
        """One note for what a live sync brought in, and what it changed.

        Silent for backfills (a first connect imports a year) and for runs
        older than a couple of days — those aren't news.
        """
        if not result.imported or result.imported > _LIVE_IMPORT_MAX:
            return False
        wants_run = prefs.wants(user.notification_prefs, prefs.AFTER_RUN)
        wants_change = prefs.wants(user.notification_prefs, prefs.PLAN_CHANGES)
        if not (wants_run or wants_change) or not self.reachable(user):
            return False

        newest = (
            self.db.query(RunLog)
            .filter(RunLog.user_id == user.id)
            .order_by(RunLog.date.desc())
            .first()
        )
        if newest is None or newest.date is None:
            return False
        created = newest.created_at or _utcnow()
        if _utcnow() - created > _LIVE_RUN_MAX_AGE:
            return False

        headline = None
        adapted_plan_id = None
        if wants_change:
            for plan_id in result.adapted_plan_ids:
                plan = self.db.get(TrainingPlan, plan_id)
                change = (plan.last_change_plan or {}) if plan else {}
                headline = change.get("headline") or change.get("reason")
                if headline:
                    adapted_plan_id = plan_id
                    break
        if headline is None and not wants_run:
            return False

        message = after_sync_message(
            RunFacts(
                distance_km=float(newest.distance_km or 0),
                duration_minutes=newest.duration_minutes,
                pace_min_km=newest.avg_pace_min_km,
                feedback=_feedback_line(newest),
            ),
            plan_id=adapted_plan_id or newest.training_plan_id,
            adaptation_headline=headline,
            extra_runs=max(0, result.imported - 1),
        )
        category = prefs.PLAN_CHANGES if headline else prefs.AFTER_RUN
        return self.notify(
            user,
            message,
            category=category,
            kind=KIND_AFTER_SYNC,
            key=str(newest.id),
        )


def _feedback_line(run: RunLog) -> Optional[str]:
    """The single most useful sentence the feedback engine wrote for this run."""
    feedback: Any = getattr(run, "feedback", None)
    if feedback is None:
        return None
    for field in (
        "effort_feedback",
        "pace_feedback",
        "hr_zone_feedback",
        "volume_feedback",
    ):
        text = getattr(feedback, field, None)
        if text:
            first = str(text).strip().split("\n")[0]
            return first
    return None


def get_push_notifier(db: Session) -> PushNotifier:
    from app.infrastructure.notifications.webpush import get_push_sender

    return PushNotifier(db, get_push_sender())
