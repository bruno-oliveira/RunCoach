"""RunnerProfile — pure dataclass snapshot of a runner's fitness and habits.

This module is part of the pure core layer and must not import infrastructure
(SQLAlchemy sessions, ORM models, services). Profile construction lives in
``app.contexts.runner.profile.profile_builder``.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


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
