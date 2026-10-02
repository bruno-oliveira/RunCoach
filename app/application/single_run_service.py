"""Create a one-off workout, and put it on the runner's watch.

A single run needs things from two contexts — the plan's paces and the runner's
logged fitness — which is why it is orchestrated here rather than inside either.

**Where the paces come from.** A runner mid-plan gets the plan's VDOT, so the
tempo they ask for today is run at the same threshold pace as the tempo their
plan gave them on Tuesday; two different "tempo paces" on one calendar would be
indefensible. With no plan in progress the paces come from their recent runs.
With neither, there is no honest pace to give: the session is prescribed by
effort and ``vdot`` is stored NULL rather than guessed.

**The watch half is not a mirror.** A plan is mirrored because it keeps
changing underneath the calendar. A single run is generated once and never
adapted, so it is pushed once, on request. Its event carries its own
``external_id`` namespace, so no plan reconcile can touch it.

**A failed push never costs the workout.** The session is committed before
Intervals.icu is called; an outage leaves the runner with a workout they can
read and re-send, not an error page.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.plan_status import in_progress_plan
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.single_runs import (
    SQLAlchemySingleRunRepository,
    planned_runs_between,
    recent_weekly_km,
)
from app.core.time_utils import local_today, utcnow_naive
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.watch_mirror import (
    build_single_run_event,
    event_hash,
    single_run_external_id,
)
from app.core.training.workouts.single_run import (
    build_single_run,
    distance_for_duration,
    estimated_minutes,
    single_run_family,
)
from app.exceptions import ValidationException
from app.models import RunLog, SingleRun, User

logger = logging.getLogger(__name__)

# How far ahead a single run may be scheduled. It is a session for "today, or
# soon" — anything further out is what a plan is for — and it keeps the event
# inside the window Intervals.icu forwards to the watch.
MAX_DAYS_AHEAD = 14

# How much history the page shows.
HISTORY_DAYS = 60

WATCH_NOT_CONNECTED = "not_connected"
WATCH_AUTH = "auth"
WATCH_PROVIDER = "provider"


@dataclass(frozen=True)
class SingleRunView:
    """A single run plus the derived state the page and API both show."""

    single_run: SingleRun
    completed_run: Optional[RunLog]
    estimated_minutes: Optional[int]

    @property
    def on_watch(self) -> bool:
        return self.single_run.watch_event_hash is not None


def current_vdot(user: User, db: Session, today: date) -> Optional[float]:
    """The fitness a single run should be paced from, or None if unknown."""
    plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(user.id)
    plan = in_progress_plan(plans, today)
    if plan is not None and plan.vdot:
        return float(plan.vdot)
    return RacePredictorService.get_best_recent_vdot(user.id, weeks=12, db=db)


def plan_overlaps(user: User, db: Session, today: date) -> list[dict[str, Any]]:
    """Planned runs a single run could duplicate, for the form to warn about.

    A single run of the same kind and size as that day's planned session is
    almost always a mistake rather than a wish for two identical runs — and if
    the runner then runs once, nothing can tell which session it was (see
    ``claiming``). So the form says so before the duplicate exists. Only
    sessions still to be run, and only those with a single-run equivalent.
    """
    overlaps = []
    window_end = today + timedelta(days=MAX_DAYS_AHEAD)
    for planned in planned_runs_between(user.id, db, today, window_end):
        family = single_run_family(planned.workout_type)
        if planned.completed or family is None:
            continue
        overlaps.append(
            {
                "date": planned.on_date.isoformat(),
                "run_type": family,
                "distance_km": planned.distance_km,
                "url": f"/plan/{planned.plan_id}/day/{planned.workout_id}",
            }
        )
    return overlaps


def create_single_run(
    user: User,
    db: Session,
    *,
    run_type: str,
    distance_km: Optional[float],
    duration_minutes: Optional[float],
    on_date: Optional[date],
) -> SingleRun:
    """Generate and persist a one-off workout.

    Raises:
        ValidationException: The date is out of range, the size is outside what
            the type supports, or a duration was asked for with no fitness on
            record to convert it.
    """
    today = local_today()
    when = on_date or today
    if when < today or when > today + timedelta(days=MAX_DAYS_AHEAD):
        raise ValidationException(
            f"Single run date {when} outside [{today}, +{MAX_DAYS_AHEAD}d]",
            user_message=(
                f"Pick a day between today and {MAX_DAYS_AHEAD} days from now."
            ),
        )

    vdot = current_vdot(user, db, today)
    pace_zones = VDOTCalculator.get_pace_zones(vdot) if vdot else None
    weekly_km = recent_weekly_km(user.id, db, today)

    try:
        if distance_km is None:
            if duration_minutes is None:
                raise ValueError("Give a distance or a duration")
            if pace_zones is None:
                # Minutes only become kilometres through a pace, and inventing
                # one would size the whole session off a number nobody ran.
                raise ValueError(
                    "We don't know your paces yet, so we can't size a run by "
                    "time. Give a distance instead — once you've logged a few "
                    "runs, time works too."
                )
            distance_km = distance_for_duration(
                run_type, duration_minutes, pace_zones, weekly_km
            )
        workout = build_single_run(run_type, distance_km, pace_zones, weekly_km)
    except ValueError as error:
        raise ValidationException(str(error)) from error

    single_run = SingleRun(
        user_id=user.id,
        date=when,
        run_type=run_type,
        distance_km=float(workout["distance"]),
        workout=workout,
        vdot=vdot,
    )
    SQLAlchemySingleRunRepository(db).save(single_run)
    db.commit()
    logger.info(
        "Single run %s created for user %s: %s %.1f km on %s",
        single_run.id,
        user.id,
        run_type,
        single_run.distance_km,
        when,
    )
    return single_run


def view_of(single_run: SingleRun, db: Session) -> SingleRunView:
    """Wrap one single run with its derived state."""
    return list_views([single_run], db)[0]


def list_views(single_runs: list[SingleRun], db: Session) -> list[SingleRunView]:
    """Wrap single runs with the run that completed each, in one query."""
    completed = SQLAlchemySingleRunRepository(db).completed_runs(
        [single_run.id for single_run in single_runs]
    )
    return [
        SingleRunView(
            single_run=single_run,
            completed_run=completed.get(single_run.id),
            estimated_minutes=estimated_minutes(single_run.workout),
        )
        for single_run in single_runs
    ]


def recent_views(user: User, db: Session) -> list[SingleRunView]:
    """The runner's upcoming and recent single runs, newest first."""
    since = local_today() - timedelta(days=HISTORY_DAYS)
    single_runs = SQLAlchemySingleRunRepository(db).list_for_user(
        user.id, since=since, limit=30
    )
    return list_views(single_runs, db)


