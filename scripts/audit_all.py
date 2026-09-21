"""Full-matrix plan-generation audit.

One reusable entry point for the generator-quality questions that keep
resurfacing as one-off scripts (test_plan_skew.py, eval_lowfreq.py): does a
plan deliver the weekly mileage it promises the runner, how much of a week
rides on the long run, and where does the builder silently over- or
under-deliver against the model's own weekly targets?

For every cell of the matrix — plan type × base mileage × goal distance ×
runs/week × block length — the harness generates a plan, reconstructs each
week's actual km from the day cards, and diffs it against the weekly target
the periodisation model computed for the same inputs (the number the user is
shown). Overshoot and shortfall are recorded per week and rolled up per
(plan type, frequency bucket).

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
from app.core.training.periodization import mileage_progression
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.profiles.backyard_profile import classify_backyard
from app.core.training.profiles.trail_profile import classify_trail

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
        "distances": [10.0, 21.1, 42.2],
        "max_base": 30.0,
        "description": "road distance-goal on a rebuilding base (<= 30 km/wk)",
    },
    "base": {
        "distances": [10.0, 21.1, 42.2],
        "description": "road distance-goal, any base",
    },
    "performance": {
        "distances": [10.0, 21.1, 42.2],
        # The performance generator silently clamps weeks to [6, 16]; weeks
        # outside that band never produce the requested duration.
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
    """Recompute the weekly model targets the generator aimed at.

    The targets are not stored on the generated weeks, so the harness
    re-derives them with the exact arguments each generator passes to
    ``calculate_weekly_progression``. For performance plans the block length
    is whatever the plan actually contains (the generator clamps weeks).
    """
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
    weekly = []
    for idx, week in enumerate(
        plan if isinstance(plan, list) else plan["weekly_plans"]
    ):
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
        is_race_week = (
            idx == len(plan if isinstance(plan, list) else plan["weekly_plans"]) - 1
        )
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


def run_audit(args):
    vdot = args.vdot
    records = []
    skips = defaultdict(int)
    started = time.time()
    count = 0
    for config in iter_configs(args):
        if args.max_plans and count >= args.max_plans:
            break
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
        except Exception as exc:  # noqa: BLE001 - the refusal IS the record
            skips[f"{type(exc).__name__}: {str(exc)[:60]}"] += 1
            records.append(
                {
                    "config": config,
                    "status": "skipped",
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
            "vdot": vdot,
            "perf_current_pace": PERF_CURRENT_PACE,
            "perf_goal_pace": PERF_GOAL_PACE,
            "configs_requested": count,
            "plans_generated": sum(1 for r in records if r["status"] == "ok"),
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
            }
        )
    return rows


def print_summary(summary, report):
    meta = report["meta"]
    print("=" * 108)
    print(
        f"PLAN GENERATION AUDIT — {meta['plans_generated']} plans, "
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
