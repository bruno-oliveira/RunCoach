"""The Sunday look back: planned vs done for one plan week, in plain numbers.

Used twice — the Week review card at the head of the plan on Sundays and
Mondays, and the Sunday-evening push — so the page and the lock screen can
never disagree about how the week went.

"Done" is judged by *date*, not by the run mapper's links: a runner who swapped
Tuesday's run to Wednesday still did a session, and a run on a planned rest day
still counts toward the week's kilometres (just not toward sessions, because it
didn't fulfil one). Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

# Ratio bands (done / planned km). Around a tenth either side of the plan is
# "on plan" for any coach; much beyond the top is worth a word about recovery.
_ON_PLAN_LOW = 0.9
_ON_PLAN_HIGH = 1.15
_SHORT_LOW = 0.6


@dataclass(frozen=True)
class WeekReview:
    week_number: int
    planned_km: float
    done_km: float
    sessions_planned: int
    sessions_done: int
    next_week_km: Optional[float]
    verdict: str  # "on_plan" | "over" | "short" | "light" | "nothing_planned"
    line: str
    missed_days: List[str]

    @property
    def completion_pct(self) -> int:
        if self.planned_km <= 0:
            return 0
        return round(100 * self.done_km / self.planned_km)


_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _is_session(workout: Mapping[str, Any]) -> bool:
    kind = (workout.get("type") or "rest").lower()
    if kind in ("rest", "off"):
        return False
    return bool(workout.get("distance") or workout.get("duration_min"))


def week_planned_km(week: Optional[Mapping[str, Any]]) -> float:
    if not week:
        return 0.0
    return round(
        sum(
            float(w.get("distance") or 0)
            for w in week.get("daily_workouts", []) or []
            if _is_session(w)
        ),
        1,
    )


def build_week_review(
    week: Mapping[str, Any],
    *,
    week_start: date,
    runs: Iterable[Tuple[date, float]],
    next_week: Optional[Mapping[str, Any]] = None,
) -> WeekReview:
    """Summarise ``week`` against the runs logged between its Monday and Sunday.

    ``runs`` is ``(local date, km)`` pairs; anything outside the week is ignored.
    """
    week_end = week_start + timedelta(days=7)
    km_by_day: dict[date, float] = {}
    for day, km in runs:
        if week_start <= day < week_end:
            km_by_day[day] = km_by_day.get(day, 0.0) + float(km or 0)

    planned_days: Sequence[Mapping[str, Any]] = [
        w for w in week.get("daily_workouts", []) or [] if _is_session(w)
    ]
    sessions_done = 0
    missed: List[str] = []
    for workout in planned_days:
        day_num = int(workout.get("day") or 0)
        if not 1 <= day_num <= 7:
            continue
        on = week_start + timedelta(days=day_num - 1)
        if km_by_day.get(on, 0) > 0:
            sessions_done += 1
        else:
            missed.append(_DAY_NAMES[day_num - 1])

    planned_km = week_planned_km(week)
    done_km = round(sum(km_by_day.values()), 1)
    verdict, line = _verdict(planned_km, done_km)
    next_km = week_planned_km(next_week) if next_week else None

    return WeekReview(
        week_number=int(week.get("week") or 0),
        planned_km=planned_km,
        done_km=done_km,
        sessions_planned=len(planned_days),
        sessions_done=sessions_done,
        next_week_km=next_km,
        verdict=verdict,
        line=line,
        missed_days=missed,
    )


def _verdict(planned: float, done: float) -> Tuple[str, str]:
    if planned <= 0:
        return "nothing_planned", "A rest week on the plan."
    ratio = done / planned
    gap = round(abs(planned - done), 1)
    gap_txt = f"{int(gap)}" if gap == int(gap) else f"{gap}"
    if _ON_PLAN_LOW <= ratio <= _ON_PLAN_HIGH:
        return "on_plan", "Right on plan."
    if ratio > _ON_PLAN_HIGH:
        return "over", f"{gap_txt} km over plan — protect the easy days next week."
    if ratio >= _SHORT_LOW:
        return "short", f"{gap_txt} km short of plan."
    return "light", "Much lighter than planned."
