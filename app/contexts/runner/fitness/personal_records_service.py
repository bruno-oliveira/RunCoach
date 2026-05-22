"""Personal records detection and tracking service.

Finds best performances across standard race distances, tracks PR
progression over time, and computes improvement deltas.
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog

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


def _format_pace(pace_min_km: float) -> str:
    mins = int(pace_min_km)
    secs = int((pace_min_km - mins) * 60)
    return f"{mins}:{secs:02d}"


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


def _build_distance_records(runs: List[RunLog]) -> List[Dict[str, Any]]:
    """Find best time for each standard distance bucket."""
    records = []

    for bucket in DISTANCE_BUCKETS:
        matching = [
            r
            for r in runs
            if abs(r.distance_km - bucket["target_km"]) <= bucket["tolerance"]
            and r.distance_km >= bucket["min_km"]
        ]
        if not matching:
            continue

        # Walk chronologically, tracking PR progression
        best_pace = float("inf")
        pr_history: List[Dict] = []

        for run in matching:
            pace = run.duration_minutes / run.distance_km
            if pace < best_pace:
                prev_pace = best_pace if best_pace < float("inf") else None
                best_pace = pace
                total_secs = int(run.duration_minutes * 60)
                entry: Dict[str, Any] = {
                    "date": run.date.isoformat() if run.date else None,
                    "distance_km": round(run.distance_km, 2),
                    "duration_seconds": total_secs,
                    "duration_formatted": VDOTCalculator.format_duration(total_secs),
                    "pace_min_km": round(pace, 2),
                    "pace_formatted": _format_pace(pace),
                    "vdot": run.vdot,
                }
                if prev_pace is not None:
                    improvement_secs = (prev_pace - pace) * run.distance_km * 60
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

    longest = max(runs, key=lambda r: r.distance_km)
    general.append(
        {
            "type": "longest_run",
            "label": "Longest Run",
            "value": round(longest.distance_km, 1),
            "unit": "km",
            "date": longest.date.isoformat() if longest.date else None,
            "formatted": f"{round(longest.distance_km, 1)} km",
        }
    )

    pace_runs = [
        r
        for r in runs
        if r.avg_pace_min_km and r.avg_pace_min_km > 0 and r.distance_km >= 3.0
    ]
    if pace_runs:
        fastest = min(pace_runs, key=lambda r: r.avg_pace_min_km)
        general.append(
            {
                "type": "fastest_pace",
                "label": "Fastest Pace",
                "value": round(fastest.avg_pace_min_km, 2),
                "unit": "min/km",
                "date": fastest.date.isoformat() if fastest.date else None,
                "formatted": f"{_format_pace(fastest.avg_pace_min_km)}/km",
                "distance_km": round(fastest.distance_km, 1),
            }
        )

    vdot_runs = [r for r in runs if r.vdot]
    if vdot_runs:
        best = max(vdot_runs, key=lambda r: r.vdot)
        general.append(
            {
                "type": "highest_vdot",
                "label": "Best VDOT",
                "value": best.vdot,
                "unit": "",
                "date": best.date.isoformat() if best.date else None,
                "formatted": str(best.vdot),
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
        week_buckets[key] = week_buckets.get(key, 0) + r.distance_km
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
