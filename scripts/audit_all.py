"""Full-matrix plan-generation audit.

One reusable entry point for the generator-quality questions that keep
resurfacing as one-off scripts (test_plan_skew.py, eval_lowfreq.py): does a
plan deliver the weekly mileage it promises the runner, how much of a week
rides on the long run, and where does the builder silently over- or
under-deliver against the model's own weekly targets?

The default ``product`` mode first validates every cell through the public
request schema and treats any accepted-but-unbuildable plan as a failure. The
``robustness`` mode reports only rejected inputs and their rejection messages;
``all`` retains the legacy direct-generator sweep for exploratory work.

For every generated cell — plan type × base mileage × goal distance ×
runs/week × block length — the harness reconstructs each week's actual km from
the day cards and diffs it against the target stamped on the final week.
Overshoot, shortfall, final-guard findings, ramp breaches, race presence, and
resolved metadata are recorded and rolled up per (plan type, frequency bucket).

The plan types are the audit's own taxonomy over what the engine can build;
the engine has no such enum:

- ``recovery``       — road distance-goal plans on a rebuilding base (≤ 30 km/wk)
- ``base``           — road distance-goal plans, any base
- ``performance``    — time-goal road plans (PerformancePlanGenerator)
- ``backyard``       — hourly-loop goals (BackyardProfile); the goal distance
                       maps to a loop count at the standard 6.706 km loop
- ``transformation`` — trail/ultra projections (trail_profile) at 100 km+

Combos the engine refuses (below-floor base, too few weeks, no frequency
composer) are recorded as skips with the refusing exception, never silently
dropped: the skip *pattern* is itself an audit finding.

Usage:
    python3 scripts/audit_all.py                     # full matrix
    python3 scripts/audit_all.py --mode robustness   # schema rejection report
    python3 scripts/audit_all.py --mode all          # legacy direct sweep
    python3 scripts/audit_all.py --plan-types base,performance
    python3 scripts/audit_all.py --frequencies 2,3 --bases 20,30
    python3 scripts/audit_all.py --output /tmp/report.json --max-plans 200
"""

import argparse
import json
import logging
import time
from collections import defaultdict

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.core.training.periodization import mileage_progression
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.profiles.backyard_profile import classify_backyard
from app.core.training.profiles.trail_profile import classify_trail
from app.schemas import PlanRequest
from app.schemas.performance_request import PerformancePlanRequest

# The audit runs the engine, not the web schema: one fixed fitness anchor so
# cells differ only by the axis under test (same convention as eval_lowfreq).
VDOT = 45.0

# Performance plans are paced, not VDOT-seeded: the generator derives its own
# VDOT from the current pace. 6.0 → 5.6 min/km is a realistic ~7% goal.
PERF_CURRENT_PACE = 6.0
PERF_GOAL_PACE = 5.6

BACKYARD_LOOP_KM = 6.706

REST_TYPES = ("rest",)
QUALITY_TYPES = ("tempo", "interval", "hill")

BUILDER_LOGGER = "app.contexts.plan.generators.plan_generator"

PLAN_TYPE_SPECS = {
    "recovery": {
        "distances": [5.0, 10.0, 21.1, 42.2],
        "max_base": 30.0,
        "description": "road distance-goal on a rebuilding base (<= 30 km/wk)",
    },
    "base": {
        "distances": [5.0, 10.0, 21.1, 42.2],
        "description": "road distance-goal, any base",
    },
    "performance": {
        "distances": [5.0, 10.0, 21.1, 42.2],
        "weeks": [8, 12, 16],
        "description": "time-goal road plans",
    },
    "backyard": {
        "distances": [56.0, 100.0, 160.0, 240.0],
        "description": "hourly-loop backyard goals",
    },
    "transformation": {
        "distances": [100.0, 160.0, 240.0],
        "description": "trail/ultra projections",
    },
}

DEFAULT_BASES = [10, 20, 30, 40, 50, 60, 80]
DEFAULT_WEEKS = [4, 8, 12, 16, 20, 24]
DEFAULT_FREQUENCIES = [1, 2, 3, 4, 5, 6, 7]


def frequency_bucket(runs: int) -> str:
    """Collapse the frequency axis into summary-table buckets."""
    if runs in (3, 4):
        return "3-4"
    if runs in (5, 6):
        return "5-6"
    return str(runs)


