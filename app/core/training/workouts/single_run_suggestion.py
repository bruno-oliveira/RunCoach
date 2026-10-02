"""Pick the single run a runner should do today.

The form asks "what kind of run, how far?" — which is the question a runner
opens a coaching app to have answered. This module answers it from what the
runner has actually done: how recently they ran hard, how much of their recent
volume was easy, how they slept, and whether a plan already owns their quality
work.

It is a **default, not a gate**: the form is pre-filled with the pick and the
runner can still choose anything. So the rules lean conservative — every doubt
resolves to an easy run, because an unnecessary easy day costs nothing and an
unnecessary hard one is how people get hurt.

The rules are ordered, and the first that applies wins. Reasons are returned as
stable keys rather than prose so the page can translate them.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from app.core.coaching.intensity_split import TOO_HARD, IntensitySplit
from app.core.training.workouts.single_run import max_distance_km, min_distance_km

# A check-in score under this is the "run-down" band the check-in card uses.
LOW_READINESS = 45.0

# Days of nothing after which a runner is coming back, not carrying on.
_LAYOFF_DAYS = 10
# Hard sessions need this many days between them.
_HARD_SPACING_DAYS = 3
# A long run is "due" when none has been done for this long…
_LONG_RUN_EVERY_DAYS = 7
# …and only for a runner with enough volume for one to make sense.
_LONG_RUN_MIN_WEEKLY_KM = 15.0

_DEFAULT_EASY_KM = 5.0
_EASY_CEILING_KM = 10.0
_SHORT_SHARE = 0.7
_REST_DAY_CEILING_KM = 5.0

# Reason keys (the page maps each to a sentence).
REST_DAY = "rest_day"
REST_DAY_LOW = "rest_day_low"
LOW_READINESS_REASON = "low_readiness"
NO_HISTORY = "no_history"
COMING_BACK = "coming_back"
HARD_RECENTLY = "hard_recently"
PLAN_TODAY = "plan_today"
TOO_MUCH_HARD = "too_hard"
PLAN_OWNS_QUALITY = "plan_owns_quality"
LONG_DUE = "long_due"
QUALITY_DUE = "quality_due"
STEADY = "steady"


@dataclass(frozen=True)
class RecentRun:
    """One logged run, reduced to what the pick needs."""

    day: date
    distance_km: float
    # The single-run family ("easy" | "tempo" | "interval" | "long"), if any.
    family: Optional[str]
    hard: bool


@dataclass(frozen=True)
class Suggestion:
    run_type: str
    distance_km: float
    reason: str


def _half_km(value: float) -> float:
    return round(value * 2) / 2


def _clamp(run_type: str, distance_km: float) -> float:
    low, high = min_distance_km(run_type), max_distance_km(run_type)
    return _half_km(min(max(distance_km, low), high))


def _typical_easy_km(runs: Sequence[RecentRun], weekly_km: float) -> float:
    """The length of this runner's ordinary easy day."""
    # Untyped runs are easy days too — most imports carry no type at all.
    easy = sorted(
        run.distance_km for run in runs if not run.hard and run.family != "long"
    )
    if easy:
        typical = easy[len(easy) // 2]
    elif weekly_km > 0:
        typical = weekly_km / 4.0
    else:
        typical = _DEFAULT_EASY_KM
    return min(typical, _EASY_CEILING_KM)


def _days_since(runs: Sequence[RecentRun], today: date, *, hard: bool) -> Optional[int]:
    days = [(today - run.day).days for run in runs if run.hard or not hard]
    return min(days) if days else None


def suggest_single_run(
    *,
    today: date,
    runs: Sequence[RecentRun],
    weekly_km: float,
    split: Optional[IntensitySplit],
    readiness_score: Optional[float],
    has_plan: bool,
    planned_today: bool,
    rest_day: bool = False,
) -> Suggestion:
    """Choose a type and distance for today's single run.

    Args:
        today: The runner's local day.
        runs: Their runs from the last four weeks (any order).
        weekly_km: Recent average weekly volume.
        split: Their easy/hard split, or None when there is too little data.
        readiness_score: Today's check-in or wearable score (0–100), if any.
        has_plan: A training plan is in progress. The plan then owns the
            quality and long sessions, and an extra run is always easy.
        planned_today: That plan has a run still to do today.
        rest_day: The runner arrived from the plan's rest-day card. The answer
            is then a short easy run whatever else is true — the link promised
            something that would not undo the rest.
    """
    typical = _typical_easy_km(runs, weekly_km)
    easy = _clamp("easy", typical)
    short = _clamp("easy", typical * _SHORT_SHARE)
    low = readiness_score is not None and readiness_score < LOW_READINESS

    if rest_day:
        gentle = min(short, _REST_DAY_CEILING_KM)
        return Suggestion("easy", gentle, REST_DAY_LOW if low else REST_DAY)
    if low:
        return Suggestion("easy", short, LOW_READINESS_REASON)
    if not runs:
        return Suggestion("easy", short, NO_HISTORY)

    since_any = _days_since(runs, today, hard=False)
    if since_any is not None and since_any >= _LAYOFF_DAYS:
        return Suggestion("easy", short, COMING_BACK)

    since_hard = _days_since(runs, today, hard=True)
    if since_hard is not None and since_hard < _HARD_SPACING_DAYS:
        return Suggestion("easy", easy, HARD_RECENTLY)
    if planned_today:
        return Suggestion("easy", short, PLAN_TODAY)
    if split is not None and split.verdict == TOO_HARD:
        return Suggestion("easy", easy, TOO_MUCH_HARD)
    if has_plan:
        return Suggestion("easy", easy, PLAN_OWNS_QUALITY)

    long_days = [(today - run.day).days for run in runs if run.family == "long"]
    long_due = not long_days or min(long_days) >= _LONG_RUN_EVERY_DAYS
    if long_due and weekly_km >= _LONG_RUN_MIN_WEEKLY_KM:
        longest = max(run.distance_km for run in runs)
        # About a third of the week, and never a jump past what they have
        # recently covered in one go.
        target = min(weekly_km * 0.33, longest * 1.1)
        return Suggestion("long", _clamp("long", target), LONG_DUE)

    # Enough history to judge, mostly easy, and no hard session lately: this is
    # the one branch that prescribes intensity. Alternate the two kinds.
    if split is not None:
        last = {
            family: min(
                ((today - run.day).days for run in runs if run.family == family),
                default=None,
            )
            for family in ("tempo", "interval")
        }
        tempo_last, interval_last = last["tempo"], last["interval"]
        tempo_is_staler = tempo_last is None or (
            interval_last is not None and tempo_last >= interval_last
        )
        run_type = "tempo" if tempo_is_staler else "interval"
        return Suggestion(run_type, _clamp(run_type, weekly_km * 0.2), QUALITY_DUE)

    return Suggestion("easy", easy, STEADY)
