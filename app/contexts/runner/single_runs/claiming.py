"""Pair an imported activity with the single run it completed.

A single run is prescribed before it is run; the activity arrives later through
the ordinary Intervals.icu import, indistinguishable from any other run. This
is where the two are joined — and it has to happen **before** the run mapper
sees the activity. The mapper greedily matches unlinked runs to planned days,
so an unclaimed single run on a plan day would be spent on that day's workout
and the adaptation engine would judge a one-off tempo against a planned easy
run.

Matching is by calendar day and distance, the same evidence the mapper itself
uses. Intervals.icu does pair activities to calendar events, but only for
sessions that were sent to the watch, and a single run does not have to be.

**One run, two sessions.** When the plan also had a run that day and the runner
ran once, day and distance cannot say which session it was. Getting it wrong
is not symmetric: claiming it for the single run leaves the planned day open,
and the plan then adapts to a skip that never happened. So what the run *looked
like* decides — a run that reads as a tempo is the tempo single run, one that
reads as easy is left for the planned easy day — and when the two sessions are
the same kind of run, the plan keeps it.
"""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.contexts.runner.single_runs.planned_days import (
    PlannedRun,
    planned_runs_between,
)
from app.core.training.workouts.single_run import (
    is_similar_distance,
    single_run_family,
)
from app.models import RunLog, SingleRun

logger = logging.getLogger(__name__)

# How far back an unrun single run is still worth matching. Covers a watch
# that uploads days late; beyond that the session is simply one that was
# never done.
_LOOKBACK_DAYS = 7


def _is_the_single_run(
    run: RunLog, single_run: SingleRun, planned: PlannedRun
) -> bool:
    """Whether a lone run was the single run rather than the planned session."""
    wanted = single_run.run_type
    planned_family = single_run_family(planned.workout_type)
    if wanted == planned_family:
        # Same kind of run on the same day: nothing can tell them apart, and
        # the plan is the one that pays for a wrong guess.
        return False

    looks_like = single_run_family(run.effective_workout_type)
    if looks_like == wanted:
        return True
    if looks_like is not None and looks_like == planned_family:
        return False

    # The run's type says nothing either way; fall back to which prescription
    # it is closer to, the single run on a tie (it is the more recent intent).
    distance = run.distance_km or 0.0
    return abs(distance - single_run.distance_km) <= abs(
        distance - planned.distance_km
    )


def claim_completed_single_runs(user_id: str, db: Session, today: date) -> int:
    """Mark the logged runs that completed this runner's pending single runs.

    Only runs not yet tied to a planned day are eligible, so a run the mapper
    has already matched is never taken back. Flushes but does not commit — the
    caller owns the transaction.

    Returns:
        How many single runs were paired with a run.
    """
    since = today - timedelta(days=_LOOKBACK_DAYS)
    claimed_ids = db.query(RunLog.single_run_id).filter(
        RunLog.user_id == user_id, RunLog.single_run_id.isnot(None)
    )
    pending = (
        db.query(SingleRun)
        .filter(
            SingleRun.user_id == user_id,
            SingleRun.date >= since,
            SingleRun.date <= today,
            SingleRun.id.notin_(claimed_ids),
        )
        .order_by(SingleRun.date.asc(), SingleRun.created_at.asc())
        .all()
    )
    if not pending:
        return 0

    open_planned: dict[date, PlannedRun] = {}
    for planned in planned_runs_between(user_id, db, since, today):
        if not planned.completed:
            open_planned.setdefault(planned.on_date, planned)

    claimed = 0
    for single_run in pending:
        day_start = datetime.combine(single_run.date, time.min)
        day_runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= day_start,
                RunLog.date < day_start + timedelta(days=1),
                RunLog.single_run_id.is_(None),
                RunLog.daily_workout_id.is_(None),
            )
            .all()
        )
        candidates = [
            run
            for run in day_runs
            if is_similar_distance(single_run.distance_km, run.distance_km or 0.0)
        ]
        if not candidates:
            continue

        # The run that looks like this session first, then the closest.
        run = min(
            candidates,
            key=lambda r: (
                single_run_family(r.effective_workout_type) != single_run.run_type,
                abs((r.distance_km or 0.0) - single_run.distance_km),
            ),
        )
        # With a second run that day there is one for each session and nothing
        # to arbitrate; the planned day is only at risk when this is the lone
        # run.
        planned = open_planned.get(single_run.date)
        if (
            planned is not None
            and len(day_runs) == 1
            and not _is_the_single_run(run, single_run, planned)
        ):
            continue

        run.single_run_id = single_run.id
        # Imports arrive untagged. The runner told us what this session was,
        # which beats inferring it from pace — but never over a label that
        # came with the activity or that they set themselves.
        if run.workout_type is None:
            run.workout_type = single_run.run_type
        # Flushed per claim so the next single run's candidate query (a second
        # one on the same day) no longer sees this run.
        db.flush()
        claimed += 1

    if claimed:
        logger.info("Claimed %d single run(s) for user %s", claimed, user_id)
    return claimed
