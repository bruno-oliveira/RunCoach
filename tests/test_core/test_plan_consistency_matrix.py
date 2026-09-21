"""Consistency matrix over the plan generator's input space.

The audit harness (``scripts/audit_all.py``) measures the whole matrix; this
test permanently pins the invariants that must never regress, on a
deterministic sample of ~230 configs spanning every plan family the engine
can build:

- weekly actual never exceeds the model's weekly target by more than
  ``max(2.0 km, 15%)`` (the target is re-derived from
  ``mileage_progression.calculate_weekly_progression`` with the exact
  arguments each generator passes — it is what the runner is shown);
- a week's ``total_km`` equals the sum of its day-card distances;
- every week contains at least one running session;
- the long run never carries more than half the week's volume where the
  frequency makes that a composition choice rather than a necessity;
- the plan's duration matches the requested weeks exactly.

Two exception classes are **documented and reported, never silent**:

- race week: the goal event is installed on the final week and the taper
  target deliberately does not budget for the race distance itself, so the
  final week's overshoot vs the taper target is structural. Every instance
  is counted and surfaced as a warning summary.
- low-volume performance plans: the performance generator's authored
  sessions overshoot the shared progression at bases <= 20 km/wk (the
  capacity-model workstream's target). Counted and surfaced.

The sample is a fixed stride over ordered grids, so a failure names a config
anyone can reproduce with ``TrainingPlanGenerator`` directly.
"""

import warnings
from functools import lru_cache

import pytest

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.periodization import mileage_progression
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.profiles.backyard_profile import classify_backyard
from app.core.training.profiles.trail_profile import classify_trail
from app.exceptions import RunCoachException

VDOT = 45.0
PERF_CURRENT_PACE = 6.0
PERF_GOAL_PACE = 5.6
BACKYARD_LOOP_KM = 6.706

OVERSHOOT_TOL_KM = 2.0
OVERSHOOT_TOL_PCT = 0.15
LONG_RUN_MAX_SHARE = 0.5
TOTAL_KM_TOLERANCE_KM = 0.06

REST_TYPES = ("rest",)

# Road-family plan types — the ones whose long-run share is a composition
# choice once the frequency reaches 4 sessions.
ROAD_PLAN_TYPES = ("recovery", "base")

# Performance plans overshoot the shared progression at low bases (audit
# finding #1); tolerated and reported until the capacity-model workstream
# lands, never silently.
PERF_KNOWN_OVERSHOOT_MAX_BASE_KM = 20.0

MAX_REPORTED_EXAMPLES = 10


def _backyard_loops(goal_distance_km):
    return max(6, min(48, round(goal_distance_km / BACKYARD_LOOP_KM)))


def _road_configs():
    for base in (10, 20, 30, 40, 50, 60, 80):
        for distance in (10.0, 21.1, 42.2):
            for runs in (2, 3, 4, 5, 6):
                for weeks in (8, 12, 16):
                    yield (
                        "recovery" if base <= 30 else "base",
                        base,
                        distance,
                        runs,
                        weeks,
                    )


def _performance_configs():
    for base in (10, 30, 50, 80):
        for distance in (10.0, 21.1, 42.2):
            for runs in (2, 4, 6):
                for weeks in (8, 12, 16):
                    yield ("performance", base, distance, runs, weeks)


def _backyard_configs():
    for goal_km in (56.0, 100.0, 160.0):
        for base in (40, 70):
            for runs in (3, 5):
                for weeks in (16, 20):
                    yield ("backyard", base, goal_km, runs, weeks)


def _transformation_configs():
    for distance in (100.0, 160.0, 240.0):
        for base in (40, 60, 80):
            for runs in (4, 6):
                for weeks in (16, 20):
                    yield ("transformation", base, distance, runs, weeks)


def _build_configs():
    """Fixed-stride sample over the ordered grids — deterministic, debuggable."""
    road = list(_road_configs())[::2]
    performance = list(_performance_configs())[::2]
    backyard = list(_backyard_configs())
    transformation = list(_transformation_configs())[::2]
    return road + performance + backyard + transformation


