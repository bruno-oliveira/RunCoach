"""The one push in a pull-only app.

Every coaching surface RunCoach has is computed on page load, so it can only
speak to someone who is already looking — which excludes exactly the runner
worth speaking to, the one who hasn't opened the app in four days. This service
runs on a schedule instead, resolves the counts each guard needs, and hands
them to the pure detector in :mod:`app.core.coaching.outbound_nudge`.

Three things keep it from becoming a mailing list:

* **Consent.** ``User.nudge_email_enabled`` defaults to false. No opt-in, no
  candidate — checked in the query, not after building the message.
* **A floor between emails.** ``settings.nudge_min_interval_days``, read from
  the stored ``last_nudge_email_at`` so it survives restarts.
* **A repeat guard.** The same situation restated in the same words is nagging,
  so a signature that hasn't changed doesn't send.

The bookkeeping is written only when the mailer reports genuine delivery, which
is why :class:`~app.domain.notifications.Mailer` returns a boolean rather than
raising. A misconfigured SMTP host must not mark everyone as emailed.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.coaching.outbound_nudge import (
    OutboundNudge,
    detect_outbound_nudge,
    render_email,
)
from app.core.time_utils import local_today
from app.core.training.plan_calendar import compute_current_week
from app.domain.notifications import EmailMessage, Mailer
from app.infrastructure.config import Settings
from app.infrastructure.config import settings as default_settings
from app.models import ReadinessLog, RunLog, TrainingPlan, User

logger = logging.getLogger(__name__)

# How far back the guards look. A week covers a full plan cycle without letting
# a single bad fortnight-old week keep firing.
_LOOKBACK_DAYS = 7
# Readiness history handed to the detector, newest first.
_READINESS_WINDOW = 10

_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


@dataclass
class NudgeRunSummary:
    """What one scheduled pass did, for the endpoint to report."""

    candidates: int = 0
    nudged: int = 0
    delivered: int = 0
    skipped_rate_limited: int = 0
    skipped_repeat: int = 0
    skipped_no_signal: int = 0
    failed: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "candidates": self.candidates,
            "nudged": self.nudged,
            "delivered": self.delivered,
            "skipped_rate_limited": self.skipped_rate_limited,
            "skipped_repeat": self.skipped_repeat,
            "skipped_no_signal": self.skipped_no_signal,
            "failed": self.failed,
        }


class OutboundNudgeService:
    """Finds runners worth interrupting and emails at most one thing each."""

    def __init__(
        self,
        db: Session,
        mailer: Mailer,
        config: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.mailer = mailer
        self.settings = config or default_settings

    # ---- entry point ----------------------------------------------------

    def run(
        self, *, dry_run: bool = False, limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Evaluate every opted-in runner and send at most one email each.

        ``dry_run`` resolves signals and renders nothing — useful for checking
        who *would* be mailed without touching an SMTP server.
        """
        summary = NudgeRunSummary()
        today = local_today()

        query = self.db.query(User).filter(
            User.nudge_email_enabled.is_(True),
            User.email.isnot(None),
        )
        if limit:
            query = query.limit(limit)

        for user in query.all():
            summary.candidates += 1
            try:
                self._process_user(user, today, summary, dry_run=dry_run)
            except Exception:
                # One runner's bad data must not abort the batch.
                logger.exception("Outbound nudge failed for user %s", user.id)
                summary.failed += 1

        if not dry_run:
            self.db.commit()
        return summary.as_dict()

    # ---- per-runner ------------------------------------------------------

    def _process_user(
        self,
        user: User,
        today: date,
        summary: NudgeRunSummary,
        *,
        dry_run: bool,
    ) -> None:
        if self._rate_limited(user):
            summary.skipped_rate_limited += 1
            return

        plan = self._active_plan(user, today)
        if plan is None:
            summary.skipped_no_signal += 1
            return

        nudge = self._detect(user, plan, today)
        if nudge is None:
            summary.skipped_no_signal += 1
            return

        if nudge.signature == (user.last_nudge_email_signature or ""):
            summary.skipped_repeat += 1
            return

        summary.nudged += 1
        if dry_run:
            logger.info("Dry run: would nudge %s with %s", user.id, nudge.signature)
            return

        if self._send(user, nudge):
            summary.delivered += 1
            user.last_nudge_email_at = _utcnow()
            user.last_nudge_email_signature = nudge.signature
        else:
            summary.failed += 1

    def _rate_limited(self, user: User) -> bool:
        last = user.last_nudge_email_at
        if last is None:
            return False
        floor = _utcnow() - timedelta(days=self.settings.nudge_min_interval_days)
        return last > floor

    def _active_plan(self, user: User, today: date) -> Optional[TrainingPlan]:
        """The plan the runner is mid-way through, or ``None``.

        A finished plan has nothing to be behind on, and an unstarted one has
        nothing to have missed — neither is worth an email.
        """
        plans = (
            self.db.query(TrainingPlan)
            .filter(
                TrainingPlan.user_id == user.id,
                TrainingPlan.start_date.isnot(None),
            )
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )
        for plan in plans:
            start = _to_date(plan.start_date)
            if start is None:
                continue
            week = compute_current_week(start, today, pre_start=0)
            if week and 1 <= week <= plan.weeks_duration:
                return plan
        return None

    def _detect(
        self, user: User, plan: TrainingPlan, today: date
    ) -> Optional[OutboundNudge]:
        since = today - timedelta(days=_LOOKBACK_DAYS)
        return detect_outbound_nudge(
            plan_id=plan.id,
            days_since_last_run=self._days_since_last_run(user, today),
            sessions_missed_recently=self._sessions_missed(plan, user, today, since),
            next_session_label=self._next_session_label(plan, today),
            recent_readiness_scores=self._readiness_scores(user, today),
            **self._adaptation_signal(plan, user),
        )

    # ---- signals ---------------------------------------------------------

    def _days_since_last_run(self, user: User, today: date) -> Optional[int]:
        last = (
            self.db.query(RunLog.date)
            .filter(RunLog.user_id == user.id, RunLog.date.isnot(None))
            .order_by(RunLog.date.desc())
            .first()
        )
        last_date = _to_date(last[0]) if last else None
        if last_date is None:
            return None
        return max(0, (today - last_date).days)

    def _sessions_missed(
        self, plan: TrainingPlan, user: User, today: date, since: date
    ) -> int:
        """Scheduled sessions in the lookback window with nothing logged on them.

        Rest days don't count as missed, and today doesn't either — the day
        isn't over.
        """
        start = _to_date(plan.start_date)
        if start is None:
            return 0

        logged_days = {
            _to_date(row[0])
            for row in self.db.query(RunLog.date)
            .filter(
                RunLog.user_id == user.id,
                RunLog.date >= since,
                RunLog.date.isnot(None),
            )
            .all()
            if row[0] is not None
        }

        missed = 0
        for week in plan.plan_data or []:
            week_num = week.get("week")
            if not week_num:
                continue
            for workout in week.get("daily_workouts", []) or []:
                day = workout.get("day")
                if not day:
                    continue
                if (workout.get("type") or "rest") in ("rest", "off"):
                    continue
                if not (workout.get("distance") or workout.get("duration_min")):
                    continue
                scheduled = start + timedelta(weeks=week_num - 1, days=day - 1)
                if since <= scheduled < today and scheduled not in logged_days:
                    missed += 1
        return missed

    def _next_session_label(self, plan: TrainingPlan, today: date) -> Optional[str]:
        """``"Thursday's tempo"`` for the next hard session, if one is close."""
        start = _to_date(plan.start_date)
        if start is None:
            return None
        horizon = today + timedelta(days=_LOOKBACK_DAYS)

        best: Optional[tuple[date, str]] = None
        for week in plan.plan_data or []:
            week_num = week.get("week")
            if not week_num:
                continue
            for workout in week.get("daily_workouts", []) or []:
                day = workout.get("day")
                wtype = (workout.get("type") or "").lower()
                if not day or wtype in ("rest", "off", "easy", "recovery"):
                    continue
                scheduled = start + timedelta(weeks=week_num - 1, days=day - 1)
                if today <= scheduled <= horizon and (
                    best is None or scheduled < best[0]
                ):
                    best = (scheduled, wtype.replace("_", " "))
        if best is None:
            return None
        return f"{_DAY_NAMES[best[0].isoweekday() - 1]}'s {best[1]}"

    def _readiness_scores(self, user: User, today: date) -> List[Optional[float]]:
        """Newest-first scores, with a ``None`` for every morning not checked in.

        The gap matters: the detector treats a missing morning as breaking a
        run of rough ones, because we can't claim someone felt bad on a day
        they never told us about.
        """
        since = today - timedelta(days=_READINESS_WINDOW)
        rows = (
            self.db.query(ReadinessLog.date, ReadinessLog.score)
            .filter(ReadinessLog.user_id == user.id, ReadinessLog.date >= since)
            .all()
        )
        by_day = {_to_date(row[0]): row[1] for row in rows if row[0] is not None}
        return [
            by_day.get(today - timedelta(days=offset))
            for offset in range(_READINESS_WINDOW)
        ]

    def _adaptation_signal(self, plan: TrainingPlan, user: User) -> Dict[str, Any]:
        """Forward whatever the in-app nudge engine already found.

        Imported lazily and guarded: this walks the full signal engine, and a
        failure there must not cost the runner the simpler guards above.
        """
        try:
            from app.contexts.plan.adaptation.proactive_nudge import get_nudge

            nudge = get_nudge(plan.id, user.id, self.db)
        except Exception:
            logger.warning(
                "Proactive nudge lookup failed for plan %s", plan.id, exc_info=True
            )
            return {}
        if not nudge:
            return {}
        return {
            "adaptation_headline": nudge.get("headline"),
            "adaptation_detail": nudge.get("detail"),
            "adaptation_signature": nudge.get("signature"),
        }

    # ---- delivery --------------------------------------------------------

    def _send(self, user: User, nudge: OutboundNudge) -> bool:
        assert user.email is not None  # guaranteed by the candidate query
        text, html = render_email(
            nudge,
            base_url=self.settings.public_base_url,
            unsubscribe_url=unsubscribe_url(user.id, self.settings),
            name=(user.name or "").split(" ")[0] or None,
        )
        return self.mailer.send(
            EmailMessage(to=user.email, subject=nudge.subject, text=text, html=html)
        )


# ---- unsubscribe tokens ---------------------------------------------------


def unsubscribe_token(user_id: str, config: Optional[Settings] = None) -> str:
    """HMAC of the user id under the app signing key.

    Not a JWT: an unsubscribe link lives in an inbox forever, so it must not
    expire, and it grants exactly one irreversible-in-the-safe-direction
    action. Keyed so a stranger can't unsubscribe someone by guessing an id.
    """
    cfg = config or default_settings
    return hmac.new(
        cfg.secret_key.encode(), f"unsubscribe:{user_id}".encode(), hashlib.sha256
    ).hexdigest()


def verify_unsubscribe_token(
    user_id: str, token: str, config: Optional[Settings] = None
) -> bool:
    return hmac.compare_digest(unsubscribe_token(user_id, config), token or "")


def unsubscribe_url(user_id: str, config: Optional[Settings] = None) -> str:
    cfg = config or default_settings
    base = cfg.public_base_url.rstrip("/")
    return f"{base}/unsubscribe?u={user_id}&t={unsubscribe_token(user_id, cfg)}"


# ---- helpers --------------------------------------------------------------


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