async def send_to_watch(
    single_run: SingleRun, user: User, db: Session, intervals_service: Any
) -> Optional[str]:
    """Push a single run to the runner's Intervals.icu calendar.

    Returns:
        None on success, otherwise one of the ``WATCH_*`` reasons. Reported
        rather than raised because the caller on the create path has already
        succeeded at the thing the runner asked for.
    """
    from app.infrastructure.integrations.intervals_service import (
        IntervalsAuthorizationError,
    )

    access_token, athlete_id = user.intervals_access_token, user.intervals_athlete_id
    if not access_token or not athlete_id:
        return WATCH_NOT_CONNECTED

    event = build_single_run_event(single_run.id, single_run.date, single_run.workout)
    try:
        # push_workout removes any earlier event with this external_id first:
        # Intervals only re-triggers the watch export on create, so a re-send
        # has to be a delete and a create.
        await intervals_service.push_workout(access_token, athlete_id, event)
    except IntervalsAuthorizationError:
        logger.warning("Single run push unauthorized for user %s", user.id)
        return WATCH_AUTH
    except Exception:
        logger.exception("Single run push failed for user %s", user.id)
        return WATCH_PROVIDER

    single_run.watch_event_hash = event_hash(event)
    single_run.watch_synced_at = utcnow_naive()
    db.commit()
    logger.info("Single run %s pushed to the watch calendar", single_run.id)
    return None


async def delete_single_run(
    single_run: SingleRun, user: User, db: Session, intervals_service: Any
) -> None:
    """Delete a single run and take its session off the watch calendar.

    The calendar cleanup is best-effort and only attempted for a session that
    was sent and has not been run: a stale event is an annoyance, a delete the
    runner cannot complete because Intervals.icu is down is worse.
    """
    still_upcoming = single_run.date >= local_today()
    was_sent = single_run.watch_event_hash is not None
    external_id = single_run_external_id(single_run.id)
    on_date = single_run.date.isoformat()

    SQLAlchemySingleRunRepository(db).delete(single_run)
    db.commit()

    access_token, athlete_id = user.intervals_access_token, user.intervals_athlete_id
    if not (was_sent and still_upcoming and access_token and athlete_id):
        return
    try:
        remote = await intervals_service.fetch_events(
            access_token, athlete_id, on_date, on_date
        )
        # Exact match on our own external_id: the only events this may delete.
        ours = [
            event["id"]
            for event in remote
            if isinstance(event, dict)
            and event.get("external_id") == external_id
            and event.get("id") is not None
        ]
        await intervals_service.delete_events(access_token, athlete_id, ours)
    except Exception:
        logger.exception("Could not remove single run %s from the watch", external_id)
