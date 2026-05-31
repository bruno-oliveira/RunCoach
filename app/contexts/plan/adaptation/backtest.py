"""Backtest / observability harness for the plan-adaptation engine.

Replays scripted *runner archetypes* against a freshly generated plan, driving
the **same** signal pipeline production uses
(:func:`plan_adjuster.gather_signals` → :func:`compute_adjustment_signals`),
and aggregates the resulting multipliers, per-signal contributions, and
clamp-firing rates.

Why this exists: ``tuning.py`` and the signal formulas are full of empirically
chosen constants, and there was previously no way to *observe* how the engine
behaves across realistic inputs. This harness makes the behavior visible and
lets tests assert directional invariants, so any future re-tuning is reviewable
instead of guesswork.

Pure consumer — it changes no production signal code. The only things it
fabricates are an in-memory plan + ``RunLog`` history and a deterministic
:class:`FitnessSignalsProvider` stub (VDOT trend / training load / mountain
score), so runs are reproducible and don't pull in the runner context.

Run it directly to print a report::

    python3 -m app.contexts.plan.adaptation.backtest
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import plan_adjuster
from app.contexts.plan.adaptation.fitness_signals import FitnessSignalsProvider
from app.contexts.plan.adaptation.tuning import PHASE_WEIGHTS
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_creation_helpers import persist_weekly_workouts
from app.core.training.hr_zone_calculator import (
    WORKOUT_ZONE_MAP,
    HRZoneCalculator,
)
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

# Nominal on-target pace per workout type (min/km), scaled by archetype pace_mult.
_BASE_PACE_MIN_KM = {
    "easy": 6.2,
    "recovery": 6.6,
    "long": 6.4,
    "tempo": 5.2,
    "interval": 4.8,
    "hill": 5.5,
    "fartlek": 5.4,
    "vo2max": 4.8,
    "race_pace": 5.0,
}

_SIGNAL_NAMES = ("volume", "effort", "completion", "hr_zone", "feedback", "readiness")


@dataclass(frozen=True)
class RunnerArchetype:
    """How a simulated runner executes their prescribed plan.

    Each field shapes the ``RunLog`` history the harness fabricates, which in
    turn drives the adaptation signals. ``volume_mult`` and ``pace_mult`` are
    relative to the *planned* workout; ``effort`` is the perceived-effort the
    runner reports; ``completion_prob`` is the fraction of prescribed workouts
    actually logged; ``hr_zone_offset`` shifts logged HR above (+) the target
    zone (only meaningful when ``with_hr_zones`` is set).
    """

    name: str
    description: str
    volume_mult: float = 1.0
    pace_mult: float = 1.0
    effort: int = 5
    completion_prob: float = 1.0
    hr_zone_offset: int = 0
    with_hr_zones: bool = False
    vdot_trend: str = "stable"
    training_load: Optional[Dict[str, Any]] = None


# The canonical archetypes. Tuned so each exercises a distinct corner of the
# engine and yields a clear directional expectation (asserted in tests).
ARCHETYPES: List[RunnerArchetype] = [
    RunnerArchetype(
        name="strong_adherent",
        description="Hits every run a touch over plan, low perceived effort.",
        volume_mult=1.05,
        effort=4,
        completion_prob=1.0,
    ),
    RunnerArchetype(
        name="overreacher",
        description="Runs well over plan at very high effort — classic overreach.",
        volume_mult=1.30,
        effort=9,
        completion_prob=1.0,
    ),
    RunnerArchetype(
        name="under_performer",
        description="Logs short, slow, and skips ~1 in 3 at high effort.",
        volume_mult=0.65,
        pace_mult=1.12,
        effort=8,
        completion_prob=0.7,
    ),
    RunnerArchetype(
        name="sporadic_logger",
        description="Only logs ~1 in 3 runs — tests the data-sufficiency guards.",
        volume_mult=1.0,
        effort=5,
        completion_prob=0.34,
    ),
    RunnerArchetype(
        name="hr_drifter",
        description="On-plan distance but HR runs ~2 zones hot the whole block.",
        volume_mult=1.0,
        effort=7,
        completion_prob=1.0,
        hr_zone_offset=2,
        with_hr_zones=True,
    ),
]


@dataclass
class WeekObservation:
    """The adaptation verdict for one simulated evaluation week."""

    week: int
    phase: str
    skipped: bool = False
    multiplier: Optional[float] = None
    raw_multiplier: Optional[float] = None
    overreach: bool = False
    volume_ratio: Optional[float] = None
    effort_factor: Optional[float] = None
    completion_rate: Optional[float] = None
    hr_zone_factor: Optional[float] = None
    avg_zone_deviation: Optional[float] = None
    tsb_form: Optional[str] = None
    realized_weights: Dict[str, float] = field(default_factory=dict)
    nominal_weights: Dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Scenario construction
# --------------------------------------------------------------------------- #


def _should_log(index: int, prob: float) -> bool:
    """Deterministic, evenly-spread sampling (Bresenham-style).

    ``prob=0.34`` keeps roughly every third item with no RNG, so a backtest is
    fully reproducible.
    """
    if prob >= 1.0:
        return True
    if prob <= 0.0:
        return False
    return int((index + 1) * prob) != int(index * prob)


def _make_plan(
    db: Session,
    *,
    current_km: float,
    target_distance: float,
    weeks: int,
    vdot: float,
    with_hr_zones: bool,
) -> Tuple[User, TrainingPlan]:
    """Generate + persist a plan (and optional HR zones) for replay."""
    user = User(email="backtest@example.com", name="Backtest Runner", age=35)
    db.add(user)
    db.flush()

    plan_data = TrainingPlanGenerator().generate_plan(
        current_km, target_distance, weeks, vdot=vdot
    )

    plan = TrainingPlan(
        user_id=user.id,
        current_weekly_km=current_km,
        target_distance=str(target_distance),
        weeks_duration=weeks,
        max_runs_per_week=4,
        plan_data=plan_data,
        vdot=vdot,
    )
    if with_hr_zones:
        max_hr = 190
        plan.max_heart_rate = max_hr
        plan.hr_zones_data = {
            "max_hr": max_hr,
            "zones": HRZoneCalculator.calculate_zones(max_hr),
        }
    db.add(plan)
    db.flush()

    persist_weekly_workouts(plan, plan_data, db)
    db.flush()
    return user, plan


def _hr_for(workout_type: str, offset: int, zones: List[dict]) -> Optional[int]:
    """Mid-band BPM for (target zone + offset), clamped to 1..5."""
    target = WORKOUT_ZONE_MAP.get(workout_type, 2)
    zone_num = max(1, min(5, target + offset))
    zone = next((z for z in zones if z["zone"] == zone_num), None)
    if not zone:
        return None
    return round((zone["min_bpm"] + zone["max_bpm"]) / 2)


def _clear_runs(db: Session, plan: TrainingPlan) -> None:
    db.query(RunLog).filter(RunLog.training_plan_id == plan.id).delete()
    db.flush()


def _seed_runs(
    db: Session,
    user: User,
    plan: TrainingPlan,
    archetype: RunnerArchetype,
    *,
    through_week: int,
    start_date: datetime,
) -> None:
    """Fabricate linked RunLogs for every completed week (< ``through_week``)."""
    # Match gather_signals' definition of "scheduled" past workouts (every
    # non-rest workout), so a 100%-completion archetype yields completion ≈ 1.0
    # rather than being penalised for workout types this harness skipped.
    rows = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number < through_week,
            DailyWorkout.workout_type != "rest",
            DailyWorkout.distance_km > 0,
        )
        .order_by(WeeklyPlan.week_number, DailyWorkout.day_of_week)
        .all()
    )

    zones = (plan.hr_zones_data or {}).get("zones") if plan.hr_zones_data else None

    for idx, (workout, week_number) in enumerate(rows):
        if not _should_log(idx, archetype.completion_prob):
            continue
        run_date = start_date + timedelta(
            weeks=(week_number - 1), days=(workout.day_of_week - 1)
        )
        base_pace = _BASE_PACE_MIN_KM.get(workout.workout_type or "easy", 6.0)
        pace = round(base_pace * archetype.pace_mult, 2)
        distance = round((workout.distance_km or 0) * archetype.volume_mult, 2)
        avg_hr = (
            _hr_for(workout.workout_type or "easy", archetype.hr_zone_offset, zones)
            if zones
            else None
        )
        db.add(
            RunLog(
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=workout.id,
                date=datetime.combine(run_date.date(), datetime.min.time()),
                distance_km=distance,
                duration_minutes=round(distance * pace, 1),
                avg_pace_min_km=pace,
                avg_heart_rate=avg_hr,
                workout_type=workout.workout_type,
                perceived_effort=archetype.effort,
            )
        )
    db.flush()


def _stub_provider(archetype: RunnerArchetype) -> FitnessSignalsProvider:
    """Deterministic fitness-signal provider — no runner-context dependency."""
    return FitnessSignalsProvider(
        get_vdot_history=lambda *a, **k: [],
        calculate_vdot_trend=lambda *a, **k: archetype.vdot_trend,
        get_training_load=lambda *a, **k: archetype.training_load,
        score_mountain_simulation=lambda *a, **k: None,
    )


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def _default_eval_weeks(weeks: int) -> List[int]:
    """Representative weeks spanning base→peak (skip wk1-3 history warmup & taper)."""
    return [w for w in range(4, max(5, weeks - 1)) if (w - 4) % 2 == 0]


def replay(
    db: Session,
    archetype: RunnerArchetype,
    *,
    current_km: float = 30.0,
    target_distance: float = 21.1,
    weeks: int = 14,
    vdot: float = 45.0,
    eval_weeks: Optional[List[int]] = None,
) -> List[WeekObservation]:
    """Run ``archetype`` against a fresh plan and record the weekly verdicts.

    For each evaluation week ``k`` the plan's ``start_date`` is set so the
    wall-clock "today" lands on week ``k`` (``compute_current_week`` → ``k``),
    history is seeded for weeks ``1..k-1``, and the production
    ``gather_signals`` path is invoked with ``run_map=False`` (runs are already
    linked) and a deterministic fitness provider.
    """
    user, plan = _make_plan(
        db,
        current_km=current_km,
        target_distance=target_distance,
        weeks=weeks,
        vdot=vdot,
        with_hr_zones=archetype.with_hr_zones,
    )
    provider = _stub_provider(archetype)
    today = plan_adjuster.today_date()
    weeks_to_eval = eval_weeks if eval_weeks is not None else _default_eval_weeks(weeks)

    observations: List[WeekObservation] = []
    for k in weeks_to_eval:
        start_date = datetime.combine(
            today - timedelta(weeks=(k - 1)), datetime.min.time()
        )
        plan.start_date = start_date
        # A fresh evaluation each week: clear and re-seed history relative to the
        # shifted start_date, and clear adaptation history so the standard
        # (non-expanded) multiplier range is what we observe.
        plan.adaptation_history = None
        _clear_runs(db, plan)
        _seed_runs(db, user, plan, archetype, through_week=k, start_date=start_date)
        db.flush()

        phase = plan_adjuster._get_current_phase(plan, k)
        gathered = plan_adjuster.gather_signals(
            plan.id, user.id, db, run_map=False, fitness_provider=provider
        )
        if gathered is None:
            observations.append(WeekObservation(week=k, phase=phase, skipped=True))
            continue

        s = gathered["signals"]
        observations.append(
            WeekObservation(
                week=k,
                phase=s.get("current_phase", phase),
                multiplier=s["multiplier"],
                raw_multiplier=s["raw_multiplier"],
                overreach=s.get("overreach_detected", False),
                volume_ratio=s.get("volume_ratio"),
                effort_factor=s.get("effort_factor"),
                completion_rate=s.get("completion_rate"),
                hr_zone_factor=s.get("hr_zone_factor"),
                avg_zone_deviation=s.get("avg_zone_deviation"),
                tsb_form=s.get("tsb_form"),
                realized_weights=dict(s.get("phase_weights", {})),
                nominal_weights=dict(
                    zip(_SIGNAL_NAMES, PHASE_WEIGHTS.get(phase, PHASE_WEIGHTS["build"]))
                ),
            )
        )
    return observations


# --------------------------------------------------------------------------- #
# Aggregation + reporting
# --------------------------------------------------------------------------- #


@dataclass
class ArchetypeReport:
    archetype: RunnerArchetype
    observations: List[WeekObservation]

    @property
    def evaluated(self) -> List[WeekObservation]:
        return [o for o in self.observations if not o.skipped]

    @property
    def multipliers(self) -> List[float]:
        return [o.multiplier for o in self.evaluated if o.multiplier is not None]

    @property
    def skipped_count(self) -> int:
        return sum(1 for o in self.observations if o.skipped)

    @property
    def overreach_rate(self) -> float:
        ev = self.evaluated
        return (sum(1 for o in ev if o.overreach) / len(ev)) if ev else 0.0

    def direction_counts(self) -> Dict[str, int]:
        counts = {"increase": 0, "hold": 0, "reduce": 0}
        for m in self.multipliers:
            counts["increase" if m > 1.0 else "reduce" if m < 1.0 else "hold"] += 1
        return counts

    def weight_realization(self) -> Dict[str, Tuple[float, float]]:
        """Per-signal (avg realized weight, avg nominal weight) across weeks."""
        ev = self.evaluated
        out: Dict[str, Tuple[float, float]] = {}
        if not ev:
            return out
        for name in _SIGNAL_NAMES:
            realized = [o.realized_weights.get(name, 0.0) for o in ev]
            nominal = [o.nominal_weights.get(name, 0.0) for o in ev]
            out[name] = (
                round(sum(realized) / len(realized), 3),
                round(sum(nominal) / len(nominal), 3),
            )
        return out


def run_all(db_factory, **plan_kwargs) -> List[ArchetypeReport]:
    """Replay every archetype, each on its own fresh session from ``db_factory``."""
    reports: List[ArchetypeReport] = []
    for arch in ARCHETYPES:
        session = db_factory()
        try:
            obs = replay(session, arch, **plan_kwargs)
        finally:
            session.close()
        reports.append(ArchetypeReport(arch, obs))
    return reports


def format_report(reports: List[ArchetypeReport]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("ADAPTATION BACKTEST — multiplier behavior by runner archetype")
    lines.append("=" * 78)
    for rep in reports:
        mult = rep.multipliers
        dist = (
            f"min={min(mult):.2f} med={median(mult):.2f} max={max(mult):.2f}"
            if mult
            else "n/a"
        )
        lines.append("")
        lines.append(f"▶ {rep.archetype.name} — {rep.archetype.description}")
        lines.append(
            f"  multipliers: {dist}   directions={rep.direction_counts()}   "
            f"overreach_rate={rep.overreach_rate:.0%}   skipped={rep.skipped_count}"
        )
        lines.append("  week  phase    mult   raw    vol   eff   compl  hrZ   tsb")
        for o in rep.observations:
            if o.skipped:
                lines.append(
                    f"   {o.week:>2}   {o.phase:<7}  —— skipped (insufficient data) ——"
                )
                continue
            lines.append(
                f"   {o.week:>2}   {o.phase:<7} "
                f"{o.multiplier:>5.2f} {o.raw_multiplier:>5.2f} "
                f"{(o.volume_ratio or 0):>5.2f} {(o.effort_factor or 0):>5.2f} "
                f"{(o.completion_rate or 0):>5.2f} {(o.hr_zone_factor or 0):>5.2f}  "
                f"{o.tsb_form or '-'}" + ("  ⚠overreach" if o.overreach else "")
            )
        wr = rep.weight_realization()
        folded = [
            name for name, (real, nom) in wr.items() if nom > 0.02 and real < 0.01
        ]
        if folded:
            lines.append(
                "  ⓘ signals contributing 0 weight (folded/no data): "
                + ", ".join(folded)
            )
    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def _in_memory_session_factory():
    """Build a throwaway in-memory SQLite session factory for the CLI."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):  # pragma: no cover - sqlite setup
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def main() -> None:  # pragma: no cover - CLI entry
    factory = _in_memory_session_factory()
    reports = run_all(factory)
    print(format_report(reports))


if __name__ == "__main__":  # pragma: no cover
    main()
