"""Pattern feedback — detect repeated pace patterns over recent runs."""

from datetime import timedelta
from typing import Optional


def pattern_feedback(run_log, db) -> Optional[str]:
    """Detect repeated pace patterns over last 45 days with recency weighting.

    Uses a 14-day half-life: recent deviations matter more than older ones.
    Also detects 3+ consecutive same-direction deviations (streak trigger).
    """
    if not run_log.avg_pace_min_km or not run_log.planned_pace_min_km:
        return None

    wtype = run_log.workout_type
    if not wtype:
        return None

    from app.models import RunLog

    cutoff = run_log.date - timedelta(days=45)
    recent = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == run_log.user_id,
            RunLog.workout_type == wtype,
            RunLog.avg_pace_min_km.isnot(None),
            RunLog.planned_pace_min_km.isnot(None),
            RunLog.date >= cutoff,
            RunLog.id != run_log.id,
        )
        .order_by(RunLog.date.desc())
        .limit(6)
        .all()
    )

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

    if (fast_score >= 0.6 or max_streak_fast >= 3) and wtype in ("easy", "recovery", "long"):
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
