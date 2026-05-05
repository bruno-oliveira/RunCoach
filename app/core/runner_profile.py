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
from app.services.fitness.race_predictor_service import RacePredictorService
from app.services.fitness.training_load_service import TrainingLoadService

# A run averaging this many meters of climb per km is treated as a trail run.
TRAIL_ELEVATION_M_PER_KM = 20.0


def _is_trail_run(run: RunLog) -> bool:
    """Heuristic: classify a run as 'trail' from elevation gain density."""
    if not run.distance_km or run.distance_km <= 0:
        return False
    if not run.elevation_gain_m:
        return False
    return run.elevation_gain_m / run.distance_km >= TRAIL_ELEVATION_M_PER_KM


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

    # Terrain breakdown (a trail run is one with >=20 m of climb per km)
    trail_weekly_km: float = 0.0
    road_weekly_km: float = 0.0
    trail_runs_count: int = 0
    trail_total_km: float = 0.0

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

    # Run characteristics
    avg_run_km: float = 0.0
    avg_pace_min_km: Optional[float] = None
    rest_days_per_week: float = 0.0
    volume_trend: str = "stable"  # increasing / stable / decreasing

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
    trail_week_buckets: Dict[str, float] = {}
    road_week_buckets: Dict[str, float] = {}
    trail_runs_count = 0
    trail_total_km = 0.0

    for r in runs:
        if not r.date or not r.distance_km:
            continue
        iso = r.date.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        week_buckets[key] = week_buckets.get(key, 0) + r.distance_km
        week_run_counts[key] = week_run_counts.get(key, 0) + 1

        if _is_trail_run(r):
            trail_week_buckets[key] = trail_week_buckets.get(key, 0) + r.distance_km
            trail_runs_count += 1
            trail_total_km += r.distance_km
        else:
            road_week_buckets[key] = road_week_buckets.get(key, 0) + r.distance_km

    if week_buckets:
        totals = list(week_buckets.values())
        profile.avg_weekly_km = round(sum(totals) / len(totals), 1)
        profile.peak_weekly_km = round(max(totals), 1)
        run_counts = list(week_run_counts.values())
        profile.runs_per_week = round(sum(run_counts) / len(run_counts), 1)
        profile.rest_days_per_week = round(7 - sum(run_counts) / len(run_counts), 1)

        weeks_observed = len(week_buckets)
        profile.trail_weekly_km = round(
            sum(trail_week_buckets.values()) / weeks_observed, 1
        )
        profile.road_weekly_km = round(
            sum(road_week_buckets.values()) / weeks_observed, 1
        )

        # Volume trend: compare first half vs second half of weeks
        if len(totals) >= 4:
            mid = len(totals) // 2
            first_avg = sum(totals[:mid]) / mid
            second_avg = sum(totals[mid:]) / (len(totals) - mid)
            if first_avg > 0:
                change_pct = (second_avg - first_avg) / first_avg * 100
                if change_pct > 10:
                    profile.volume_trend = "increasing"
                elif change_pct < -10:
                    profile.volume_trend = "decreasing"

    profile.trail_runs_count = trail_runs_count
    profile.trail_total_km = round(trail_total_km, 1)

    distances = [r.distance_km for r in runs if r.distance_km]
    if distances:
        profile.longest_run_km = round(max(distances), 1)
        profile.avg_run_km = round(sum(distances) / len(distances), 1)

    paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km and r.avg_pace_min_km > 0]
    if paces:
        profile.avg_pace_min_km = round(sum(paces) / len(paces), 2)


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
