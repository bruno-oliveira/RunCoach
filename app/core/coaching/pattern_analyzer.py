"""Pattern feedback — detect repeated pace patterns over recent runs (pure).

Pure: no I/O, no ORM. The caller (context layer) supplies the candidate runs via
``app.contexts.runner.fitness.coaching_data.fetch_pattern_candidates``; this
module only filters by workout type and weights by recency.
"""

from typing import List, Optional


def pattern_feedback(run_log, candidate_runs: List) -> Optional[str]:
    """Detect repeated pace patterns with 14-day-half-life recency weighting.

    Recent deviations matter more than older ones; 3+ consecutive same-direction
    deviations also trigger (streak).

    Args:
        run_log: The run just logged.
        candidate_runs: Same-user runs within the last 45 days (excluding
            ``run_log``) that have both planned and actual pace, ordered newest
            first. The SQL fetch is the caller's responsibility — see module
            docstring.

    Returns:
        A coaching message, or None when no pattern is detected.
    """
    if not run_log.avg_pace_min_km or not run_log.planned_pace_min_km:
        return None

    wtype = run_log.effective_workout_type
    if not wtype:
        return None

    # effective_workout_type is a derived property (reconciles the raw tag with
    # inference), so the type match is applied in Python rather than in SQL.
    recent = [r for r in candidate_runs if r.effective_workout_type == wtype][:6]

    if len(recent) < 2:
        return None

    half_life = 14.0
    weighted_fast = 0.0
    weighted_slow = 0.0
    total_weight = 0.0
    streak_fast = 0
    streak_slow = 0
    max_streak_fast = 0
    max_streak_slow = 0

    for r in recent:
        days_ago = max(0, (run_log.date - r.date).days)
        weight = 0.5 ** (days_ago / half_life)
        deviation = (r.avg_pace_min_km - r.planned_pace_min_km) / r.planned_pace_min_km

        total_weight += weight
        if deviation < -0.05:
            weighted_fast += weight
            streak_fast += 1
            streak_slow = 0
        elif deviation > 0.08:
            weighted_slow += weight
            streak_fast = 0
            streak_slow += 1
        else:
            streak_fast = 0
            streak_slow = 0

        max_streak_fast = max(max_streak_fast, streak_fast)
        max_streak_slow = max(max_streak_slow, streak_slow)

    fast_score = weighted_fast / total_weight if total_weight > 0 else 0
    slow_score = weighted_slow / total_weight if total_weight > 0 else 0

    if (fast_score >= 0.6 or max_streak_fast >= 3) and wtype in (
        "easy",
        "recovery",
        "long",
    ):
        return (
            f"Pattern detected: your recent {wtype} runs "
            "have been consistently faster than planned. Running easy days "
            "too hard limits recovery and long-term improvement."
        )
    elif (slow_score >= 0.6 or max_streak_slow >= 3) and wtype in ("tempo", "interval"):
        return (
            f"Pattern detected: your recent {wtype} "
            "sessions have been consistently slower than target. Consider "
            "whether the pace target is realistic or if you need more recovery."
        )
    return None
