"""Validate plan generation across a wide range of inputs.

Generates plans for weekly mileage 0-90km, 2-5 runs/week, all distances,
and reports key metrics for each combination.
"""

import sys
import traceback
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.core.generators.plan_generator import TrainingPlanGenerator
from app.constants import DISTANCE_NAMES, SUPPORTED_DISTANCES


def summarize_week(week: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key metrics from a generated week."""
    workouts = week.get("daily_workouts", [])
    run_workouts = [
        w for w in workouts
        if w.get("type") not in ("rest", "recovery", "strength", "cross_training")
        and w.get("distance", 0) > 0
    ]
    distances = [w["distance"] for w in run_workouts]
    total_km = sum(distances)
    long_run = max(distances) if distances else 0
    return {
        "total_km": round(total_km, 1),
        "runs": len(run_workouts),
        "long_run": round(long_run, 1),
        "workouts": len(workouts),
    }


def validate_plan(plan: List[Dict[str, Any]], current_km: float,
                  target_distance: float, weeks: int, max_runs: int) -> List[str]:
    """Check plan for issues. Returns list of warnings."""
    warnings = []
    prev_km = current_km
    high_water = current_km  # tracks non-recovery highs

    for i, week in enumerate(plan, 1):
        summary = summarize_week(week)
        total = summary["total_km"]
        is_recovery = week.get("is_recovery", False)

        # Check 10% rule against the high-water mark (not the recovery dip)
        if i > 1 and high_water > 0 and not is_recovery:
            increase_pct = ((total - high_water) / high_water) * 100
            if increase_pct > 12:
                warnings.append(
                    f"  Week {i}: {increase_pct:.0f}% over high-water ({high_water:.1f} -> {total:.1f}km)"
                )

        if not is_recovery and total > high_water:
            high_water = total

        # Check for zero-distance weeks (non-recovery)
        if total == 0 and i < weeks:
            warnings.append(f"  Week {i}: 0km total (not final week)")

        # Check long run > 50% of weekly volume
        if total > 0 and summary["long_run"] / total > 0.55:
            warnings.append(
                f"  Week {i}: long run is {summary['long_run']/total:.0%} of weekly volume "
                f"({summary['long_run']:.1f}/{total:.1f}km)"
            )

        # Check runs vs requested
        if summary["runs"] > max_runs:
            warnings.append(
                f"  Week {i}: {summary['runs']} runs (requested max {max_runs})"
            )

        prev_km = total

    return warnings


def run_validation():
    generator = TrainingPlanGenerator()

    mileages = list(range(10, 81, 5))  # 10-80km (step 5)
    runs_per_week = [2, 3, 4, 5]
    distances = SUPPORTED_DISTANCES  # [5.0, 10.0, 21.1, 30.0, 42.2]

    # Constraints from config defaults
    min_mileage = {5.0: 5.0, 10.0: 10.0, 21.1: 15.0, 30.0: 15.0, 42.2: 25.0}
    min_runs = {5.0: 2, 10.0: 2, 21.1: 3, 30.0: 4, 42.2: 4}
    default_weeks = {5.0: 8, 10.0: 10, 21.1: 12, 30.0: 12, 42.2: 16}

    total = 0
    successes = 0
    failures = 0
    warnings_count = 0
    all_issues: List[str] = []

    print("=" * 80)
    print("TRAINING PLAN VALIDATION")
    print("=" * 80)
    print(f"Mileages: {mileages[0]}-{mileages[-1]}km (step 5)")
    print(f"Runs/week: {runs_per_week}")
    print(f"Distances: {[DISTANCE_NAMES[d] for d in distances]}")
    print("=" * 80)

    for distance in distances:
        dist_name = DISTANCE_NAMES[distance]
        weeks = default_weeks[distance]
        dist_failures = []
        dist_warnings = []

        print(f"\n{'─' * 80}")
        print(f"  {dist_name} ({distance}km) — {weeks} weeks")
        print(f"{'─' * 80}")
        print(f"  {'Mileage':<10} {'Runs':<6} {'Result':<10} {'Wk1 km':<10} {'Peak km':<10} {'Long peak':<10}")
        print(f"  {'─'*10} {'─'*5} {'─'*9} {'─'*9} {'─'*9} {'─'*9}")

        for mileage in mileages:
            for max_runs in runs_per_week:
                total += 1

                # Skip invalid combos (would fail validation)
                if max_runs < min_runs[distance]:
                    continue
                if mileage > 0 and mileage < min_mileage[distance]:
                    continue
                if mileage == 0 and distance not in [5.0, 10.0]:
                    continue
                if mileage == 0 and weeks < 8:
                    continue

                try:
                    plan = generator.generate_plan(
                        current_km=float(mileage),
                        target_distance=distance,
                        weeks=weeks,
                        max_runs_per_week=max_runs,
                    )

                    week_summaries = [summarize_week(w) for w in plan]
                    wk1 = week_summaries[0]["total_km"]
                    peak = max(s["total_km"] for s in week_summaries)
                    peak_long = max(s["long_run"] for s in week_summaries)

                    plan_warnings = validate_plan(plan, mileage, distance, weeks, max_runs)

                    status = "OK" if not plan_warnings else f"WARN({len(plan_warnings)})"
                    print(f"  {mileage:<10} {max_runs:<6} {status:<10} {wk1:<10} {peak:<10} {peak_long:<10}")

                    if plan_warnings:
                        warnings_count += 1
                        header = f"  {dist_name} | {mileage}km/wk | {max_runs} runs/wk"
                        dist_warnings.append(header)
                        dist_warnings.extend(plan_warnings)

                    successes += 1

                except Exception as e:
                    failures += 1
                    err_msg = str(e)[:60]
                    print(f"  {mileage:<10} {max_runs:<6} {'FAIL':<10} {err_msg}")
                    dist_failures.append(
                        f"  {dist_name} | {mileage}km/wk | {max_runs} runs/wk: {err_msg}"
                    )

        if dist_failures:
            all_issues.append(f"\n  FAILURES for {dist_name}:")
            all_issues.extend(dist_failures)
        if dist_warnings:
            all_issues.append(f"\n  WARNINGS for {dist_name}:")
            all_issues.extend(dist_warnings)

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total combinations tested: {total}")
    print(f"  Successful:                {successes}")
    print(f"  With warnings:             {warnings_count}")
    print(f"  Failures:                  {failures}")

    if all_issues:
        print(f"\n{'─' * 80}")
        print("ISSUES:")
        print("─" * 80)
        for line in all_issues:
            print(line)

    print()
    return failures == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
