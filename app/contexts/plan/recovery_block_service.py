"""Offer — and start — the recovery block that follows a finished race plan.

The block itself is prescribed in
:mod:`app.core.training.periodization.recovery_block`; this module decides
*when* to offer it and persists it when the runner says yes. It is prepared,
not imposed: the runner sees a preview (how long, how much, from when) and one
tap starts it, because a plan appearing on its own would also start pushing
sessions to a watch nobody asked to fill.

The offer is deliberately narrow, so it never competes with a decision the
runner has already made:

* only for a race plan that has **finished**, within a few weeks of race day —
  after that the race is absorbed and "recovery" is the wrong word;
* never once the runner has **another plan on the go**: they have moved on;
* never twice: once a block exists, the offer becomes a link to it
  (``TrainingPlan.follows_plan_id`` is the record).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.core.race.recovery import easy_days_after
from app.core.training.periodization.plan_calendar import plan_has_ended
from app.core.training.periodization.recovery_block import (
    build_recovery_block,
    peak_weekly_km,
    recovery_prescription,
)
from app.exceptions import ConflictException
from app.models import TrainingPlan

from .plan_creation_helpers import persist_weekly_workouts
from .plan_status import plan_status
from .plan_type_registry import display_label

logger = logging.getLogger(__name__)

RECOVERY_PLAN_TYPE = "recovery"

# How long after race day the block is still offered. Past this the runner has
# either recovered on their own or stopped, and a "recovery" block is neither.
_OFFER_WINDOW = timedelta(weeks=6)


@dataclass(frozen=True)
class RecoveryOffer:
    """A prepared-but-not-started recovery block, as the runner previews it."""

    race_name: str
    weeks: int
    start_date: date
    first_week_km: float
    last_week_km: float
    easy_days: int


def _start_of(plan: TrainingPlan) -> Optional[date]:
    sd = plan.start_date
    return sd.date() if isinstance(sd, datetime) else sd


def _race_km(plan: TrainingPlan) -> float:
    return plan.target_distance_km


def block_start_date(plan_end: date, today: date) -> date:
    """The Monday the block starts on.

    Plans are laid out Monday-first (day 1 renders as "Mon"), so the block
    starts on a Monday. The first week's runs begin on day 3, so a block
    started as late as Wednesday still has every session ahead of the runner;
    from Thursday it waits for next Monday. Never before the race plan ended.
    """
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday if today.weekday() <= 2 else this_monday + timedelta(days=7)
    if start < plan_end:
        start = plan_end + timedelta(days=(7 - plan_end.weekday()) % 7)
    return start


def existing_block(
    plan: TrainingPlan, plans: Sequence[TrainingPlan]
) -> Optional[TrainingPlan]:
    """The recovery block already started from ``plan``, if any."""
    return next((p for p in plans if p.follows_plan_id == plan.id), None)


def recovery_offer(
    plan: TrainingPlan, plans: Sequence[TrainingPlan], today: date
) -> Optional[RecoveryOffer]:
    """What the runner would get by starting a recovery block from ``plan``.

    Args:
        plan: The (possibly) finished race plan.
        plans: All of the runner's plans, ``plan`` included.
        today: The runner's local date.

    Returns:
        The preview, or ``None`` when no block should be offered.
    """
    if plan.plan_type == RECOVERY_PLAN_TYPE:
        return None
    race_km = _race_km(plan)
    start = _start_of(plan)
    if race_km <= 0 or start is None or plan.weeks_duration is None:
        return None
    if not plan_has_ended(start, plan.weeks_duration, today):
        return None
    plan_end = start + timedelta(weeks=plan.weeks_duration)
    if today - plan_end > _OFFER_WINDOW:
        return None
    if existing_block(plan, plans) is not None:
        return None
    if any(
        other.id != plan.id and not plan_status(other, today).completed
        for other in plans
    ):
        return None
    peak = peak_weekly_km(plan.plan_data or [])
    if peak <= 0:
        return None

    prescription = recovery_prescription(race_km)
    return RecoveryOffer(
        race_name=display_label(plan),
        weeks=prescription.weeks,
        start_date=block_start_date(plan_end, today),
        first_week_km=round(peak * prescription.volume_fractions[0]),
        last_week_km=round(peak * prescription.volume_fractions[-1]),
        easy_days=easy_days_after(race_km),
    )


def start_recovery_block(
    plan: TrainingPlan, plans: Sequence[TrainingPlan], db: Session, today: date
) -> TrainingPlan:
    """Build and persist the recovery block that follows ``plan``.

    Idempotent: a second tap (or a retried request) returns the block the first
    one created rather than stacking up a duplicate.

    Raises:
        ConflictException: when no block is on offer for ``plan`` — it has not
            finished, the offer window has passed, or another plan is active.
    """
    already = existing_block(plan, plans)
    if already is not None:
        return already
    offer = recovery_offer(plan, plans, today)
    if offer is None:
        raise ConflictException(
            f"No recovery block on offer for plan {plan.id}",
            user_message="A recovery block isn't available for this plan any more.",
        )

    pace_zones = None
    if plan.vdot:
        from app.core.training.physiology.personal_easy_band import (
            with_personal_easy_band,
        )
        from app.core.training.physiology.vdot_calculator import VDOTCalculator

        # A recovery block is all easy running, so the runner's own easy pace
        # matters here more than anywhere.
        pace_zones = with_personal_easy_band(
            VDOTCalculator.get_pace_zones(plan.vdot), plan.easy_pace_min_km
        )

    plan_data = build_recovery_block(
        race_km=_race_km(plan),
        race_name=offer.race_name,
        peak_km=peak_weekly_km(plan.plan_data or []),
        runs_per_week=plan.max_runs_per_week or 3,
        pace_zones=pace_zones,
    )
    block = TrainingPlan(
        user_id=plan.user_id,
        plan_type=RECOVERY_PLAN_TYPE,
        follows_plan_id=plan.id,
        # No race: the block's "distance" is nothing, and every display
        # surface labels it through the plan-type registry instead.
        target_distance=None,
        current_weekly_km=plan_data[0]["total_km"],
        weeks_duration=len(plan_data),
        max_runs_per_week=plan.max_runs_per_week,
        plan_data=plan_data,
        start_date=datetime.combine(offer.start_date, datetime.min.time()),
        vdot=plan.vdot,
        easy_pace_min_km=plan.easy_pace_min_km,
        max_heart_rate=plan.max_heart_rate,
        body_weight_kg=plan.body_weight_kg,
        hr_zones_data=plan.hr_zones_data,
        # The runner asked for this plan's sessions on their watch; the block
        # is its continuation, so it keeps the same standing opt-in.
        watch_sync_enabled=bool(plan.watch_sync_enabled),
    )
    try:
        db.add(block)
        db.flush()
        persist_weekly_workouts(block, plan_data, db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info(
        "Started %s-week recovery block %s after plan %s",
        len(plan_data),
        block.id,
        plan.id,
    )
    return block
