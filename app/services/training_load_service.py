"""Training load and ACWR (Acute:Chronic Workload Ratio) service.

Computes a simplified TRIMP-style training load per run, then derives
the Acute:Chronic Workload Ratio to flag injury risk.

ACWR zones:
  - low       (< 0.8)  — under-training / detraining risk
  - optimal   (0.8–1.3) — sweet spot for adaptation
  - high      (1.3–1.5) — elevated injury risk
  - very_high (> 1.5)   — danger zone
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import RunLog

ACUTE_DAYS = 7
CHRONIC_DAYS = 28


class TrainingLoadService:
    """Computes training load metrics and injury risk via ACWR."""

    @staticmethod
    def _run_load(run: RunLog) -> float:
        """Training load for a single run: duration * intensity factor."""
        duration = run.duration_minutes or 0
        if duration <= 0:
            return 0.0

        if run.perceived_effort and run.perceived_effort > 0:
            intensity = 0.5 + (run.perceived_effort / 10) * 1.5
        elif run.avg_heart_rate and run.avg_heart_rate > 0:
            intensity = run.avg_heart_rate / 150
        else:
            intensity = 1.0

        return duration * intensity

    @staticmethod
    def get_training_load(
        user_id: str,
        db: Session,
        lookback_days: int = 90,
    ) -> Dict[str, Any]:
        """Return daily loads, ACWR history, and current risk status.

        Fetches runs for lookback + CHRONIC_DAYS so the chronic baseline
        is valid from day one of the returned window.
        """
        buffer = lookback_days + CHRONIC_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=buffer)
        cutoff_naive = cutoff.replace(tzinfo=None)

        runs = (
            db.query(RunLog)
            .filter(RunLog.user_id == user_id, RunLog.date >= cutoff_naive)
            .order_by(RunLog.date.asc())
            .all()
        )

        if not runs:
            return {"available": False, "reason": "No runs logged yet."}

        # Build daily load map
        daily_loads: Dict[str, float] = {}
        for run in runs:
            if not run.date:
                continue
            key = run.date.strftime("%Y-%m-%d")
            daily_loads[key] = daily_loads.get(key, 0) + TrainingLoadService._run_load(run)

        today = date.today()
        start = today - timedelta(days=lookback_days)

        history: List[Dict[str, Any]] = []
        for i in range(lookback_days + 1):
            d = start + timedelta(days=i)

            acute = sum(
                daily_loads.get((d - timedelta(days=j)).isoformat(), 0)
                for j in range(ACUTE_DAYS)
            )

            chronic_total = sum(
                daily_loads.get((d - timedelta(days=j)).isoformat(), 0)
                for j in range(CHRONIC_DAYS)
            )
            # Express chronic as a 7-day equivalent for direct comparison
            chronic = chronic_total / CHRONIC_DAYS * ACUTE_DAYS

            acwr = round(acute / chronic, 2) if chronic > 0 else 0
            risk = _classify_risk(acwr)

            history.append({
                "date": d.isoformat(),
                "daily_load": round(daily_loads.get(d.isoformat(), 0), 1),
                "acute": round(acute, 1),
                "chronic": round(chronic, 1),
                "acwr": acwr,
                "risk": risk,
            })

        current = history[-1] if history else None

        return {
            "available": True,
            "current": current,
            "history": history,
        }


def _classify_risk(acwr: float) -> str:
    if acwr < 0.8:
        return "low"
    if acwr <= 1.3:
        return "optimal"
    if acwr <= 1.5:
        return "high"
    return "very_high"