def backyard_loops_for_distance(distance_km: float) -> int:
    """Map a goal distance onto hourly loops at the standard loop length."""
    return max(6, min(48, round(distance_km / BACKYARD_LOOP_KM)))


class _BuilderWarningCollector(logging.Handler):
    """Capture the generator's own warnings while a plan is being built.

    The generator already logs what it cannot reconcile ("the week layout
    cannot place the modelled volume at this frequency") — capturing those
    records makes under-delivery measurable without re-deriving it.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _targets_for(plan_type, base, distance, runs, weeks, vdot, plan=None):
    """Recompute targets only for legacy output without stamped targets."""
    if plan_type == "performance":
        eff_weeks = len(plan["weekly_plans"])
        implied_seconds = int(PERF_CURRENT_PACE * distance * 60)
        plan_vdot = VDOTCalculator.calculate_vdot(distance, implied_seconds)
        progression = mileage_progression.calculate_weekly_progression(
            base, distance, eff_weeks, runs, plan_vdot
        )
        return _apply_reachability_gate(progression, base, runs, trail=None)
    if plan_type == "backyard":
        profile = classify_backyard(backyard_loops_for_distance(distance))
        progression = mileage_progression.calculate_weekly_progression(
            base,
            profile.equivalent_distance_km,
            weeks,
            runs,
            vdot,
            trail_profile=profile.as_trail_profile(),
        )
        return _apply_reachability_gate(
            progression, base, runs, trail=profile.as_trail_profile()
        )
    if plan_type == "transformation":
        profile = classify_trail(distance, 1500.0)
        progression = mileage_progression.calculate_weekly_progression(
            base, distance, weeks, runs, vdot, trail_profile=profile
        )
        return _apply_reachability_gate(progression, base, runs, trail=profile)
    progression = mileage_progression.calculate_weekly_progression(
        base, distance, weeks, runs, vdot
    )
    return _apply_reachability_gate(progression, base, runs, trail=None)


def _apply_reachability_gate(progression, base, runs, trail):
    """Replicate the engine's reachability gate on re-derived targets.

    ``generate_plan`` caps the progression's peak at what the schedule can
    deliver (``resolve_reachable_target`` + ``cap_progression_to_peak``)
    before any week is built; the harness must measure against the capped
    targets or it reports shortfalls the engine already reconciled away.
    """
    from app.core.training.periodization.mileage_progression import (
        cap_progression_to_peak,
        resolve_reachable_target,
        typical_session_length_km,
    )

    session_km = typical_session_length_km(trail)
    peak_target = max(progression, default=0.0)
    reachable_peak, cap_reason, _diag = resolve_reachable_target(
        peak_target, runs, session_km, base_km=base
    )
    if cap_reason is not None:
        return cap_progression_to_peak(progression, reachable_peak, base)
    return progression


def _generate(plan_type, base, distance, runs, weeks, vdot):
    """Generate one plan; returns ``(plan, targets, builder_warnings)``."""
    collector = _BuilderWarningCollector()
    logger = logging.getLogger(BUILDER_LOGGER)
    logger.addHandler(collector)
    try:
        if plan_type == "performance":
            plan = PerformancePlanGenerator().generate_plan(
                target_distance=distance,
                current_pace=PERF_CURRENT_PACE,
                goal_pace=PERF_GOAL_PACE,
                weeks=weeks,
                current_weekly_km=base,
                runs_per_week=runs,
            )
            targets = _targets_for(
                plan_type, base, distance, runs, weeks, vdot, plan=plan
            )
        elif plan_type == "backyard":
            profile = classify_backyard(backyard_loops_for_distance(distance))
            plan = TrainingPlanGenerator().generate_plan(
                base,
                profile.equivalent_distance_km,
                weeks,
                runs,
                vdot=vdot,
                backyard_profile=profile,
            )
            targets = _targets_for(plan_type, base, distance, runs, weeks, vdot)
        elif plan_type == "transformation":
            profile = classify_trail(distance, 1500.0)
            plan = TrainingPlanGenerator().generate_plan(
                base, distance, weeks, runs, vdot=vdot, trail_profile=profile
            )
            targets = _targets_for(plan_type, base, distance, runs, weeks, vdot)
        else:
            plan = TrainingPlanGenerator().generate_plan(
                base, distance, weeks, runs, vdot=vdot
            )
            targets = _targets_for(plan_type, base, distance, runs, weeks, vdot)
    finally:
        logger.removeHandler(collector)
    plan_weeks = plan if isinstance(plan, list) else plan["weekly_plans"]
    stamped = [week.get("weekly_target_km") for week in plan_weeks]
    if stamped and all(target is not None for target in stamped):
        targets = stamped
    return plan, targets, collector.messages


def _week_sessions(week):
    """Day cards that ask the runner to run, per the generator's own set."""
    return [
        w
        for w in week["daily_workouts"]
        if w.get("type") not in REST_TYPES and (w.get("distance") or 0) > 0
    ]


