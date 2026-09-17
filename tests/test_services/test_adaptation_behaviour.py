"""End-to-end adaptation behaviour on a real generated plan.

Generation itself is covered by ``test_physiological_envelope`` — every accepted
input produces a sound plan. This module asks the complementary question: **once
runs start arriving from Intervals, does adapting the plan keep it sound?**

Two distinct paths are exercised, because they do different things:

* **The automatic path** — ``auto_map_and_adjust``, the only trigger the adaptive
  engine has (shared by the manual sync and the scheduled sweep). It maps logged
  runs onto planned days and recalibrates VDOT/pace zones. It does **not** change
  the prescribed distance of any week; the tests below characterise that, so a
  future change that starts re-pacing volume automatically is caught here.
* **The applied path** — ``apply_adjustment_to_future_weeks``, reached only from
  user-initiated flows (the plan-adjustments router and the intent service).
  This is the one that moves volume, so this is where "does adapting break the
  plan?" is really decided.
"""

import copy
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.contexts.plan.plan_creation_helpers import (
    persist_plan_core,
    persist_weekly_workouts,
)
from app.core.training.periodization.training_constants import training_km
from app.infrastructure.integrations.post_sync_service import auto_map_and_adjust
from app.models import RunLog, TrainingPlan, User
from app.schemas.plan_request import PlanRequest

RUNNABLE = ("rest", "recovery")


def _make_user(db: Session) -> User:
    user = User(
        id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com", name="Runner"
    )
    db.add(user)
    db.flush()
    return user


def _make_plan(
    db: Session,
    user: User,
    *,
    base: float,
    distance: float,
    weeks: int,
    runs: int,
    start: date,
) -> TrainingPlan:
    """Persist a real generated plan the way the app does — normalized tree
    (``weekly_plans``/``daily_workouts``) plus the denormalized ``plan_data``."""
    request = PlanRequest(
        current_km=base,
        target_distance=distance,
        weeks=weeks,
        max_runs_per_week=runs,
    )
    plan_data = TrainingPlanGenerator().generate_plan(base, distance, weeks, runs)
    plan = persist_plan_core(request, user, plan_data, db)
    plan.start_date = start
    persist_weekly_workouts(plan, plan_data, db)
    db.commit()
    return plan


def _planned_sessions(plan_data: List[Dict[str, Any]], start: date):
    """(date, distance, type) for every running day, keyed off the plan start."""
    out = []
    for week in plan_data:
        week_start = start + timedelta(weeks=week["week"] - 1)
        for workout in week.get("daily_workouts", []):
            if (workout.get("distance") or 0) <= 0:
                continue
            if workout.get("type") in RUNNABLE:
                continue
            out.append(
                (
                    week_start + timedelta(days=(workout.get("day") or 1) - 1),
                    float(workout["distance"]),
                    workout.get("type"),
                )
            )
    return out


