"""The hourly sweep: morning briefs and Sunday week reviews, in local time.

GitHub's scheduler runs this every hour; each runner is only acted on in the
hour that is *their* morning (or their week's last evening), read from the
timezone their browser last reported. Runners with no push device are skipped
before any query — this job only ever speaks through a lock screen.

**Morning brief** (``MORNING_HOUR`` local): pull last night's wellness first
so the verdict includes it, then say today's session and whether the body
agrees. Rest days and already-run days stay silent — a coach doesn't text you
to say "nothing today".

**Week review** (``REVIEW_HOUR`` local, last day of the plan week): planned vs
done, and what changes next.

Both are idempotent through the notification ledger, so a double-fired cron or
a manual re-run the same hour sends nothing twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.application.push_notification_service import (
    KIND_MORNING_BRIEF,
    KIND_WEEK_REVIEW,
    PushNotifier,
)
from app.application.week_review_service import due_review
from app.application.wellness_sync_service import refresh_wellness
from app.core.coaching import notification_prefs as prefs
from app.core.coaching.push_messages import (
    morning_brief_message,
    week_review_message,
)
from app.core.time_utils import use_timezone
from app.models import PushSubscription, TrainingPlan, User

logger = logging.getLogger(__name__)

MORNING_HOUR = 7
REVIEW_HOUR = 19


@dataclass
class HourlySummary:
    candidates: int = 0
    briefs_sent: int = 0
    reviews_sent: int = 0
    failed: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "candidates": self.candidates,
            "briefs_sent": self.briefs_sent,
            "reviews_sent": self.reviews_sent,
            "failed": self.failed,
        }


def local_now(tz_name: Optional[str], now_utc: datetime) -> datetime:
    try:
        zone = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    aware = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
    return aware.astimezone(zone)


class ScheduledPushService:
    def __init__(
        self, db: Session, intervals_service: Any, notifier: PushNotifier
    ) -> None:
        self.db = db
        self.intervals_service = intervals_service
        self.notifier = notifier

    async def run(
        self, *, now_utc: Optional[datetime] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        summary = HourlySummary()
        if not self.notifier.configured:
            return {**summary.as_dict(), "configured": False}
        now_utc = now_utc or datetime.now(timezone.utc)

        users = (
            self.db.query(User)
            .join(PushSubscription, PushSubscription.user_id == User.id)
            .distinct()
            .all()
        )
        for user in users:
            summary.candidates += 1
            local = local_now(user.timezone, now_utc)
            try:
                with use_timezone(user.timezone):
                    if local.hour == MORNING_HOUR and await self._morning_brief(
                        user, local.date(), dry_run=dry_run
                    ):
                        summary.briefs_sent += 1
                    if local.hour == REVIEW_HOUR and self._week_review(
                        user, local.date(), dry_run=dry_run
                    ):
                        summary.reviews_sent += 1
                if not dry_run:
                    self.db.commit()
            except Exception:
                logger.exception("Hourly push failed for user %s", user.id)
                self.db.rollback()
                summary.failed += 1
        return {**summary.as_dict(), "configured": True}

    # ---- morning brief ----------------------------------------------------

    async def _morning_brief(self, user: User, today: date, *, dry_run: bool) -> bool:
        if not prefs.wants(user.notification_prefs, prefs.MORNING_BRIEF):
            return False
        if self.notifier.already_sent(user, KIND_MORNING_BRIEF, today.isoformat()):
            return False
        plan = self._active_plan(user)
        if plan is None:
            return False

        if not dry_run:
            await refresh_wellness(user, self.db, self.intervals_service, today=today)

        from app.contexts.plan.plan_helpers import today_card_for_plan

        card = today_card_for_plan(self.db, user, plan)
        if card is None or card.session is None:
            return False
        session = card.session
        if session.is_rest or session.logged:
            return False

        message = morning_brief_message(
            plan_id=str(plan.id),
            session_title=session.title,
            session_detail=session.detail,
            readiness_label=card.readiness_label,
            drivers=card.readiness_drivers,
            advisory=card.advisory,
        )
        if dry_run:
            logger.info("Dry run: morning brief for %s: %s", user.id, message.title)
            return True
        return self.notifier.notify(
            user,
            message,
            category=prefs.MORNING_BRIEF,
            kind=KIND_MORNING_BRIEF,
            key=today.isoformat(),
        )

    # ---- week review ------------------------------------------------------

    def _week_review(self, user: User, today: date, *, dry_run: bool) -> bool:
        if not prefs.wants(user.notification_prefs, prefs.WEEK_REVIEW):
            return False
        plan = self._active_plan(user)
        if plan is None:
            return False
        due = due_review(plan, str(user.id), self.db, today)
        # Only on the week's last day — the Monday carry-over is for the card.
        if due is None or due.week_end != today:
            return False
        key = f"{plan.id}:{due.review.week_number}"
        if self.notifier.already_sent(user, KIND_WEEK_REVIEW, key):
            return False
        review = due.review
        if review.sessions_planned == 0:
            return False
        message = week_review_message(
            plan_id=str(plan.id),
            week_number=review.week_number,
            planned_km=review.planned_km,
            done_km=review.done_km,
            sessions_done=review.sessions_done,
            sessions_planned=review.sessions_planned,
            next_week_km=review.next_week_km,
            change_headline=due.change_headline,
        )
        if dry_run:
            logger.info("Dry run: week review for %s: %s", user.id, message.title)
            return True
        return self.notifier.notify(
            user,
            message,
            category=prefs.WEEK_REVIEW,
            kind=KIND_WEEK_REVIEW,
            key=key,
        )

    # ---- helpers ----------------------------------------------------------

    def _active_plan(self, user: User) -> Optional[TrainingPlan]:
        from app.contexts.plan.plan_helpers import (
            current_active_plan,
            decorate_plan_status,
        )
        from app.contexts.plan.repositories import SQLAlchemyPlanRepository
        from app.core.time_utils import local_today

        plans = SQLAlchemyPlanRepository(self.db).list_by_user_recent_first(user.id)
        today = local_today()
        for plan in plans:
            decorate_plan_status(plan, today)
        plan = current_active_plan(plans)
        if plan is None or getattr(plan, "status_label", None) == "Completed":
            return None
        if plan.start_date is None:
            return None
        return plan
