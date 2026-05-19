"""Assembles a RunnerProfile from persisted run logs and fitness services.

Lives in the service layer because it depends on the database session and the
fitness services; the pure ``RunnerProfile`` dataclass stays in
``app.contexts.runner.profile.runner_profile``.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from app.contexts.runner.profile.runner_profile import RunnerProfile
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.fitness.training_load_service import TrainingLoadService

# A run averaging this many meters of climb per km is treated as a trail run.
TRAIL_ELEVATION_M_PER_KM = 20.0

WEEKS_WINDOW = 12


def _is_trail_run(run: RunLog) -> bool:
    """Classify a run as 'trail' from elevation gain density."""
    if not run.distance_km or run.distance_km <= 0:
        return False
    if not run.elevation_gain_m:
        return False
    return run.elevation_gain_m / run.distance_km >= TRAIL_ELEVATION_M_PER_KM


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

    dates = [r.date for r in runs if r.date]
    if dates:
        span_days = (dates[-1] - dates[0]).days
        profile.weeks_of_data = max(span_days // 7, 1)

    profile.current_vdot = RacePredictorService.get_best_recent_vdot(
        user_id, weeks=WEEKS_WINDOW, db=db
    )
    history = RacePredictorService.get_vdot_history(user_id, weeks=WEEKS_WINDOW, db=db)
    profile.vdot_trend = RacePredictorService.calculate_vdot_trend(history)

    _compute_volume(profile, runs)
    _compute_load(profile, user_id, db)
    _compute_efficiency(profile, runs)
    _compute_pace_zones(profile, runs)
    _compute_workout_types(profile, runs)

    return profile


def _compute_volume(profile: RunnerProfile, runs: List[RunLog]) -> None:
    """Weekly averages, peak week, longest run, runs/week, terrain split."""
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


def _compute_efficiency(profile: RunnerProfile, runs: List[RunLog]) -> None:
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


def _compute_pace_zones(profile: RunnerProfile, runs: List[RunLog]) -> None:
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


def _compute_workout_types(profile: RunnerProfile, runs: List[RunLog]) -> None:
    """Count runs by workout_type."""
    counts: Dict[str, int] = {}
    for r in runs:
        wt = r.workout_type or "unknown"
        counts[wt] = counts.get(wt, 0) + 1
    profile.workout_type_counts = counts