def _targets_for(plan_type, base, distance, runs, weeks, plan):
    """Re-derive the weekly model targets with each generator's own arguments."""
    if plan_type == "performance":
        implied_seconds = int(PERF_CURRENT_PACE * distance * 60)
        plan_vdot = VDOTCalculator.calculate_vdot(distance, implied_seconds)
        return mileage_progression.calculate_weekly_progression(
            base, distance, len(plan), runs, plan_vdot
        )
    if plan_type == "backyard":
        profile = classify_backyard(_backyard_loops(distance))
        return mileage_progression.calculate_weekly_progression(
            base,
            profile.equivalent_distance_km,
            weeks,
            runs,
            VDOT,
            trail_profile=profile.as_trail_profile(),
        )
    if plan_type == "transformation":
        profile = classify_trail(distance, 1500.0)
        return mileage_progression.calculate_weekly_progression(
            base, distance, weeks, runs, VDOT, trail_profile=profile
        )
    return mileage_progression.calculate_weekly_progression(
        base, distance, weeks, runs, VDOT
    )


def _generate(plan_type, base, distance, runs, weeks):
    if plan_type == "performance":
        plan = PerformancePlanGenerator().generate_plan(
            target_distance=distance,
            current_pace=PERF_CURRENT_PACE,
            goal_pace=PERF_GOAL_PACE,
            weeks=weeks,
            current_weekly_km=base,
            runs_per_week=runs,
        )["weekly_plans"]
    elif plan_type == "backyard":
        profile = classify_backyard(_backyard_loops(distance))
        plan = TrainingPlanGenerator().generate_plan(
            base,
            profile.equivalent_distance_km,
            weeks,
            runs,
            vdot=VDOT,
            backyard_profile=profile,
        )
    elif plan_type == "transformation":
        profile = classify_trail(distance, 1500.0)
        plan = TrainingPlanGenerator().generate_plan(
            base, distance, weeks, runs, vdot=VDOT, trail_profile=profile
        )
    else:
        plan = TrainingPlanGenerator().generate_plan(
            base, distance, weeks, runs, vdot=VDOT
        )
    return plan


