"""Low-frequency plan quality harness.

Reproduces the metrics from PLAN_GENERATOR_QUALITY_EVALUATION.md focused on
2-3 runs/week road plans across distances and bases, so generator changes can
be measured before/after. Not committed to CI — a developer measurement aid.

Usage: python3 scripts/eval_lowfreq.py
"""

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator

DISTANCES = {"5K": 5.0, "10K": 10.0, "Half": 21.1, "Mara": 42.2}
# (distance label, base km, weeks)
CASES = [
    ("5K", 5.0, 35, 12),
    ("10K", 10.0, 20, 12),
    ("10K", 10.0, 40, 12),
    ("Half", 21.1, 25, 16),
    ("Half", 21.1, 50, 16),
    ("Mara", 42.2, 30, 18),
    ("Mara", 42.2, 60, 18),
]


def week_metrics(week):
    runs = [
        w for w in week["daily_workouts"] if w.get("type") not in ("rest", "recovery")
    ]
    long = next((w for w in runs if w.get("type") == "long"), None)
    long_km = long.get("distance", 0) if long else 0
    q = sum(1 for w in runs if w.get("type") in ("tempo", "interval", "hill"))
    total = week["total_km"]
    return total, long_km, q, week.get("is_recovery", False)


def analyze(label, dist, base, weeks, runs):
    gen = TrainingPlanGenerator()
    plan = gen.generate_plan(base, dist, weeks, max_runs_per_week=runs, vdot=45.0)
    totals, longs, qs, recs = [], [], [], []
    for wk in plan:
        t, lr, q, r = week_metrics(wk)
        totals.append(t)
        longs.append(lr)
        qs.append(q)
        recs.append(r)

    peak = max(totals)
    peak_idx = totals.index(peak)
    peak_lr = longs[peak_idx]
    lr_share = peak_lr / peak if peak else 0

    # max LR share across loading weeks
    max_lr_share = max(
        (lo / to) for lo, to, r in zip(longs, totals, recs) if to > 0 and not r
    )

    # 10% rule violations among loading weeks (vs prior loading week)
    violations = 0
    worst_jump = 0.0
    prev_load = None
    for t, r in zip(totals, recs):
        if r:
            continue
        if prev_load is not None and prev_load > 0:
            jump = (t - prev_load) / prev_load
            if jump > 0.105:
                violations += 1
                worst_jump = max(worst_jump, jump)
        prev_load = t

    below_base = sum(1 for t, r in zip(totals, recs) if not r and t < base * 0.995)
    min_load = min((t for t, r in zip(totals, recs) if not r), default=0)

    # post-deload stumble: loading week after a recovery week lower than it
    stumbles = 0
    for i in range(1, len(totals)):
        if recs[i - 1] and not recs[i] and totals[i] < totals[i - 1]:
            stumbles += 1

    print(
        f"[{label:4} base{base:>3} {runs}r wk{weeks}] "
        f"peak{peak:>5.0f} total{sum(totals):>5.0f} peakLR{peak_lr:>5.1f} "
        f"LRshare{lr_share * 100:>3.0f}% maxLRshare{max_lr_share * 100:>3.0f}% "
        f"viol{violations} worst{worst_jump * 100:>3.0f}% "
        f"belowbase{below_base} min{min_load:>4.0f} stumble{stumbles}"
    )
    print(
        "   km: "
        + " ".join(f"{t:>4.0f}{'r' if rr else ' '}" for t, rr in zip(totals, recs))
    )
    print("   LR: " + " ".join(f"{lr:>4.1f} " for lr in longs))


def main():
    for runs in (2, 3):
        print(f"\n===== {runs} RUNS / WEEK =====")
        for label, dist, base, weeks in CASES:
            analyze(label, dist, base, weeks, runs)


if __name__ == "__main__":
    main()
