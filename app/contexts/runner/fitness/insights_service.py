"""Personalized training insights synthesized from run data.

Generates actionable, data-backed insights that go beyond simple stats.
Each insight has a category, priority, and recommendation.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.contexts.runner.profile.profile_builder import build_profile
from app.contexts.runner.profile.runner_profile import RunnerProfile

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    category: str  # volume, intensity, fitness, recovery, consistency, efficiency
    title: str
    body: str
    priority: int  # 1 = highest
    icon: str  # emoji shorthand for the UI
    sentiment: str  # positive, neutral, warning, negative


class InsightsService:
    """Generates personalized insights from a RunnerProfile."""

    @staticmethod
    def get_insights(user_id: str, db: Session) -> Dict[str, Any]:
        profile = build_profile(user_id, db)
        if not profile.has_sufficient_data:
            return {
                "available": False,
                "reason": "Log 3 runs and I'll start spotting patterns — how your paces and effort are trending.",
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
    from app.contexts.runner.fitness.insight_generators import (
        acwr_insight,
        consistency_insight,
        efficiency_insight,
        fitness_insight,
        long_run_insight,
        polarization_insight,
        race_readiness_insight,
        recovery_insight,
        run_length_insight,
        variety_insight,
        volume_insight,
        volume_trend_insight,
    )

    insights = []

    # -- ACWR / Injury Risk --
    if p.acwr is not None:
        insights.append(acwr_insight(p))

    # -- Volume trend --
    insights.append(volume_insight(p))

    # -- Polarization (80/20) --
    if p.easy_pct > 0 or p.hard_pct > 0:
        insights.append(polarization_insight(p))

    # -- VDOT / Fitness --
    if p.current_vdot:
        insights.append(fitness_insight(p))

    # -- Consistency --
    insights.append(consistency_insight(p))

    # -- Efficiency --
    if p.avg_efficiency is not None:
        insights.append(efficiency_insight(p))

    # -- Long run adequacy --
    if p.longest_run_km > 0 and p.avg_weekly_km > 0:
        insights.append(long_run_insight(p))

    # -- Workout variety --
    if p.workout_type_counts:
        insights.append(variety_insight(p))

    # -- Recovery / rest days --
    insights.append(recovery_insight(p))

    # -- Volume progression --
    if p.volume_trend != "stable":
        insights.append(volume_trend_insight(p))

    # -- Average run length --
    if p.avg_run_km > 0 and p.avg_weekly_km > 0:
        insights.append(run_length_insight(p))

    # -- Race readiness (VDOT-based prediction context) --
    if p.current_vdot and p.weeks_of_data >= 4:
        insights.append(race_readiness_insight(p))

    return insights


# Backward-compatible aliases for direct imports of the old private names
_acwr_insight = None
_volume_insight = None
_polarization_insight = None
_fitness_insight = None
_consistency_insight = None
_efficiency_insight = None
_long_run_insight = None
_variety_insight = None
_recovery_insight = None
_volume_trend_insight = None
_run_length_insight = None
_race_readiness_insight = None
