"""Validate plan generation across mileage/distance combinations.

Checks both Performance (time-goal) and Regular (distance-goal) generators
for structural skew: quality vs long run ratio, easy run minimums, and
volume accuracy.
"""

import sys

sys.path.insert(0, ".")

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator


def analyze_performance_plan(label, target_distance, current_weekly_km, weeks=8):
    gen = PerformancePlanGenerator()
    current_pace = 6.0
    goal_pace = 5.5

    plan = gen.generate_plan(
        target_distance=target_distance,
        current_pace=current_pace,
        goal_pace=goal_pace,
        weeks=weeks,
        current_weekly_km=current_weekly_km,
        runs_per_week=5,
    )

    issues = []
    worst_ratio = 0
    shortest_easy = 999

    for week in plan["weekly_plans"]:
        workouts = week["daily_workouts"]
        long_runs = [w for w in workouts if w["type"] == "long"]
        long_dist = long_runs[0]["distance"] if long_runs else 0

        for w in workouts:
            if w.get("quality", False) and long_dist > 0:
                ratio = w["distance"] / long_dist
                worst_ratio = max(worst_ratio, ratio)
                if ratio > 1.1:
                    issues.append(
                        f"W{week['week']}: {w['type']}={w['distance']:.1f}km > long={long_dist:.1f}km ({ratio:.2f}x)"
                    )

            if w["type"] == "easy" and w["distance"] > 0:
                shortest_easy = min(shortest_easy, w["distance"])
                if w["distance"] < 2.0:
                    issues.append(
                        f"W{week['week']}: easy={w['distance']:.1f}km (too short)"
                    )

        if not week.get("validation", {}).get("valid", True):
            issues.append(
                f"W{week['week']}: VALIDATION FAILED - {week['validation']['message']}"
            )

    if shortest_easy == 999:
        shortest_easy = 0

    return {
        "label": label,
        "worst_quality_ratio": worst_ratio,
        "shortest_easy": shortest_easy,
        "issues": issues,
        "total_km": plan["summary"]["total_km"],
    }


def analyze_regular_plan(label, current_km, target_distance, weeks=8):
    gen = TrainingPlanGenerator()
    weekly_plans = gen.generate_plan(
        current_km=current_km,
        target_distance=target_distance,
        weeks=weeks,
        max_runs_per_week=4,
    )

    issues = []
    worst_ratio = 0
    shortest_easy = 999
    total_actual = 0

    for week in weekly_plans:
        workouts = week["daily_workouts"]
        long_runs = [w for w in workouts if w["type"] == "long"]
        long_dist = long_runs[0]["distance"] if long_runs else 0

        for w in workouts:
            if w["type"] in ("tempo", "interval", "hill") and long_dist > 0:
                ratio = w.get("distance", 0) / long_dist
                worst_ratio = max(worst_ratio, ratio)
                if ratio > 1.1:
                    issues.append(
                        f"W{week['week']}: {w['type']}={w.get('distance', 0):.1f}km > long={long_dist:.1f}km ({ratio:.2f}x)"
                    )

            if w["type"] == "easy" and w.get("distance", 0) > 0:
                shortest_easy = min(shortest_easy, w["distance"])

        total_actual += week["total_km"]

        if not week.get("validation", {}).get("valid", True):
            issues.append(f"W{week['week']}: {week['validation']['message']}")

    if shortest_easy == 999:
        shortest_easy = 0

    return {
        "label": label,
        "worst_quality_ratio": worst_ratio,
        "shortest_easy": shortest_easy,
        "issues": issues,
        "total_actual_km": total_actual,
    }


def main():
    print("=" * 80)
    print("PERFORMANCE PLAN GENERATOR (time-goal)")
    print("=" * 80)

    perf_scenarios = [
        ("5K very low (10km/wk)", 5.0, 10),
        ("5K low (15km/wk)", 5.0, 15),
        ("5K medium (25km/wk)", 5.0, 25),
        ("10K very low (10km/wk)", 10.0, 10),
        ("10K low (12km/wk)", 10.0, 12),
        ("10K medium (30km/wk)", 10.0, 30),
        ("Half low (25km/wk)", 21.1, 25),
        ("Half medium (40km/wk)", 21.1, 40),
        ("Marathon low (35km/wk)", 42.2, 35),
        ("Marathon medium (55km/wk)", 42.2, 55),
    ]

    print(
        f"\n{'Scenario':<28} {'Worst Q/L':>10} {'Min Easy':>10} {'Issues':>7} {'Total km':>10}"
    )
    print("-" * 70)

    all_perf_issues = []
    for label, dist, km in perf_scenarios:
        result = analyze_performance_plan(label, dist, km)
        status = "OK" if not result["issues"] else f"{len(result['issues'])}"
        print(
            f"{result['label']:<28} {result['worst_quality_ratio']:>9.2f}x {result['shortest_easy']:>9.1f} {status:>7} {result['total_km']:>9.1f}"
        )
        if result["issues"]:
            all_perf_issues.extend(result["issues"][:3])

    if all_perf_issues:
        print(f"\nSample issues ({len(all_perf_issues)} shown):")
        for issue in all_perf_issues[:10]:
            print(f"  - {issue}")

    print("\n")
    print("=" * 80)
    print("REGULAR PLAN GENERATOR (distance-goal)")
    print("=" * 80)

    reg_scenarios = [
        ("5K low (15km/wk)", 15, 5.0),
        ("5K medium (25km/wk)", 25, 5.0),
        ("10K low (12km/wk)", 12, 10.0),
        ("10K medium (30km/wk)", 30, 10.0),
        ("10K high (50km/wk)", 50, 10.0),
        ("Half low (25km/wk)", 25, 21.1),
        ("Half medium (40km/wk)", 40, 21.1),
        ("Marathon low (35km/wk)", 35, 42.2),
        ("Marathon medium (55km/wk)", 55, 42.2),
    ]

    print(
        f"\n{'Scenario':<28} {'Worst Q/L':>10} {'Min Easy':>10} {'Issues':>7} {'Total km':>10}"
    )
    print("-" * 70)

    all_reg_issues = []
    for label, km, dist in reg_scenarios:
        result = analyze_regular_plan(label, km, dist)
        status = "OK" if not result["issues"] else f"{len(result['issues'])}"
        print(
            f"{result['label']:<28} {result['worst_quality_ratio']:>9.2f}x {result['shortest_easy']:>9.1f} {status:>7} {result['total_actual_km']:>9.1f}"
        )
        if result["issues"]:
            all_reg_issues.extend(result["issues"][:3])

    if all_reg_issues:
        print(f"\nSample issues ({len(all_reg_issues)} shown):")
        for issue in all_reg_issues[:10]:
            print(f"  - {issue}")

    # Summary
    print("\n")
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(
        f"Performance plans: {sum(1 for level, d, k in perf_scenarios if not analyze_performance_plan(level, d, k)['issues'])}/{len(perf_scenarios)} clean"
    )
    print(
        f"Regular plans:     {sum(1 for level, k, d in reg_scenarios if not analyze_regular_plan(level, k, d)['issues'])}/{len(reg_scenarios)} clean"
    )
    print()
    print("Target: Quality/Long ratio <= 1.0, Shortest easy >= 3.0km")


if __name__ == "__main__":
    main()
