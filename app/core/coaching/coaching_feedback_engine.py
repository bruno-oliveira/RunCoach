"""Coaching feedback engine.

Generates automated post-run coaching feedback by comparing
a logged run against the planned workout, HR zones, and recent patterns.

Pure: the volume/pattern history queries are performed by the caller (context
layer) and the results are passed in — see
``app.contexts.runner.fitness.coaching_data``.
"""

import logging
from typing import List, Optional, Tuple

from app.core.coaching.hr_feedback import hr_zone_feedback
from app.core.coaching.pace_feedback import pace_feedback
from app.core.coaching.pattern_analyzer import pattern_feedback
from app.core.coaching.sentiment_classifier import determine_sentiment
from app.core.coaching.volume_tracker import volume_feedback
from app.core.training.quality_scorer import calculate_quality_score

logger = logging.getLogger(__name__)


class CoachingFeedbackEngine:
    """Generate structured coaching feedback after a run is logged."""

    @classmethod
    def generate_feedback(
        cls,
        run_log,
        planned_workout,
        hr_zones: Optional[list[dict]],
        volume_inputs: Optional[Tuple[int, float, float]],
        pattern_candidates: List,
    ) -> dict:
        """Master method — calls all sub-generators and aggregates results.

        Args:
            run_log:            RunLog instance (just committed).
            planned_workout:    DailyWorkout instance, or None.
            hr_zones:           Zone list from HRZoneService, or None.
            volume_inputs:      ``(week_num, logged_km, planned_km)`` resolved by
                                the caller, or None when no plan week applies.
            pattern_candidates: Same-user runs within 45 days (newest first),
                                pre-fetched by the caller.

        Returns:
            Dict with pace_feedback, hr_zone_feedback, effort_feedback,
            volume_feedback, pattern_feedback, and overall_sentiment.
        """
        fb: dict[str, Optional[str]] = {
            "pace_feedback": pace_feedback(run_log, planned_workout),
            "hr_zone_feedback": hr_zone_feedback(run_log, planned_workout, hr_zones),
            "effort_feedback": cls._effort_feedback(run_log, planned_workout),
            "volume_feedback": (
                volume_feedback(*volume_inputs) if volume_inputs else None
            ),
            "pattern_feedback": pattern_feedback(run_log, pattern_candidates),
        }
        fb["overall_sentiment"] = determine_sentiment(fb)
        return fb

    @classmethod
    def _effort_feedback(cls, run_log, planned_workout) -> Optional[str]:
        """Wrap quality scorer output into coaching narrative."""
        if not run_log.perceived_effort:
            return None

        wtype = (
            (planned_workout.workout_type if planned_workout else None)
            or run_log.workout_type
            or "easy"
        )
        planned_pace = (
            getattr(planned_workout, "planned_pace_min_km", None)
            if planned_workout
            else None
        )

        score, label = calculate_quality_score(
            actual_effort=run_log.perceived_effort,
            actual_pace_min_km=run_log.avg_pace_min_km,
            workout_type=wtype,
            planned_pace_min_km=planned_pace,
        )

        messages = {
            "Nailed it": (
                f"Nailed it! Effort and pace were spot-on for this {wtype} session "
                f"(quality score: {score:.0f}/100)."
            ),
            "On track": (
                f"On track — solid {wtype} session (quality score: {score:.0f}/100)."
            ),
            "Too easy": (
                f"This {wtype} session felt too easy (effort {run_log.perceived_effort}/10). "
                "Push a bit harder next time to maximise training stimulus."
            ),
            "Too hard": (
                f"This {wtype} session felt too hard (effort {run_log.perceived_effort}/10). "
                "Consider backing off to prevent overtraining."
            ),
        }
        return messages.get(label, f"Quality score: {score:.0f}/100.")
