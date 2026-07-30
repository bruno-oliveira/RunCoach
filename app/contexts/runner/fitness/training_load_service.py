"""Training load, ACWR, and Fitness/Fatigue/Form service.

Computes a simplified TRIMP-style training load per run, then derives:
  - ACWR (Acute:Chronic Workload Ratio) — injury risk flag
  - CTL (Chronic Training Load / "Fitness") — 42-day EWMA of daily load
  - ATL (Acute Training Load  / "Fatigue") —  7-day EWMA of daily load
  - TSB (Training Stress Balance / "Form") — CTL(prev) - ATL(prev)

ACWR zones:
  - insufficient_data    — < ~3 weeks of history; chronic load not yet trustworthy
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

from app.core.time_utils import local_today
from app.models import RunLog

ACUTE_DAYS = 7
CHRONIC_DAYS = 28

CTL_TAU = 42  # Fitness time constant (days)
ATL_TAU = 7  # Fatigue time constant (days)

# ACWR needs ~3 weeks of history before its chronic average is meaningful;
# below this it is reported as ``insufficient_data`` rather than a false risk
# flag (audit B6).
MIN_DAYS_FOR_ACWR = 21
# CTL (42-day fitness constant) needs ~6 weeks to fully warm up; the load
# metrics are flagged low-confidence until then (audit B4).
LOAD_CONFIDENCE_DAYS = 42

# Intensity factors for the load fallback when neither RPE nor HR is logged
# (common for imported runs). Keyed on ``effective_workout_type`` so a
# threshold session and an easy jog of equal duration don't score identically
# (audit B5).
_TYPE_INTENSITY = {
    "recovery": 0.6,
    "easy": 0.8,
    "long": 0.9,
    "tempo": 1.3,
    "threshold": 1.3,
    "cruise_interval": 1.4,
    "fartlek": 1.3,
    "hill": 1.4,
    "interval": 1.6,
    "vo2max": 1.6,
    "vo2max_ladder": 1.6,
    "speed": 1.6,
    "race": 1.5,
    "race_pace": 1.4,
    "time_trial": 1.6,
}
_DEFAULT_INTENSITY = 1.0


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
            # HR-fraction proxy (threshold HR ~150 bpm), clamped so a stray
            # reading can't blow up the load.
            intensity = max(0.5, min(1.8, run.avg_heart_rate / 150))
        else:
            # No RPE/HR (e.g. an imported run): derive intensity from the run's
            # workout type instead of a flat 1.0 so a polarized week and an
            # all-hard week produce different CTL/ATL/TSB/ACWR (audit B5).
            wtype = (run.effective_workout_type or "").lower()
            intensity = _TYPE_INTENSITY.get(wtype, _DEFAULT_INTENSITY)

        return duration * intensity

    @staticmethod
    def get_training_load(
        user_id: str,
        db: Session,
        lookback_days: int = 90,
    ) -> Dict[str, Any]:
        """Return daily loads, ACWR, and fitness/fatigue/form history.

        Fetches the full run history back to the first logged run. The CTL/ATL
        EWMAs are seeded from the athlete's mean daily load rather than cold-
        started at 0, so runners with < ~6 weeks of history get a usable (not
        cold-start-biased) Form reading; ``load_confidence`` flags the first
        ~6 weeks as ``low`` and ACWR is reported as ``insufficient_data`` until
        ~3 weeks of history exist.
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

        today = local_today()
        window_start = today - timedelta(days=lookback_days)

        # Seed CTL/ATL from the athlete's mean daily load instead of cold-
        # starting at 0. With CTL_TAU=42 a zero start needs ~6 weeks to warm
        # up, which left short-history runners with an unreliable Form reading.
        # Seeding at the per-athlete baseline removes that bias; with a long
        # history the seed is overwritten by real data within a few weeks
        # (its influence decays as e^(-days/TAU)) so established runners are
        # unaffected (audit B4).
        history_span_days = (today - first_run_date).days + 1 if first_run_date else 1
        seed = sum(daily_loads.values()) / max(1, history_span_days)
        ctl = seed
        atl = seed

        # Sweep from the first run forward — there is no real load before it,
        # so the old pre-first-run "warm-up" was just zeros that decayed the
        # EWMAs back toward the cold start.
        sweep_start = first_run_date or window_start

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
            # Divide the chronic sum by the days actually elapsed (capped at
            # CHRONIC_DAYS), not a fixed 28 — otherwise a runner with < 28
            # days of history has chronic load deflated up to ~2.8x (false
            # high/very_high ACWR). Below MIN_DAYS_FOR_ACWR the ratio is not
            # trustworthy and is reported as insufficient_data (audit B6).
            days_elapsed = (
                (d - first_run_date).days + 1 if first_run_date else CHRONIC_DAYS
            )
            chronic_window = min(CHRONIC_DAYS, max(1, days_elapsed))
            chronic = chronic_total / chronic_window * ACUTE_DAYS
            acwr = round(acute / chronic, 2) if chronic > 0 else 0
            risk = (
                _classify_risk(acwr)
                if days_elapsed >= MIN_DAYS_FOR_ACWR
                else "insufficient_data"
            )
            confidence = "high" if days_elapsed >= LOAD_CONFIDENCE_DAYS else "low"

            history.append(
                {
                    "date": d.isoformat(),
                    "daily_load": round(load, 1),
                    "acute": round(acute, 1),
                    "chronic": round(chronic, 1),
                    "acwr": acwr,
                    "risk": risk,
                    # Fitness / Fatigue / Form (TrainingPeaks-style)
                    "ctl": round(ctl, 1),
                    "atl": round(atl, 1),
                    "tsb": round(tsb, 1),
                    "form": _classify_form(tsb),
                    "load_confidence": confidence,
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
