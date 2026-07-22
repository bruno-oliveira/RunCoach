"""Home-page stats: pace evolution and HR-zone evolution over recent months.

Powers the discreet right-rail panel on the signed-in home page — the quiet
"you're getting fitter" story. Two month-bucketed series:

  * **Pace evolution** — median *easy-effort* pace per month, so we compare
    like-for-like (a couple of races never masquerade as a fitness swing) and a
    genuinely faster easy pace reads as the aerobic gain it is.
  * **HR-zone evolution** — how each month's running time distributes across the
    runner's *canonical* HR zones (the one source of truth), classified from each
    run's average HR weighted by its duration.

No configuration: one opinionated 6-month window that naturally shows fewer
months for newer runners. Both series degrade honestly — too little data yields a
``has_data: False`` block with a plain-English reason, never an empty axis.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.hr_zone_service import resolve_zones_for_user
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.models import RunLog, User

# One opinionated window. ~6 calendar months; bucketing only emits months that
# actually have runs, so a newer runner simply sees a shorter line.
WINDOW_MONTHS = 6
_WINDOW_DAYS = 31 * WINDOW_MONTHS

# A line needs at least two month points to say anything.
_MIN_MONTHS_FOR_CHART = 2
# Below this many easy runs the easy-only filter is too sparse to trust, so we
# fall back to charting all runs (and say so via ``effort_basis``).
_MIN_EASY_RUNS = 4
# A monthly median built from a single run is noise; require a couple.
_MIN_RUNS_PER_MONTH = 2

# Pace change (per km) below this is visual noise, not a real trend.
_PACE_TREND_MIN_DELTA_SEC = 3
# Easy-zone share shift below this is not worth a claim.
_EASY_SHARE_MIN_DELTA = 0.06


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _month_label(month_key: str) -> str:
    return datetime.strptime(month_key, "%Y-%m").strftime("%b")


def _bucket_median_pace(
    runs: list[RunLog],
) -> list[tuple[str, float]]:
    """Median ``avg_pace_min_km`` per month, chronological, months with enough runs."""
    by_month: dict[str, list[float]] = {}
    for run in runs:
        if run.date is None or not run.avg_pace_min_km or run.avg_pace_min_km <= 0:
            continue
        by_month.setdefault(_month_key(run.date), []).append(run.avg_pace_min_km)
    points = [
        (month, statistics.median(paces))
        for month, paces in by_month.items()
        if len(paces) >= _MIN_RUNS_PER_MONTH
    ]
    points.sort(key=lambda p: p[0])
    return points[-WINDOW_MONTHS:]


class HomeStatsService:
    """Build the home-page pace and HR-zone evolution series for a runner."""

    @staticmethod
    def build(user: User, db: Session) -> dict:
        since = _now_naive() - timedelta(days=_WINDOW_DAYS)
        runs = SQLAlchemyRunRepository(db).list_recent_for_user(user.id, since=since)
        return {
            "window_months": WINDOW_MONTHS,
            "pace_evolution": HomeStatsService._pace_evolution(runs),
            "hr_zone_evolution": HomeStatsService._hr_zone_evolution(runs, user, db),
        }

    # -- Pace ---------------------------------------------------------------

    @staticmethod
    def _pace_evolution(runs: list[RunLog]) -> dict:
        easy = [r for r in runs if r.effort_class == "easy_effort"]
        if len(easy) >= _MIN_EASY_RUNS:
            points = _bucket_median_pace(easy)
            basis = "easy"
        else:
            points = []
            basis = "easy"
        # Fall back to all runs when the easy-only series is too thin to draw.
        if len(points) < _MIN_MONTHS_FOR_CHART:
            points = _bucket_median_pace(runs)
            basis = "all"

        if len(points) < _MIN_MONTHS_FOR_CHART:
            return {
                "has_data": False,
                "empty_reason": "Log a few more runs to see your pace trend.",
            }

        series = [
            {"month": m, "label": _month_label(m), "pace_min_km": round(p, 3)}
            for m, p in points
        ]
        return {
            "has_data": True,
            "effort_basis": basis,
            "points": series,
            "trend": _pace_trend(points, basis),
        }

    # -- HR zones -----------------------------------------------------------

    @staticmethod
    def _hr_zone_evolution(runs: list[RunLog], user: User, db: Session) -> dict:
        zones = resolve_zones_for_user(user, db)
        # (month, zone_number) -> accumulated minutes.
        minutes: dict[tuple[str, int], float] = {}
        month_totals: dict[str, float] = {}
        for run in runs:
            if run.date is None or not run.avg_heart_rate:
                continue
            weight = run.duration_minutes if run.duration_minutes else 1.0
            zone = HRZoneCalculator.classify_hr(run.avg_heart_rate, zones)
            month = _month_key(run.date)
            minutes[(month, zone)] = minutes.get((month, zone), 0.0) + weight
            month_totals[month] = month_totals.get(month, 0.0) + weight

        present_months = sorted(month_totals.keys())[-WINDOW_MONTHS:]
        if len(present_months) < _MIN_MONTHS_FOR_CHART:
            return {
                "has_data": False,
                "empty_reason": (
                    "Connect your watch — heart-rate runs unlock your zone trend."
                ),
            }

        zone_meta = [(z["zone"], z["name"]) for z in zones]
        series = []
        for zone_number, name in zone_meta:
            data = []
            for month in present_months:
                total = month_totals[month]
                share = minutes.get((month, zone_number), 0.0) / total if total else 0.0
                data.append(round(share * 100, 1))
            series.append({"zone": zone_number, "name": name, "data": data})

        return {
            "has_data": True,
            "months": present_months,
            "labels": [_month_label(m) for m in present_months],
            "series": series,
            "takeaway": _hr_zone_takeaway(present_months, month_totals, minutes),
        }


def _pace_trend(points: list[tuple[str, float]], basis: str) -> dict:
    """Plain-English pace trend from the first vs last monthly median."""
    first_pace = points[0][1]
    last_pace = points[-1][1]
    delta_sec = round((last_pace - first_pace) * 60)  # negative == faster now
    months_span = len(points) - 1
    span_text = f"{months_span} month{'s' if months_span != 1 else ''}"
    qualifier = "easy pace" if basis == "easy" else "pace"

    if delta_sec <= -_PACE_TREND_MIN_DELTA_SEC:
        return {
            "direction": "faster",
            "delta_sec_per_km": abs(delta_sec),
            "summary": f"Your {qualifier} is {abs(delta_sec)}s/km quicker than {span_text} ago.",
        }
    if delta_sec >= _PACE_TREND_MIN_DELTA_SEC:
        return {
            "direction": "slower",
            "delta_sec_per_km": delta_sec,
            "summary": f"Your {qualifier} has eased {delta_sec}s/km over the last {span_text}.",
        }
    return {
        "direction": "steady",
        "delta_sec_per_km": 0,
        "summary": f"Your {qualifier} is holding steady over the last {span_text}.",
    }


def _hr_zone_takeaway(
    months: list[str],
    month_totals: dict[str, float],
    minutes: dict[tuple[str, int], float],
) -> Optional[str]:
    """Describe the shift in easy-zone (Z1+Z2) share, first month vs last."""

    def easy_share(month: str) -> Optional[float]:
        total = month_totals.get(month, 0.0)
        if not total:
            return None
        easy = minutes.get((month, 1), 0.0) + minutes.get((month, 2), 0.0)
        return easy / total

    first = easy_share(months[0])
    last = easy_share(months[-1])
    if first is None or last is None:
        return None
    delta = last - first
    if delta >= _EASY_SHARE_MIN_DELTA:
        return "More of your running sits in the easy zones — your aerobic base is deepening."
    if delta <= -_EASY_SHARE_MIN_DELTA:
        return "You've been spending more time at higher intensity lately."
    return "Your intensity mix has held steady across these months."
