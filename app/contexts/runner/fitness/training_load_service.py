"""Training load, ACWR, and Fitness/Fatigue/Form service.

Computes a simplified TRIMP-style training load per run, then derives:
  - ACWR (Acute:Chronic Workload Ratio) — injury risk flag
  - CTL (Chronic Training Load / "Fitness") — 42-day EWMA of daily load
  - ATL (Acute Training Load  / "Fatigue") —  7-day EWMA of daily load
  - TSB (Training Stress Balance / "Form") — CTL(prev) - ATL(prev)

ACWR zones:
  - low       (< 0.8)  — under-training / detraining risk
  - optimal   (0.8-1.3) — sweet spot for adaptation
  - high      (1.3-1.5) — elevated injury risk
  - very_high (> 1.5)   — danger zone

Form zones (TSB):
  - fresh       (TSB >=  5)   — rested, primed for a hard session or race
  - neutral     (-10 < TSB < 5) — normal training state
  - fatigued    (-30 <= TSB <= -10) — productive training fatigue
  - deep        (TSB < -30)   — overreaching, risk of burnout
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import RunLog

ACUTE_DAYS = 7
CHRONIC_DAYS = 28

CTL_TAU = 42  # Fitness time constant (days)
ATL_TAU = 7  # Fatigue time constant (days)


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
        """Return daily loads, ACWR, and fitness/fatigue/form history.

        Fetches the full run history back to the first logged run so the
        EWMA for CTL/ATL can warm up properly (42+ days of lead-in).
        """
        runs = (
            db.query(RunLog)
            .filter(RunLog.user_id == user_id)
            .order_by(RunLog.date.asc())
            .all()
        )

        if not runs:
            return {"available": False, "reason": "No runs logged yet."}

        # Build daily load map
        daily_loads: Dict[str, float] = {}
        first_run_date: Optional[date] = None
        for run in runs:
            if not run.date:
                continue
            run_date = run.date.date() if isinstance(run.date, datetime) else run.date
            if first_run_date is None or run_date < first_run_date:
                first_run_date = run_date
            key = run_date.isoformat()
            daily_loads[key] = daily_loads.get(key, 0) + TrainingLoadService._run_load(
                run
            )

        today = date.today()
        window_start = today - timedelta(days=lookback_days)
        # Start EWMA sweep 60 days before the first run (or window_start, whichever is earlier)
        # so CTL/ATL are properly warmed up by the time they enter the returned window.
        sweep_start = min(first_run_date or window_start, window_start) - timedelta(
            days=14
        )

        ctl = 0.0
        atl = 0.0
        history: List[Dict[str, Any]] = []
        total_days = (today - sweep_start).days + 1

        for i in range(total_days):
            d = sweep_start + timedelta(days=i)
            load = daily_loads.get(d.isoformat(), 0)

            # Form uses YESTERDAY's CTL/ATL per convention so it reflects
            # how rested you *are* going into today, not after today's work.
            tsb = ctl - atl

            # Advance the EWMAs with today's load
            ctl = ctl + (load - ctl) / CTL_TAU
            atl = atl + (load - atl) / ATL_TAU

            if d < window_start:
                continue

            # Rolling-sum acute & chronic (kept for ACWR backward compat)
            acute = sum(
                daily_loads.get((d - timedelta(days=j)).isoformat(), 0)
                for j in range(ACUTE_DAYS)
            )
            chronic_total = sum(
                daily_loads.get((d - timedelta(days=j)).isoformat(), 0)
                for j in range(CHRONIC_DAYS)
            )
            chronic = chronic_total / CHRONIC_DAYS * ACUTE_DAYS
            acwr = round(acute / chronic, 2) if chronic > 0 else 0

            history.append(
                {
                    "date": d.isoformat(),
                    "daily_load": round(load, 1),
                    "acute": round(acute, 1),
                    "chronic": round(chronic, 1),
                    "acwr": acwr,
                    "risk": _classify_risk(acwr),
                    # Fitness / Fatigue / Form (TrainingPeaks-style)
                    "ctl": round(ctl, 1),
                    "atl": round(atl, 1),
                    "tsb": round(tsb, 1),
                    "form": _classify_form(tsb),
                }
            )

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


def _classify_form(tsb: float) -> str:
    """Map TSB (form) to a human label for UI badges."""
    if tsb >= 5:
        return "fresh"
    if tsb > -10:
        return "neutral"
    if tsb >= -30:
        return "fatigued"
    return "deep"