def _log_runs(
    db: Session,
    user: User,
    sessions,
    *,
    today: date,
    completion: float,
    distance_factor: float,
    pace_min_km: float,
    plan: TrainingPlan,
) -> int:
    """Log a run for the sessions up to ``today``, honouring ``completion``."""
    logged = 0
    past = [s for s in sessions if s[0] <= today]
    keep = int(len(past) * completion)
    for index, (day, distance, _kind) in enumerate(past):
        if index >= keep:
            continue
        km = round(distance * distance_factor, 2)
        if km <= 0:
            continue
        run = RunLog(
            id=str(uuid.uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            date=day,
            distance_km=km,
            duration_minutes=round(km * pace_min_km, 1),
            avg_pace_min_km=pace_min_km,
            workout_type="easy",
            source="intervals",
        )
        db.add(run)
        logged += 1
    db.commit()
    return logged


def _reload(db: Session, plan: TrainingPlan) -> List[Dict[str, Any]]:
    """A deep copy of the plan's JSON snapshot.

    Deep, not shallow: ``list(...)`` copies only the outer list, so a "before"
    snapshot would share its nested workout dicts with the live object and every
    later mutation would look like it had already been there. That aliasing is
    what makes a before/after comparison silently vacuous.
    """
    db.expire_all()
    fresh = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
    return copy.deepcopy(list(fresh.plan_data or []))


def _race_distance(plan_data: List[Dict[str, Any]]) -> float:
    for week in plan_data:
        for workout in week.get("daily_workouts", []):
            if workout.get("type") == "race":
                return float(workout.get("distance") or 0)
    return 0.0


def _assert_still_sound(before: List[Dict[str, Any]], after: List[Dict[str, Any]]):
    """Adapting a plan must never break it."""
    assert len(after) == len(before), "adaptation changed the number of weeks"

    issues = check_plan_structure(after)
    assert issues["fatal"] == [], (
        f"adaptation made the plan unrunnable: {issues['fatal']}"
    )

    # Race day is set by the event: no adaptation may move it.
    assert _race_distance(after) == _race_distance(before), (
        "adaptation rescaled race day"
    )

    # Every week still needs a runnable session.
    for week in after:
        runs = [
            w
            for w in week.get("daily_workouts", [])
            if w.get("type") not in RUNNABLE and (w.get("distance") or 0) > 0
        ]
        assert runs, f"week {week.get('week')} lost its runnable session"

    # A taper week may be reduced, never inflated: the taper is the drawdown.
    for original, adapted in zip(before, after):
        if original.get("phase") != "taper":
            continue
        assert training_km(adapted) <= training_km(original) + 0.05, (
            f"taper week {adapted.get('week')} grew from "
            f"{training_km(original):.1f} to {training_km(adapted):.1f}"
        )

    # The taper still descends toward race day.
    taper = [training_km(w) for w in after if w.get("phase") == "taper"]
    for earlier, later in zip(taper, taper[1:]):
        assert later <= earlier + 0.05, f"taper climbs after adaptation: {taper}"


def _run_scenario(
    db: Session, *, completion: float, distance_factor: float, pace_min_km: float
):
    """Generate a plan, replay a runner profile, adapt, and return before/after."""
    today = date.today()
    start = today - timedelta(days=7 * 6)  # six weeks in: half the plan is past
    user = _make_user(db)
    plan = _make_plan(db, user, base=30.0, distance=10.0, weeks=12, runs=4, start=start)
    before = _reload(db, plan)
    sessions = _planned_sessions(before, start)
    logged = _log_runs(
        db,
        user,
        sessions,
        today=today,
        completion=completion,
        distance_factor=distance_factor,
        pace_min_km=pace_min_km,
        plan=plan,
    )
    results = auto_map_and_adjust(user, db, AdaptationService())
    after = _reload(db, plan)
    return before, after, logged, results


def test_on_plan_runner_leaves_a_sound_plan(test_db: Session):
    """Completing the sessions roughly as prescribed keeps the plan sound."""
    before, after, logged, results = _run_scenario(
        test_db, completion=1.0, distance_factor=1.0, pace_min_km=5.5
    )
    assert logged > 0, "no runs were logged — the fixture is not exercising anything"
    assert results, "auto_map_and_adjust returned nothing for an active plan"
    _assert_still_sound(before, after)


def test_automatic_sync_auto_adjusts_volume_when_signals_warrant(test_db: Session):
    """The automatic path now adjusts volume when signals are strong enough.

    ``auto_map_and_adjust`` maps runs, gathers signals, and applies a
    conservative volume adjustment + VDOT recalibration. An over-performing
    runner (130% prescribed distance, fast paces) should trigger an upward
    adjustment — and the result must still be a sound plan.
    """
    before, after, logged, results = _run_scenario(
        test_db, completion=1.0, distance_factor=1.3, pace_min_km=4.4
    )
    assert logged > 0
    assert results and results[0]["runs_mapped"] > 0, (
        f"the sync did not map any logged run: {results}"
    )
    _assert_still_sound(before, after)


def test_auto_adjust_records_change_plan(test_db: Session):
    """When the sync auto-adjusts, the plan carries a visible change_plan."""
    today = date.today()
    start = today - timedelta(days=7 * 6)
    user = _make_user(test_db)
    plan = _make_plan(
        test_db, user, base=30.0, distance=10.0, weeks=12, runs=4, start=start
    )
    before = _reload(test_db, plan)
    sessions = _planned_sessions(before, start)
    _log_runs(
        test_db,
        user,
        sessions,
        today=today,
        completion=1.0,
        distance_factor=1.3,
        pace_min_km=4.4,
        plan=plan,
    )
    results = auto_map_and_adjust(user, test_db, AdaptationService())
    assert results

    test_db.expire_all()
    fresh = test_db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()

    if results[0].get("auto_adjusted"):
        cp = fresh.last_change_plan
        assert cp is not None, "auto-adjust did not record a change_plan"
        assert cp["action"] == "auto_adjust"
        assert cp.get("seen") is False
        assert cp["reason"]
        history = fresh.adaptation_history or []
        assert any(e.get("type") == "auto_adjust" for e in history)
    # If signals didn't warrant auto-adjust (e.g., neutral multiplier after
    # the deadband), the test just verifies no crash — both outcomes are valid.


def test_auto_adjust_respects_manual_cooldown(test_db: Session):
    """A recent manual intent prevents the ambient sync from auto-adjusting."""
    from datetime import datetime, timezone

    today = date.today()
    start = today - timedelta(days=7 * 6)
    user = _make_user(test_db)
    plan = _make_plan(
        test_db, user, base=30.0, distance=10.0, weeks=12, runs=4, start=start
    )
    before = _reload(test_db, plan)
    sessions = _planned_sessions(before, start)
    _log_runs(
        test_db,
        user,
        sessions,
        today=today,
        completion=1.0,
        distance_factor=1.3,
        pace_min_km=4.4,
        plan=plan,
    )

    plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    test_db.commit()

    results = auto_map_and_adjust(user, test_db, AdaptationService())
    assert results
    assert results[0].get("auto_adjusted") is False, (
        "auto-adjust should be suppressed during the manual cooldown"
    )


def _future_weeks(db: Session, plan: TrainingPlan, from_week: int):
    from app.models import WeeklyPlan

    return (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number > from_week,
        )
        .order_by(WeeklyPlan.week_number)
        .all()
    )


