"""Feedback service — orchestrates coaching feedback generation and persistence."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.coaching.coaching_feedback_engine import CoachingFeedbackEngine
from app.models.daily_workout import DailyWorkout
from app.models.run_feedback import RunFeedback
from app.models.run_log import RunLog
from app.models.training_plan import TrainingPlan

logger = logging.getLogger(__name__)


class FeedbackService:
    """Generate, store, and retrieve post-run coaching feedback."""

    @staticmethod
    def generate_and_store(run_log: RunLog, db: Session) -> Optional[RunFeedback]:
        """Generate coaching feedback for a run and persist it.

        This is non-fatal — callers should wrap in try/except.

        Args:
            run_log: Freshly committed RunLog instance.
            db:      SQLAlchemy session.

        Returns:
            Saved RunFeedback instance, or None if feedback couldn't be generated.
        """
        # Resolve planned workout
        planned_workout = None
        if run_log.daily_workout_id:
            planned_workout = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.id == run_log.daily_workout_id)
                .first()
            )

        # Resolve HR zones from the linked training plan
        hr_zones = None
        if run_log.training_plan_id:
            plan = (
                db.query(TrainingPlan)
                .filter(TrainingPlan.id == run_log.training_plan_id)
                .first()
            )
            if plan and plan.hr_zones_data:
                try:
                    data = plan.hr_zones_data
                    hr_zones = data.get("zones")
                except (AttributeError, TypeError):
                    pass

        # Generate feedback
        fb = CoachingFeedbackEngine.generate_feedback(
            run_log, planned_workout, hr_zones, db
        )

        # Only store if at least one field is populated
        has_content = any(
            fb.get(k) for k in (
                "pace_feedback", "hr_zone_feedback", "effort_feedback",
                "volume_feedback", "pattern_feedback",
            )
        )
        if not has_content:
            return None

        run_feedback = RunFeedback(
            run_log_id=run_log.id,
            user_id=run_log.user_id,
            pace_feedback=fb.get("pace_feedback"),
            hr_zone_feedback=fb.get("hr_zone_feedback"),
            effort_feedback=fb.get("effort_feedback"),
            volume_feedback=fb.get("volume_feedback"),
            pattern_feedback=fb.get("pattern_feedback"),
            overall_sentiment=fb.get("overall_sentiment", "info"),
            planned_workout_id=(
                planned_workout.id if planned_workout else None
            ),
        )
        db.add(run_feedback)
        db.commit()
        db.refresh(run_feedback)

        logger.info(
            f"Coaching feedback generated for run {run_log.id}: "
            f"sentiment={run_feedback.overall_sentiment}"
        )
        return run_feedback

    @staticmethod
    def get_feedback_for_run(
        run_log_id: str, db: Session
    ) -> Optional[RunFeedback]:
        """Retrieve feedback for a specific run."""
        return (
            db.query(RunFeedback)
            .filter(RunFeedback.run_log_id == run_log_id)
            .first()
        )

    @staticmethod
    def get_feedback_for_plan(
        plan_id: str, user_id: str, db: Session
    ) -> list[RunFeedback]:
        """Retrieve all feedback entries for runs logged against a plan."""
        run_ids = [
            r.id
            for r in db.query(RunLog.id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.user_id == user_id,
            )
            .all()
        ]
        if not run_ids:
            return []
        return (
            db.query(RunFeedback)
            .filter(RunFeedback.run_log_id.in_(run_ids))
            .order_by(RunFeedback.created_at.desc())
            .all()
        )