@lru_cache(maxsize=1)
def _load_matrix():
    """Generate the sample once; returns (ok_entries, skipped_entries)."""
    ok = []
    skipped = []
    for plan_type, base, distance, runs, weeks in _build_configs():
        config = {
            "plan_type": plan_type,
            "base_km": base,
            "distance_km": distance,
            "runs_per_week": runs,
            "weeks": weeks,
        }
        try:
            plan = _generate(plan_type, base, distance, runs, weeks)
        except (RunCoachException, ValueError) as exc:
            # Documented engine refusals (below-floor base, too few weeks,
            # no frequency composer) — recorded, never silently dropped.
            skipped.append(
                {
                    "config": config,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        targets = _targets_for(plan_type, base, distance, runs, weeks, plan)
        ok.append({"config": config, "plan": plan, "targets": targets})
    return ok, skipped


def _fmt(entry):
    c = entry["config"]
    return (
        f"{c['plan_type']}(base={c['base_km']}, dist={c['distance_km']}, "
        f"runs={c['runs_per_week']}, weeks={c['weeks']})"
    )


def _sessions(week):
    return [
        w
        for w in week["daily_workouts"]
        if w.get("type") not in REST_TYPES and (w.get("distance") or 0) > 0
    ]


def _fail(name, violations):
    shown = "\n".join(f"  - {v}" for v in violations[:MAX_REPORTED_EXAMPLES])
    pytest.fail(
        f"{len(violations)} {name} violation(s); first "
        f"{min(len(violations), MAX_REPORTED_EXAMPLES)}:\n{shown}",
        pytrace=False,
    )


def _report_exceptions(bucket, entries):
    """Surface documented exceptions as a warning summary — reported, not silent."""
    if not entries:
        return
    sample = "; ".join(entries[:3])
    warnings.warn(
        f"[documented exception: {bucket}] {len(entries)} instance(s), e.g. {sample}",
        stacklevel=2,
    )


class TestPlanConsistencyMatrix:
    def test_matrix_generated_meaningful_sample(self):
        ok, skipped = _load_matrix()
        assert len(ok) + len(skipped) == len(_build_configs())
        assert len(ok) >= 150, (
            f"only {len(ok)} of {len(_build_configs())} sampled configs "
            f"generated a plan — the matrix is silently collapsing"
        )
        assert all(s["reason"] for s in skipped)

    def test_weekly_actual_never_overshoots_model_target(self):
        ok, _ = _load_matrix()
        violations = []
        race_week = []
        perf_low_base = []
        for entry in ok:
            plan = entry["plan"]
            cfg = entry["config"]
            for idx, week in enumerate(plan):
                target = entry["targets"][idx]
                actual = week["total_km"]
                tol = max(OVERSHOOT_TOL_KM, OVERSHOOT_TOL_PCT * target)
                if actual <= target + tol:
                    continue
                detail = (
                    f"{_fmt(entry)} week {week['week']}: target "
                    f"{target:.1f} km, actual {actual:.1f} km "
                    f"(+{(actual - target) / target * 100:.0f}%, tolerance "
                    f"+{tol:.1f} km)"
                )
                if idx == len(plan) - 1:
                    # Race week: the goal event is not budgeted in the taper
                    # target, so its overshoot is structural. Reported, not
                    # silent.
                    race_week.append(detail)
                elif (
                    cfg["plan_type"] == "performance"
                    and cfg["base_km"] <= PERF_KNOWN_OVERSHOOT_MAX_BASE_KM
                ):
                    perf_low_base.append(detail)
                else:
                    violations.append(detail)
        _report_exceptions("race-week overshoot vs taper target", race_week)
        _report_exceptions(
            "low-base performance overshoot (capacity-model fix pending)",
            perf_low_base,
        )
        if violations:
            _fail("weekly overshoot beyond max(2.0 km, 15%)", violations)

    def test_week_total_matches_workout_distances(self):
        ok, _ = _load_matrix()
        violations = []
        for entry in ok:
            for week in entry["plan"]:
                workout_sum = sum(
                    (w.get("distance") or 0) for w in week["daily_workouts"]
                )
                if abs(workout_sum - week["total_km"]) > TOTAL_KM_TOLERANCE_KM:
                    violations.append(
                        f"{_fmt(entry)} week {week['week']}: total_km "
                        f"{week['total_km']:.2f} vs workout sum "
                        f"{workout_sum:.2f}"
                    )
        if violations:
            _fail("total_km vs workout-distance-sum mismatch", violations)

    def test_every_week_has_a_session(self):
        ok, _ = _load_matrix()
        violations = []
        for entry in ok:
            for week in entry["plan"]:
                if not _sessions(week):
                    violations.append(
                        f"{_fmt(entry)} week {week['week']}: no running "
                        f"session (cards: "
                        f"{[w['type'] for w in week['daily_workouts']]})"
                    )
        if violations:
            _fail("week without a single session", violations)

    def test_long_run_share(self):
        ok, _ = _load_matrix()
        violations = []
        documented = []
        for entry in ok:
            cfg = entry["config"]
            for week in entry["plan"]:
                sessions = _sessions(week)
                total = week["total_km"]
                long_runs = [w for w in sessions if w.get("type") == "long"]
                if not long_runs or total <= 0:
                    continue
                share = long_runs[0]["distance"] / total
                if share <= LONG_RUN_MAX_SHARE:
                    continue
                detail = (
                    f"{_fmt(entry)} week {week['week']}: long run "
                    f"{long_runs[0]['distance']:.1f} km of {total:.1f} km "
                    f"({share * 100:.0f}%, {len(sessions)} sessions)"
                )
                # Low-frequency weeks need the long run to carry the week;
                # ultras are built around it by design. Both are documented
                # exceptions and reported; a road plan at 4+ sessions has no
                # such excuse.
                if cfg["plan_type"] in ROAD_PLAN_TYPES and cfg["runs_per_week"] >= 4:
                    violations.append(detail)
                else:
                    documented.append(detail)
        _report_exceptions(
            "long run > 50% of the week (low-frequency / ultra plans)",
            documented,
        )
        if violations:
            _fail("long run > 50% of week volume at 4+ runs/week", violations)

    def test_plan_duration_matches_requested_weeks(self):
        ok, _ = _load_matrix()
        violations = []
        for entry in ok:
            requested = entry["config"]["weeks"]
            actual = len(entry["plan"])
            if actual != requested:
                violations.append(
                    f"{_fmt(entry)}: requested {requested} weeks, plan has {actual}"
                )
        if violations:
            _fail("plan duration mismatch", violations)