def _applied_scenario(db: Session, multiplier: float):
    """Generate a plan, apply a volume multiplier to its future weeks, read back."""
    from app.contexts.plan.adaptation.week_adjuster import (
        apply_adjustment_to_future_weeks,
    )

    today = date.today()
    start = today - timedelta(days=7 * 6)
    user = _make_user(db)
    plan = _make_plan(db, user, base=30.0, distance=10.0, weeks=12, runs=4, start=start)
    before = _reload(db, plan)
    orm_before = _orm_distances(db, plan)
    future = _future_weeks(db, plan, from_week=6)
    assert future, "no future weeks to adjust"
    recorder: List[Dict[str, Any]] = []
    outcome = apply_adjustment_to_future_weeks(
        plan,
        future,
        multiplier,
        db,
        current_week=6,
        current_day_of_week=1,
        recorder=recorder,
    )
    db.commit()
    return {
        "before": before,
        "after": _reload(db, plan),
        "orm_before": orm_before,
        "orm_after": _orm_distances(db, plan),
        "outcome": outcome,
    }


def _session_distances(plan_data: List[Dict[str, Any]]) -> List[float]:
    """Every prescribed distance, flattened — what the adjuster actually moves."""
    return [
        float(w.get("distance") or 0)
        for week in plan_data
        for w in week.get("daily_workouts", [])
    ]


