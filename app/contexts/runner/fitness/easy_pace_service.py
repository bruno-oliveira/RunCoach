"""The pace a runner currently jogs at — read from their own logged runs.

The I/O half of ``core/training/physiology/personal_easy_band``: it finds the
top of the runner's aerobic heart-rate zone and the runs of the last few weeks,
and lets the pure module decide which were easy and what their median is.

One function answers "what is this runner's easy pace today?" for every
surface that prescribes or reports it — plan generation, the sync-time
re-pace, a single run, and the home trends rail — so the number a runner is
shown is the number they are given.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.hr_zone_service import (
    get_user_max_hr,
    get_user_threshold_hr,
    resolve_zones_for_user,
)
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.core.training.physiology.personal_easy_band import (
    EASY_PACE_WINDOW_DAYS,
    EasyRunSample,
    personal_easy_pace,
)
from app.models import RunLog, User

_AEROBIC_ZONE = 2
# Anchor sources that are a formula rather than something the runner's heart
# did. Zones built on nothing else cannot say which runs were easy.
_GUESSED_MAX_HR = ("estimated", "default")
_NO_THRESHOLD = "none"


def easy_hr_ceiling(user: User, db: Session) -> Optional[int]:
    """Top of the runner's aerobic zone in bpm, or ``None`` when it is a guess.

    The zones are always computable — an age formula will produce them — but a
    ceiling from a formula would sort runs into easy and not-easy by a number
    the runner's body never produced. It counts only once a threshold or a max
    heart rate is known from the runner themselves, their watch, or their runs.
    """
    _, max_source = get_user_max_hr(
        user.id, db, user_age=user.age, user_max_hr=user.max_hr
    )
    _, threshold_source = get_user_threshold_hr(user, db)
    if max_source in _GUESSED_MAX_HR and threshold_source == _NO_THRESHOLD:
        return None
    for zone in resolve_zones_for_user(user, db):
        if zone.get("zone") == _AEROBIC_ZONE:
            return zone.get("max_bpm")
    return None


def _as_sample(run: RunLog) -> EasyRunSample:
    return EasyRunSample(
        pace_min_km=run.avg_pace_min_km,
        avg_heart_rate=run.avg_heart_rate,
        distance_km=run.distance_km,
        elevation_gain_m=run.elevation_gain_m,
    )


def current_easy_pace(user_id: Optional[str], db: Session) -> Optional[float]:
    """The runner's measured easy pace (min/km), or ``None`` with too little to go on."""
    user = db.get(User, user_id) if user_id else None
    if user is None:
        return None
    ceiling = easy_hr_ceiling(user, db)
    if ceiling is None:
        return None
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=EASY_PACE_WINDOW_DAYS
    )
    runs = SQLAlchemyRunRepository(db).list_recent_for_user(user.id, since=since)
    return personal_easy_pace((_as_sample(run) for run in runs), ceiling)