def extract_plan_record(config, plan, targets, builder_warnings):
    """Normalize one generated plan into per-week metrics and roll-ups."""
    plan_weeks = plan if isinstance(plan, list) else plan["weekly_plans"]
    guard = check_plan_structure(plan_weeks)
    weekly = []
    delivered_high_water = config["base_km"]
    ramp_breaches = []
    for idx, week in enumerate(plan_weeks):
        workouts = week["daily_workouts"]
        sessions = _week_sessions(week)
        workout_sum = sum((w.get("distance") or 0) for w in workouts)
        actual = week.get("total_km")
        total_km_field = actual
        if actual is None:
            actual = workout_sum
        target = targets[idx] if idx < len(targets) else 0.0
        long_km = max(
            ((w.get("distance") or 0) for w in sessions if w.get("type") == "long"),
            default=0.0,
        )
        is_race_week = bool(week.get("is_race_week"))
        if not week.get("is_recovery") and not is_race_week:
            if actual > delivered_high_water * 1.12 + 0.05:
                ramp_breaches.append(week.get("week", idx + 1))
            delivered_high_water = max(delivered_high_water, actual)
        overshoot = max(0.0, actual - target)
        shortfall = max(0.0, target - actual)
        weekly.append(
            {
                "week": week.get("week", idx + 1),
                "phase": week.get("phase"),
                "is_recovery": bool(week.get("is_recovery")),
                "is_race_week": is_race_week,
                "target_km": round(target, 2),
                "actual_km": round(actual, 2),
                "workout_sum_km": round(workout_sum, 2),
                "total_km_field": round(total_km_field, 2)
                if total_km_field is not None
                else None,
                "total_km_mismatch": bool(
                    total_km_field is not None
                    and abs(total_km_field - workout_sum) > 0.06
                ),
                "overshoot_km": round(overshoot, 2),
                "shortfall_km": round(shortfall, 2),
                "overshoot_pct": round(overshoot / target, 4) if target > 0 else None,
                "sessions": len(sessions),
                "quality_sessions": sum(
                    1
                    for w in sessions
                    if w.get("quality") or w.get("type") in QUALITY_TYPES
                ),
                "long_km": round(long_km, 2),
                "long_share": round(long_km / actual, 4) if actual > 0 else None,
                "validation_status": (week.get("validation") or {}).get("status"),
            }
        )

    base = config["base_km"]
    training_weeks = [w for w in weekly if not w["is_race_week"]]
    overshoot_weeks = [
        w
        for w in training_weeks
        if w["target_km"] > 0
        and w["actual_km"] > w["target_km"] + max(2.0, 0.15 * w["target_km"])
    ]
    deviations = [
        (w["actual_km"] - w["target_km"]) / w["target_km"]
        for w in training_weeks
        if w["target_km"] > 0
    ]
    shortfalls = [
        w["shortfall_km"] / w["target_km"] for w in training_weeks if w["target_km"] > 0
    ]
    long_shares = [
        w["long_share"] for w in training_weeks if w["long_share"] is not None
    ]
    peak_actual = max((w["actual_km"] for w in weekly), default=0.0)
    peak_target = max((w["target_km"] for w in weekly), default=0.0)
    first_week = plan_weeks[0] if plan_weeks else {}
    race_present = any(
        workout.get("type") == "race"
        for week in plan_weeks
        for workout in week.get("daily_workouts", [])
    )

    return {
        "config": config,
        "status": "ok",
        "weeks_effective": len(weekly),
        "weeks": weekly,
        "aggregates": {
            "peak_target_km": round(peak_target, 2),
            "peak_actual_km": round(peak_actual, 2),
            "peak_actual_over_base": round(peak_actual / base, 3) if base else None,
            "peak_target_over_base": round(peak_target / base, 3) if base else None,
            "median_week_deviation_pct": round(_median(deviations), 4),
            "p90_week_deviation_pct": round(_percentile(deviations, 0.9), 4),
            "weeks_over_tolerance": len(overshoot_weeks),
            "weeks_over_tolerance_share": round(
                len(overshoot_weeks) / max(1, len(deviations)), 4
            ),
            "mean_shortfall_pct": round(_mean(shortfalls), 4),
            "mean_long_share": round(_mean(long_shares), 4),
            "max_long_share": round(max(long_shares), 4) if long_shares else None,
            "race_week_overshoot_km": round(weekly[-1]["overshoot_km"], 2)
            if weekly and weekly[-1]["is_race_week"]
            else None,
            "total_actual_km": round(sum(w["actual_km"] for w in weekly), 2),
            "total_target_km": round(sum(w["target_km"] for w in weekly), 2),
            "total_km_field_mismatches": sum(
                1 for w in weekly if w["total_km_mismatch"]
            ),
            "builder_warnings": len(builder_warnings),
            "builder_warning_samples": builder_warnings[:2],
            "guard_fatal": guard["fatal"],
            "guard_warnings": guard["warnings"],
            "ramp_breach_weeks": ramp_breaches,
            "race_present": race_present,
            "validation_errors": sum(
                1 for w in weekly if w["validation_status"] == "error"
            ),
            "validation_degraded": sum(
                1 for w in weekly if w["validation_status"] == "degraded"
            ),
            "requested_runs_per_week": first_week.get(
                "requested_runs_per_week", config["runs_per_week"]
            ),
            "resolved_runs_per_week": first_week.get(
                "resolved_runs_per_week", config["runs_per_week"]
            ),
        },
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _percentile(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def iter_configs(args):
    """Yield audit configs across the matrix, honouring per-type distance sets."""
    plan_types = _parse_list(args.plan_types, list(PLAN_TYPE_SPECS), str)
    # ``recovery`` and ``base`` call the same road generator over overlapping
    # low-base rows. Keep the alias available when explicitly selected, but do
    # not double-count it in the default product report.
    if getattr(args, "mode", "product") == "product" and "base" in plan_types:
        plan_types = [plan_type for plan_type in plan_types if plan_type != "recovery"]
    bases = _parse_list(args.bases, DEFAULT_BASES, float)
    frequencies = _parse_list(args.frequencies, DEFAULT_FREQUENCIES, int)
    all_weeks = _parse_list(args.weeks, DEFAULT_WEEKS, int)
    distance_filter = (
        _parse_list(args.distances, None, float) if args.distances else None
    )
    for plan_type in plan_types:
        spec = PLAN_TYPE_SPECS[plan_type]
        weeks_choices = spec.get("weeks", all_weeks)
        distances = spec["distances"]
        if distance_filter:
            distances = [d for d in distances if d in distance_filter]
        for base in bases:
            if "max_base" in spec and base > spec["max_base"]:
                continue
            for distance in distances:
                for runs in frequencies:
                    for weeks in weeks_choices:
                        yield {
                            "plan_type": plan_type,
                            "base_km": base,
                            "distance_km": distance,
                            "runs_per_week": runs,
                            "weeks": weeks,
                        }


def _parse_list(raw, defaults, cast):
    if raw is None:
        return defaults
    return [cast(x) for x in str(raw).split(",") if x.strip()]


def _validate_product_config(config):
    """Validate an audit cell through the same public schema as production."""
    common = {
        "current_km": config["base_km"],
        "weeks": config["weeks"],
        "max_runs_per_week": config["runs_per_week"],
    }
    plan_type = config["plan_type"]
    distance = config["distance_km"]
    if plan_type == "performance":
        return PerformancePlanRequest(
            target_distance=distance,
            current_pace=PERF_CURRENT_PACE,
            goal_pace=PERF_GOAL_PACE,
            current_time="current pace",
            goal_time="goal pace",
            weeks=config["weeks"],
            current_weekly_km=config["base_km"],
            runs_per_week=config["runs_per_week"],
        )
    if plan_type == "backyard":
        return PlanRequest(
            **common,
            target_distance=1.0,  # replaced by the backyard schema projection
            is_backyard=True,
            backyard_target_loops=backyard_loops_for_distance(distance),
        )
    if plan_type == "transformation":
        return PlanRequest(
            **common,
            target_distance=distance,
            is_trail=True,
            target_elevation_gain_m=1500.0,
        )
    return PlanRequest(**common, target_distance=distance)


def run_audit(args):
    vdot = args.vdot
    mode = getattr(args, "mode", "product")
    records = []
    skips = defaultdict(int)
    started = time.time()
    count = 0
    for config in iter_configs(args):
        if args.max_plans and count >= args.max_plans:
            break
        try:
            _validate_product_config(config)
            schema_error = None
        except Exception as exc:  # noqa: BLE001 - rejection is audit evidence
            schema_error = f"{type(exc).__name__}: {exc}"

        if mode == "product" and schema_error:
            continue
        if mode == "robustness":
            if schema_error is None:
                continue
            count += 1
            skips[schema_error[:120]] += 1
            records.append(
                {
                    "config": config,
                    "status": "rejected",
                    "rejection": schema_error,
                }
            )
            continue

        count += 1
        try:
            plan, targets, warnings_ = _generate(
                config["plan_type"],
                config["base_km"],
                config["distance_km"],
                config["runs_per_week"],
                config["weeks"],
                vdot,
            )
        except Exception as exc:  # noqa: BLE001 - failure/refusal is the record
            skips[f"{type(exc).__name__}: {str(exc)[:60]}"] += 1
            records.append(
                {
                    "config": config,
                    "status": "failed" if mode == "product" else "skipped",
                    "skip_reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        records.append(extract_plan_record(config, plan, targets, warnings_))
        if not args.quiet and len(records) % 250 == 0:
            print(f"  ... {len(records)} configs processed", flush=True)

    summary = summarize(records)
    report = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": mode,
            "vdot": vdot,
            "perf_current_pace": PERF_CURRENT_PACE,
            "perf_goal_pace": PERF_GOAL_PACE,
            "configs_requested": count,
            "plans_generated": sum(1 for r in records if r["status"] == "ok"),
            "failed": sum(1 for r in records if r["status"] == "failed"),
            "rejected": sum(1 for r in records if r["status"] == "rejected"),
            "skipped": sum(1 for r in records if r["status"] == "skipped"),
            "duration_secs": round(time.time() - started, 1),
            "plan_type_specs": PLAN_TYPE_SPECS,
        },
        "summary": summary,
        "skip_reasons": dict(sorted(skips.items(), key=lambda kv: -kv[1])),
        "plans": records,
    }
    return report


def summarize(records):
    """Group plan records by (plan type, frequency bucket) for the table."""
    groups = defaultdict(list)
    for r in records:
        if r["status"] != "ok":
            continue
        cfg = r["config"]
        groups[(cfg["plan_type"], frequency_bucket(cfg["runs_per_week"]))].append(r)

    rows = []
    for (plan_type, bucket), rs in sorted(groups.items()):
        weeks = [w for r in rs for w in r["weeks"] if not w["is_race_week"]]
        deviations = [
            (w["actual_km"] - w["target_km"]) / w["target_km"] * 100
            for w in weeks
            if w["target_km"] > 0
        ]
        over_tol = sum(
            1
            for w in weeks
            if w["target_km"] > 0
            and w["actual_km"] > w["target_km"] + max(2.0, 0.15 * w["target_km"])
        )
        long_shares = [w["long_share"] for w in weeks if w["long_share"] is not None]
        mismatches = sum(1 for r in rs for w in r["weeks"] if w["total_km_mismatch"])
        warn_plans = sum(1 for r in rs if r["aggregates"]["builder_warnings"] > 0)
        fatal_plans = sum(1 for r in rs if r["aggregates"]["guard_fatal"])
        guard_warn_plans = sum(1 for r in rs if r["aggregates"]["guard_warnings"])
        ramp_breaches = sum(len(r["aggregates"]["ramp_breach_weeks"]) for r in rs)
        missing_races = sum(1 for r in rs if not r["aggregates"]["race_present"])
        resolved_frequency = sum(
            1
            for r in rs
            if r["aggregates"]["requested_runs_per_week"]
            != r["aggregates"]["resolved_runs_per_week"]
        )
        rows.append(
            {
                "plan_type": plan_type,
                "frequency_bucket": bucket,
                "plans": len(rs),
                "training_weeks": len(weeks),
                "median_dev_pct": round(_median(deviations), 1),
                "p90_dev_pct": round(_percentile(deviations, 0.9), 1),
                "max_dev_pct": round(max(deviations), 1) if deviations else None,
                "min_dev_pct": round(min(deviations), 1) if deviations else None,
                "weeks_over_tolerance": over_tol,
                "weeks_over_tolerance_pct": round(
                    100.0 * over_tol / max(1, len(weeks)), 1
                ),
                "mean_long_share": round(_mean(long_shares), 3),
                "max_long_share": round(max(long_shares), 3) if long_shares else None,
                "total_km_field_mismatches": mismatches,
                "plans_with_builder_warnings": warn_plans,
                "plans_with_guard_fatal": fatal_plans,
                "plans_with_guard_warnings": guard_warn_plans,
                "ramp_breaches": ramp_breaches,
                "plans_missing_race": missing_races,
                "plans_with_resolved_frequency": resolved_frequency,
            }
        )
    return rows


def print_summary(summary, report):
    meta = report["meta"]
    print("=" * 108)
    print(
        f"PLAN GENERATION AUDIT ({meta['mode']}) — {meta['plans_generated']} plans, "
        f"{meta['failed']} failed, {meta['rejected']} rejected, "
        f"{meta['skipped']} skipped, {meta['duration_secs']}s, "
        f"vdot {meta['vdot']}"
    )
    print("=" * 108)
    header = (
        f"{'plan type':<14} {'freq':<5} {'plans':>5} {'weeks':>6} "
        f"{'med dev%':>9} {'p90 dev%':>9} {'min%':>7} {'max%':>7} "
        f"{'>tol%':>6} {'LR mean':>8} {'LR max':>7} {'warns':>6}"
    )
    print(header)
    print("-" * 108)
    for row in summary:
        print(
            f"{row['plan_type']:<14} {row['frequency_bucket']:<5} {row['plans']:>5} "
            f"{row['training_weeks']:>6} {row['median_dev_pct']:>9.1f} "
            f"{row['p90_dev_pct']:>9.1f} "
            f"{row['min_dev_pct']:>7.1f} {row['max_dev_pct']:>7.1f} "
            f"{row['weeks_over_tolerance_pct']:>6.1f} "
            f"{row['mean_long_share']:>8.2f} {row['max_long_share']:>7.2f} "
            f"{row['plans_with_builder_warnings']:>6}"
        )
    print("-" * 108)
    print(
        "dev% = (week actual - model target) / target over training weeks "
        "(race week excluded: the goal event is not budgeted in the taper target)."
    )
    print(
        ">tol% = share of training weeks overshooting the target by more than "
        "max(2.0 km, 15%)."
    )
    if report["skip_reasons"]:
        print("\nTop skip reasons (engine refusals):")
        for reason, n in list(report["skip_reasons"].items())[:8]:
            print(f"  {n:>5}  {reason}")


def main():
    parser = argparse.ArgumentParser(
        description="Audit plan generation across the full config matrix."
    )
    parser.add_argument(
        "--mode",
        choices=("product", "robustness", "all"),
        default="product",
        help="product schema matrix, rejected-input report, or legacy direct sweep",
    )
    parser.add_argument(
        "--plan-types",
        default=None,
        help="comma list: recovery,base,performance,backyard,transformation",
    )
    parser.add_argument("--bases", default=None, help="comma list of km/week values")
    parser.add_argument(
        "--distances", default=None, help="comma list of goal distances in km"
    )
    parser.add_argument(
        "--frequencies", default=None, help="comma list of runs/week values"
    )
    parser.add_argument("--weeks", default=None, help="comma list of block lengths")
    parser.add_argument("--vdot", type=float, default=VDOT)
    parser.add_argument(
        "--output", default="scripts/audit_report.json", help="JSON report path"
    )
    parser.add_argument(
        "--max-plans", type=int, default=0, help="cap on configs processed (0 = all)"
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = run_audit(args)
    print_summary(report["summary"], report)
    with open(args.output, "w") as fh:
        json.dump(report, fh, indent=1)
    print(f"\nFull report written to {args.output}")


if __name__ == "__main__":
    main()
