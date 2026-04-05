"""Personalized training insights synthesized from run data.

Generates actionable, data-backed insights that go beyond simple stats.
Each insight has a category, priority, and recommendation.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.runner_profile import RunnerProfile, build_profile

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    category: str      # volume, intensity, fitness, recovery, consistency, efficiency
    title: str
    body: str
    priority: int      # 1 = highest
    icon: str          # emoji shorthand for the UI
    sentiment: str     # positive, neutral, warning, negative


class InsightsService:
    """Generates personalized insights from a RunnerProfile."""

    @staticmethod
    def get_insights(user_id: str, db: Session) -> Dict[str, Any]:
        profile = build_profile(user_id, db)
        if not profile.has_sufficient_data:
            return {
                "available": False,
                "reason": "Log at least 3 runs to unlock personalized insights.",
                "profile": profile.to_dict(),
            }

        insights = _generate_insights(profile)
        # Sort by priority (lowest number = most important)
        insights.sort(key=lambda i: i.priority)

        return {
            "available": True,
            "insights": [_insight_to_dict(i) for i in insights],
            "profile": profile.to_dict(),
        }


def _insight_to_dict(i) -> Dict[str, Any]:
    return {
        "category": i.category,
        "title": i.title,
        "body": i.body,
        "priority": i.priority,
        "icon": i.icon,
        "sentiment": i.sentiment,
    }


def _generate_insights(p: RunnerProfile) -> list:
    """Build all applicable insights from the profile."""
    insights = []

    # -- ACWR / Injury Risk --
    if p.acwr is not None:
        insights.append(_acwr_insight(p))

    # -- Volume trend --
    insights.append(_volume_insight(p))

    # -- Polarization (80/20) --
    if p.easy_pct > 0 or p.hard_pct > 0:
        insights.append(_polarization_insight(p))

    # -- VDOT / Fitness --
    if p.current_vdot:
        insights.append(_fitness_insight(p))

    # -- Consistency --
    insights.append(_consistency_insight(p))

    # -- Efficiency --
    if p.avg_efficiency is not None:
        insights.append(_efficiency_insight(p))

    # -- Long run adequacy --
    if p.longest_run_km > 0 and p.avg_weekly_km > 0:
        insights.append(_long_run_insight(p))

    # -- Workout variety --
    if p.workout_type_counts:
        insights.append(_variety_insight(p))

    return insights


# ── Individual insight generators ────────────────────────────────────────

def _acwr_insight(p: RunnerProfile) -> Insight:
    acwr = p.acwr
    if p.acwr_risk == "optimal":
        return Insight(
            category="recovery",
            title="Training load is in the sweet spot",
            body=f"Your ACWR is {acwr:.2f} — right in the 0.8–1.3 optimal zone. "
                 "You're balancing stress and recovery well. Keep it up.",
            priority=3,
            icon="\u2705",
            sentiment="positive",
        )
    elif p.acwr_risk == "low":
        return Insight(
            category="recovery",
            title="Training load is low",
            body=f"Your ACWR is {acwr:.2f} (under 0.8). You're either in a recovery "
                 "phase or under-training. If this isn't intentional, gradually increase "
                 "volume over the next 2 weeks.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    elif p.acwr_risk == "high":
        return Insight(
            category="recovery",
            title="Training load is elevated",
            body=f"Your ACWR is {acwr:.2f} — above the 1.3 threshold. "
                 "Consider an easy week soon to reduce injury risk. "
                 "Replace one quality session with an easy run.",
            priority=1,
            icon="\U0001F6A8",
            sentiment="negative",
        )
    else:  # very_high
        return Insight(
            category="recovery",
            title="Training load spike — high injury risk",
            body=f"Your ACWR is {acwr:.2f} — well above 1.5. This is a danger zone. "
                 "Take 2–3 easy days immediately. Reduce volume by 30–40% this week.",
            priority=1,
            icon="\U0001F6D1",
            sentiment="negative",
        )


def _volume_insight(p: RunnerProfile) -> Insight:
    if p.peak_weekly_km > 0 and p.avg_weekly_km > 0:
        ratio = p.peak_weekly_km / p.avg_weekly_km
        if ratio > 1.4:
            return Insight(
                category="volume",
                title="Large volume swings detected",
                body=f"Your peak week ({p.peak_weekly_km} km) is {ratio:.1f}x your "
                     f"average ({p.avg_weekly_km} km). Consistency matters more than "
                     "big weeks. Aim for <30% variation week to week.",
                priority=2,
                icon="\U0001F4C8",
                sentiment="warning",
            )
    return Insight(
        category="volume",
        title=f"Averaging {p.avg_weekly_km} km/week",
        body=f"Over the last {p.weeks_of_data} weeks you've averaged "
             f"{p.avg_weekly_km} km/week across {p.runs_per_week} runs/week. "
             f"Peak week: {p.peak_weekly_km} km.",
        priority=4,
        icon="\U0001F3C3",
        sentiment="neutral",
    )


def _polarization_insight(p: RunnerProfile) -> Insight:
    if p.easy_pct >= 75:
        return Insight(
            category="intensity",
            title="Great polarization — mostly easy running",
            body=f"{p.easy_pct:.0f}% of your runs are at easy effort. "
                 "This follows the 80/20 principle elite runners use. "
                 "Your hard sessions can be truly hard because you recover between them.",
            priority=4,
            icon="\U0001F31F",
            sentiment="positive",
        )
    elif p.easy_pct >= 60:
        return Insight(
            category="intensity",
            title="Moderate intensity balance",
            body=f"Only {p.easy_pct:.0f}% of your runs are easy — ideally aim for 80%. "
                 f"You have {p.hard_pct:.0f}% hard sessions. Try converting 1–2 moderate "
                 "runs per week to truly easy pace to improve recovery.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    else:
        return Insight(
            category="intensity",
            title="Too much intensity",
            body=f"Only {p.easy_pct:.0f}% of your runs are easy — the recommended "
                 "target is 80%. Running too hard too often leads to stagnation and "
                 "injury. Slow down your easy runs by 30–60 sec/km.",
            priority=1,
            icon="\U0001F6A8",
            sentiment="negative",
        )


def _fitness_insight(p: RunnerProfile) -> Insight:
    vdot = p.current_vdot
    if p.vdot_trend == "improving":
        return Insight(
            category="fitness",
            title=f"Fitness is improving (VDOT {vdot})",
            body="Your VDOT has trended upward recently. Your current training "
                 "is producing adaptations — stay the course.",
            priority=3,
            icon="\U0001F4AA",
            sentiment="positive",
        )
    elif p.vdot_trend == "declining":
        return Insight(
            category="fitness",
            title=f"Fitness dip detected (VDOT {vdot})",
            body="Your VDOT has dipped recently. This could be fatigue, illness, "
                 "or heat. If you've been training hard, a recovery week often "
                 "reverses the trend.",
            priority=2,
            icon="\U0001F4C9",
            sentiment="warning",
        )
    return Insight(
        category="fitness",
        title=f"Fitness is stable (VDOT {vdot})",
        body="Your VDOT has held steady. To push it higher, add one focused "
             "quality session per week (tempo or intervals) without increasing "
             "total volume.",
        priority=4,
        icon="\u2696\uFE0F",
        sentiment="neutral",
    )


def _consistency_insight(p: RunnerProfile) -> Insight:
    rpw = p.runs_per_week
    if rpw >= 4:
        return Insight(
            category="consistency",
            title=f"Strong consistency — {rpw} runs/week",
            body="Running 4+ times per week gives your body frequent adaptation signals. "
                 "This consistency is more valuable than any single workout.",
            priority=4,
            icon="\U0001F4C5",
            sentiment="positive",
        )
    elif rpw >= 3:
        return Insight(
            category="consistency",
            title=f"Solid consistency — {rpw} runs/week",
            body="Three runs per week is a great foundation. When you're ready "
                 "to progress, adding a 4th easy run gives you more volume without "
                 "more intensity.",
            priority=4,
            icon="\U0001F4C5",
            sentiment="neutral",
        )
    else:
        return Insight(
            category="consistency",
            title=f"Low frequency — {rpw} runs/week",
            body="Fewer than 3 runs/week limits adaptation. Try to add one short, "
                 "easy run (20–30 min) on a non-running day to build consistency.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )


def _efficiency_insight(p: RunnerProfile) -> Insight:
    trend = p.efficiency_trend_pct
    if trend is not None and trend > 3:
        return Insight(
            category="efficiency",
            title="Aerobic efficiency is improving",
            body=f"Your speed-to-heart-rate ratio improved {trend:.1f}% recently. "
                 "You're getting faster at the same effort — a sign of real fitness gains.",
            priority=3,
            icon="\u2764\uFE0F",
            sentiment="positive",
        )
    elif trend is not None and trend < -3:
        return Insight(
            category="efficiency",
            title="Aerobic efficiency has dipped",
            body=f"Your speed-to-heart-rate ratio dropped {abs(trend):.1f}%. "
                 "This may indicate fatigue, heat, or overtraining. "
                 "Consider more easy-paced runs this week.",
            priority=2,
            icon="\U0001F4C9",
            sentiment="warning",
        )
    return Insight(
        category="efficiency",
        title="Aerobic efficiency is steady",
        body="Your speed-to-heart-rate ratio is stable. Consistent easy running "
             "is the best way to push this metric higher over time.",
        priority=5,
        icon="\u2764\uFE0F",
        sentiment="neutral",
    )


def _long_run_insight(p: RunnerProfile) -> Insight:
    ratio = p.longest_run_km / p.avg_weekly_km if p.avg_weekly_km > 0 else 0
    if ratio > 0.5:
        return Insight(
            category="volume",
            title="Long run is a big chunk of weekly volume",
            body=f"Your longest run ({p.longest_run_km} km) is {ratio:.0%} of your "
                 f"weekly average ({p.avg_weekly_km} km). Ideally the long run should "
                 "be 25–35% of weekly volume. Add more mid-week volume to balance.",
            priority=3,
            icon="\U0001F4CF",
            sentiment="warning",
        )
    return Insight(
        category="volume",
        title="Good long-run balance",
        body=f"Your longest run ({p.longest_run_km} km) is {ratio:.0%} of weekly "
             f"volume — well balanced.",
        priority=5,
        icon="\U0001F44D",
        sentiment="positive",
    )


def _variety_insight(p: RunnerProfile) -> Insight:
    counts = p.workout_type_counts or {}
    total = sum(counts.values())
    if total == 0:
        return Insight(
            category="intensity",
            title="No workout type data",
            body="We couldn't determine your workout types. "
                 "Tag your runs (easy, tempo, interval) for better insights.",
            priority=5,
            icon="\U0001F3F7\uFE0F",
            sentiment="neutral",
        )

    quality_types = {"tempo", "interval", "hill", "race"}
    quality_count = sum(counts.get(t, 0) for t in quality_types)
    quality_pct = quality_count / total * 100 if total else 0

    if quality_pct < 5 and total >= 6:
        return Insight(
            category="intensity",
            title="Missing quality sessions",
            body="You've done almost no tempo, interval, or hill workouts recently. "
                 "Adding 1–2 quality sessions per week (while keeping total volume "
                 "the same) can unlock significant fitness gains.",
            priority=2,
            icon="\u26A1",
            sentiment="warning",
        )
    elif quality_pct > 30:
        return Insight(
            category="intensity",
            title="Heavy on quality sessions",
            body=f"{quality_pct:.0f}% of your runs are quality sessions. "
                 "Limit hard sessions to 2–3 per week max to ensure recovery.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    return Insight(
        category="intensity",
        title="Good workout mix",
        body=f"You're doing {quality_pct:.0f}% quality sessions — a healthy balance "
             "of easy and hard work.",
        priority=5,
        icon="\u2705",
        sentiment="positive",
    )
