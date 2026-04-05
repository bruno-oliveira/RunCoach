"""RunnerProfile — synthesized snapshot of a runner's current fitness and habits.

Built from existing services (TrainingLoadService, RacePredictorService, etc.)
and used to drive personalized insights and data-aware plan generation.
"""

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog
from app.services.race_predictor_service import RacePredictorService
from app.services.training_load_service import TrainingLoadService


@dataclass
class RunnerProfile:
    """Snapshot of a runner's current fitness, load, and training habits."""

    # Fitness
    current_vdot: Optional[float] = None
    vdot_trend: str = "stable"  # improving / stable / declining

    # Volume (from actual run logs, not self-reported)
    avg_weekly_km: float = 0.0
    peak_weekly_km: float = 0.0
    longest_run_km: float = 0.0
    runs_per_week: float = 0.0

    # Training load & injury risk
    acwr: Optional[float] = None
    acwr_risk: str = "low"  # low / optimal / high / very_high

    # Efficiency
    avg_efficiency: Optional[float] = None  # speed/HR * 100
    efficiency_trend_pct: Optional[float] = None  # % change recent vs prior

    # Pace zone distribution (fraction of runs, not distance)
    easy_pct: float = 0.0
    moderate_pct: float = 0.0
    hard_pct: float = 0.0

    # Gaps / areas to improve
    workout_type_counts: Optional[Dict[str, int]] = None
    total_runs: int = 0

    # Data sufficiency
    has_sufficient_data: bool = False
    weeks_of_data: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

WEEKS_WINDOW = 12


def build_profile(user_id: str, db: Session) -> RunnerProfile:
    """Assemble a RunnerProfile from the user's run data and existing services."""
    profile = RunnerProfile()

    cutoff = datetime.now(timezone.utc) - timedelta(weeks=WEEKS_WINDOW)
    cutoff_naive = cutoff.replace(tzinfo=None)

    runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == user_id, RunLog.date >= cutoff_naive)
        .order_by(RunLog.date.asc())
        .all()
    )

    if len(runs) < 3:
        return profile

    profile.total_runs = len(runs)
    profile.has_sufficient_data = True

    # Weeks of data
    dates = [r.date for r in runs if r.date]
    if dates:
        span_days = (dates[-1] - dates[0]).days
        profile.weeks_of_data = max(span_days // 7, 1)

    # -- VDOT & trend --
    profile.current_vdot = RacePredictorService.get_best_recent_vdot(
        user_id, weeks=WEEKS_WINDOW, db=db
    )
    history = RacePredictorService.get_vdot_history(user_id, weeks=WEEKS_WINDOW, db=db)
    profile.vdot_trend = RacePredictorService.calculate_vdot_trend(history)

    # -- Volume stats --
    _compute_volume(profile, runs)

    # -- Training load --
    _compute_load(profile, user_id, db)

    # -- Efficiency --
    _compute_efficiency(profile, runs)

    # -- Pace zone distribution --
    _compute_pace_zones(profile, runs)

    # -- Workout type counts --
    _compute_workout_types(profile, runs)

    return profile


def _compute_volume(profile: RunnerProfile, runs: list) -> None:
    """Compute weekly averages, peak week, longest run, runs/week."""
    week_buckets: Dict[str, float] = {}
    week_run_counts: Dict[str, int] = {}

    for r in runs:
        if not r.date or not r.distance_km:
            continue
        iso = r.date.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        week_buckets[key] = week_buckets.get(key, 0) + r.distance_km
        week_run_counts[key] = week_run_counts.get(key, 0) + 1

    if week_buckets:
        totals = list(week_buckets.values())
        profile.avg_weekly_km = round(sum(totals) / len(totals), 1)
        profile.peak_weekly_km = round(max(totals), 1)
        run_counts = list(week_run_counts.values())
        profile.runs_per_week = round(sum(run_counts) / len(run_counts), 1)

    distances = [r.distance_km for r in runs if r.distance_km]
    if distances:
        profile.longest_run_km = round(max(distances), 1)


def _compute_load(profile: RunnerProfile, user_id: str, db: Session) -> None:
    """Pull current ACWR from TrainingLoadService."""
    load_data = TrainingLoadService.get_training_load(user_id, db, lookback_days=28)
    if load_data.get("available") and load_data.get("current"):
        current = load_data["current"]
        profile.acwr = current.get("acwr")
        profile.acwr_risk = current.get("risk", "low")


def _compute_efficiency(profile: RunnerProfile, runs: list) -> None:
    """Aerobic efficiency = (speed km/h) / HR * 100. Compare halves for trend."""
    eff_runs = [
        r for r in runs
        if r.avg_heart_rate and r.avg_heart_rate > 0
        and r.avg_pace_min_km and r.avg_pace_min_km > 0
    ]
    if len(eff_runs) < 4:
        return

    def _eff(r: RunLog) -> float:
        speed_kmh = 60 / r.avg_pace_min_km
        return speed_kmh / r.avg_heart_rate * 100

    efficiencies = [_eff(r) for r in eff_runs]
    profile.avg_efficiency = round(sum(efficiencies) / len(efficiencies), 2)

    mid = len(efficiencies) // 2
    first_half = sum(efficiencies[:mid]) / mid
    second_half = sum(efficiencies[mid:]) / (len(efficiencies) - mid)
    if first_half > 0:
        profile.efficiency_trend_pct = round(
            (second_half - first_half) / first_half * 100, 1
        )


def _compute_pace_zones(profile: RunnerProfile, runs: list) -> None:
    """Classify runs into easy / moderate / hard by pace relative to VDOT zones."""
    if not profile.current_vdot:
        return

    zones = VDOTCalculator.get_pace_zones(profile.current_vdot)
    if not zones:
        return

    easy_threshold = zones.get("E", {}).get("pace_min_km")
    threshold_pace = zones.get("T", {}).get("pace_min_km")

    if not easy_threshold or not threshold_pace:
        return

    easy = moderate = hard = 0
    for r in runs:
        if not r.avg_pace_min_km or r.avg_pace_min_km <= 0:
            continue
        pace = r.avg_pace_min_km
        if pace >= easy_threshold:
            easy += 1
        elif pace >= threshold_pace:
            moderate += 1
        else:
            hard += 1

    total = easy + moderate + hard
    if total > 0:
        profile.easy_pct = round(easy / total * 100, 1)
        profile.moderate_pct = round(moderate / total * 100, 1)
        profile.hard_pct = round(hard / total * 100, 1)


def _compute_workout_types(profile: RunnerProfile, runs: list) -> None:
    """Count runs by workout_type."""
    counts: Dict[str, int] = {}
    for r in runs:
        wt = r.workout_type or "unknown"
        counts[wt] = counts.get(wt, 0) + 1
    profile.workout_type_counts = counts