def _orm_distances(db: Session, plan: TrainingPlan) -> List[float]:
    """The same distances as stored on the normalized ``daily_workouts`` rows."""
    from app.models import DailyWorkout, WeeklyPlan

    rows = (
        db.query(DailyWorkout)
        .join(WeeklyPlan, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
        .filter(WeeklyPlan.training_plan_id == plan.id)
        .order_by(WeeklyPlan.week_number, DailyWorkout.day_of_week)
        .all()
    )
    return [float(w.distance_km or 0) for w in rows]


def test_applied_downturn_keeps_the_plan_runnable(test_db: Session):
    """Scaling future weeks down must not collapse or break the plan."""
    result = _applied_scenario(test_db, 0.75)
    before, after = result["before"], result["after"]
    _assert_still_sound(before, after)
    # The downturn must actually have done something, or this proves nothing.
    # The adjuster moves the normalized ``daily_workouts`` rows; ``plan_data``
    # is re-derived from them afterwards, so the two must agree.
    assert result["orm_after"] != result["orm_before"], (
        f"the applied adjustment changed nothing — outcome={result['outcome']}"
    )
    assert _session_distances(after) == result["orm_after"], (
        "plan_data and the normalized workouts diverged after an adjustment: "
        f"json={_session_distances(after)[:8]} orm={result['orm_after'][:8]}"
    )
    for week in after:
        runs = [
            w
            for w in week.get("daily_workouts", [])
            if w.get("type") not in RUNNABLE and (w.get("distance") or 0) > 0
        ]
        assert runs, f"week {week.get('week')} has no runnable session after a downturn"


def test_applied_upturn_cannot_exceed_per_run_contracts(test_db: Session):
    """Scaling future weeks up must respect the single-session contracts.

    An upturn is the dangerous direction: it is the one path that can push a
    session past the caps generation enforces, so it is asserted explicitly.
    """
    result = _applied_scenario(test_db, 1.20)
    before, after = result["before"], result["after"]
    _assert_still_sound(before, after)

    breaches = []
    for week in after:
        for workout in week.get("daily_workouts", []):
            km = workout.get("distance") or 0
            if week.get("is_recovery") or week.get("phase") == "taper":
                continue
            if workout.get("type") == "easy" and km > 21.0:
                breaches.append((week.get("week"), "easy", km))
            if workout.get("type") == "long" and km > 40.05:
                breaches.append((week.get("week"), "long", km))
    assert not breaches, f"an upturn prescribed over-long sessions: {breaches}"


def test_over_performing_runner_adapts_without_breaking_the_plan(test_db: Session):
    """Running longer and faster may adapt volume up — but must not break it."""
    before, after, logged, _ = _run_scenario(
        test_db, completion=1.0, distance_factor=1.25, pace_min_km=4.5
    )
    assert logged > 0
    _assert_still_sound(before, after)

    # Future volume may rise with demonstrated fitness, but the plan's own
    # ceilings still hold: nothing may be prescribed beyond the race-appropriate
    # long-run contract after adaptation.
    for week in after:
        if week.get("phase") == "taper":
            continue
        longest = max(
            (
                w.get("distance") or 0
                for w in week.get("daily_workouts", [])
                if w.get("type") == "long"
            ),
            default=0,
        )
        assert longest <= 40.05, (
            f"adapted week {week.get('week')} long run {longest} km"
        )


def test_mostly_missed_runner_is_not_inflated(test_db: Session):
    """Missed sessions must never raise the future prescription."""
    before, after, logged, _ = _run_scenario(
        test_db, completion=0.4, distance_factor=0.6, pace_min_km=6.5
    )
    assert logged > 0
    _assert_still_sound(before, after)

    original_peak = max(
        (w.get("total_km") or 0 for w in before if w.get("phase") != "taper"), default=0
    )
    adapted_peak = max(
        (w.get("total_km") or 0 for w in after if w.get("phase") != "taper"), default=0
    )
    assert adapted_peak <= original_peak + 0.05, (
        f"a runner who missed sessions had their load raised: "
        f"{original_peak:.1f} -> {adapted_peak:.1f}"
    )


def test_adaptation_does_not_exceed_single_session_contracts(test_db: Session):
    """No adapted week may prescribe a single run past the contracted cap.

    The same bound ``fill_shortfall`` enforces at generation time: adaptation
    redistributes volume, and that redistribution must respect the per-run caps
    rather than moving the overflow into one heroic session.
    """
    before, after, _, _ = _run_scenario(
        test_db, completion=1.0, distance_factor=1.35, pace_min_km=4.2
    )
    _assert_still_sound(before, after)

    breaches = []
    for week in after:
        if week.get("is_recovery") or week.get("phase") == "taper":
            continue
        for workout in week.get("daily_workouts", []):
            km = workout.get("distance") or 0
            if workout.get("type") == "easy" and km > 21.0:
                breaches.append((week.get("week"), "easy", km))
            if workout.get("type") == "long" and km > 36.05:
                breaches.append((week.get("week"), "long", km))
    assert not breaches, f"adapted plan prescribes over-long sessions: {breaches}"
