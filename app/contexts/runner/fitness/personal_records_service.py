"""Personal records detection and tracking service.

Finds best performances across standard race distances, tracks PR
progression over time, and computes improvement deltas.
"""

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.models import RunLog
from app.utils import format_pace, format_pace_bare

# Standard distances with tolerance for GPS drift
DISTANCE_BUCKETS = [
    {
        "name": "1K",
        "target_km": 1.0,
        "tolerance": 0.15,
        "min_km": 0.85,
        "icon": "sprint",
    },
    {"name": "5K", "target_km": 5.0, "tolerance": 0.5, "min_km": 4.5, "icon": "race"},
    {"name": "10K", "target_km": 10.0, "tolerance": 1.0, "min_km": 9.0, "icon": "race"},
    {
        "name": "Half Marathon",
        "target_km": 21.1,
        "tolerance": 1.5,
        "min_km": 20.0,
        "icon": "medal",
    },
    {
        "name": "Marathon",
        "target_km": 42.195,
        "tolerance": 2.0,
        "min_km": 40.0,
        "icon": "trophy",
    },
]


class PersonalRecordsService:
    """Detects and tracks personal records across standard distances."""

    @staticmethod
    def get_personal_records(user_id: str, db: Session) -> Dict[str, Any]:
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.distance_km.isnot(None),
                RunLog.duration_minutes.isnot(None),
                RunLog.duration_minutes > 0,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        if not runs:
            return {"available": False, "records": [], "general": []}

        distance_records = _build_distance_records(runs)
        general = _build_general_records(runs)

        return {
            "available": True,
            "distance_records": distance_records,
            "general": general,
            "total_runs": len(runs),
        }


def _extreme_by(
    runs: List[RunLog],
    getter: Callable[[RunLog], Optional[float]],
    *,
    largest: bool,
) -> tuple[Optional[float], Optional[RunLog]]:
    """The run with the largest/smallest non-None value of ``getter``, and it.

    Every caller here used to hand ``max``/``min`` a key function returning
    ``float | None`` — the columns behind these attributes are nullable, so any
    single run missing a distance, pace or VDOT made the comparison raise
    ``TypeError`` and lost the entire records payload. Filtering the Nones first
    also means the value comes back narrowed, so no caller has to re-prove it.
    """
    candidates = [(value, run) for run in runs if (value := getter(run)) is not None]
    if not candidates:
        return None, None
    value, run = (max if largest else min)(candidates, key=lambda pair: pair[0])
    return value, run


def _build_distance_records(runs: List[RunLog]) -> List[Dict[str, Any]]:
    """Find best time for each standard distance bucket."""
    records = []

    for bucket in DISTANCE_BUCKETS:
        # A bucket needs both a distance and a duration: the comparisons below
        # and the pace arithmetic raise if either is missing (both are nullable
        # columns, so any imported run without a distance broke the page).
        matching = [
            r
            for r in runs
            if r.distance_km is not None
            and r.duration_minutes is not None
            and abs(r.distance_km - bucket["target_km"]) <= bucket["tolerance"]
            and r.distance_km >= bucket["min_km"]
        ]
        if not matching:
            continue

        # Walk chronologically, tracking PR progression
        best_pace = float("inf")
        pr_history: List[Dict] = []

        for run in matching:
            distance_km = run.distance_km
            duration_minutes = run.duration_minutes
            if distance_km is None or duration_minutes is None:
                continue  # excluded above; restated so the checker can see it
            pace = duration_minutes / distance_km
            if pace < best_pace:
                prev_pace = best_pace if best_pace < float("inf") else None
                best_pace = pace
                total_secs = int(duration_minutes * 60)
                entry: Dict[str, Any] = {
                    "date": run.date.isoformat() if run.date else None,
                    "distance_km": round(distance_km, 2),
                    "duration_seconds": total_secs,
                    "duration_formatted": VDOTCalculator.format_duration(total_secs),
                    "pace_min_km": round(pace, 2),
                    "pace_formatted": format_pace_bare(pace),
                    "vdot": run.vdot,
                }
                if prev_pace is not None:
                    improvement_secs = (prev_pace - pace) * distance_km * 60
                    entry["improvement_seconds"] = round(improvement_secs, 1)
                pr_history.append(entry)

        if not pr_history:
            continue

        current_pr = pr_history[-1]
        records.append(
            {
                "distance_name": bucket["name"],
                "target_km": bucket["target_km"],
                "icon": bucket["icon"],
                "current_pr": current_pr,
                "attempts": len(matching),
                "pr_count": len(pr_history),
                "history": pr_history,
            }
        )

    return records


def _build_general_records(runs: List[RunLog]) -> List[Dict[str, Any]]:
    """Longest run, fastest overall pace, best VDOT."""
    general = []

    longest_km, longest = _extreme_by(runs, lambda r: r.distance_km, largest=True)
    if longest is not None and longest_km is not None:
        general.append(
            {
                "type": "longest_run",
                "label": "Longest Run",
                "value": round(longest_km, 1),
                "unit": "km",
                "date": longest.date.isoformat() if longest.date else None,
                "formatted": f"{round(longest_km, 1)} km",
            }
        )

    # Pace only means something over a few km, so short runs are excluded along
    # with any run missing a pace or a distance.
    pace_runs = [
        r
        for r in runs
        if r.avg_pace_min_km
        and r.avg_pace_min_km > 0
        and r.distance_km is not None
        and r.distance_km >= 3.0
    ]
    fastest_pace, fastest = _extreme_by(
        pace_runs, lambda r: r.avg_pace_min_km, largest=False
    )
    if fastest is not None and fastest_pace is not None:
        fastest_km = fastest.distance_km or 0.0
        general.append(
            {
                "type": "fastest_pace",
                "label": "Fastest Pace",
                "value": round(fastest_pace, 2),
                "unit": "min/km",
                "date": fastest.date.isoformat() if fastest.date else None,
                "formatted": format_pace(fastest_pace),
                "distance_km": round(fastest_km, 1),
            }
        )

    best_vdot, best = _extreme_by(runs, lambda r: r.vdot, largest=True)
    if best is not None and best_vdot:
        general.append(
            {
                "type": "highest_vdot",
                "label": "Best VDOT",
                "value": best_vdot,
                "unit": "",
                "date": best.date.isoformat() if best.date else None,
                "formatted": str(best_vdot),
            }
        )

    # Best week by total km
    week_buckets: Dict[str, float] = {}
    for r in runs:
        if not r.date:
            continue
        d = r.date
        # ISO week key
        iso = d.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        # A run with no distance adds nothing to its week.
        week_buckets[key] = week_buckets.get(key, 0.0) + (r.distance_km or 0.0)
    if week_buckets:
        best_week_km = max(week_buckets.values())
        general.append(
            {
                "type": "best_week",
                "label": "Best Week",
                "value": round(best_week_km, 1),
                "unit": "km",
                "date": None,
                "formatted": f"{round(best_week_km, 1)} km",
            }
        )

    return general
