"""Feedback service — orchestrates coaching feedback generation and persistence."""

import logging
from collections import defaultdict
from datetime import date as _date, datetime as _datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
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
            plan = SQLAlchemyPlanRepository(db).get_by_id(run_log.training_plan_id)
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

        # Compute and store numeric HR zone deviation on the run log
        from app.core.coaching.hr_feedback import compute_hr_zone_deviation

        hr_deviation = compute_hr_zone_deviation(run_log, planned_workout, hr_zones)
        if hr_deviation is not None:
            run_log.hr_zone_deviation = hr_deviation
            db.commit()

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

    @staticmethod
    def get_weekly_feedback_summary(
        plan_id: str, user_id: str, db: Session
    ) -> dict[int, dict]:
        """Aggregate per-run coaching feedback into weekly summaries.

        Returns {week_number: {summary, sentiment, run_count, highlights}}.
        """
        training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
        if not training_plan or not training_plan.start_date:
            return {}

        start_date = training_plan.start_date
        if isinstance(start_date, _datetime):
            start_date = start_date.date()

        runs = (
            db.query(RunLog)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.user_id == user_id,
            )
            .order_by(RunLog.date.asc())
            .all()
        )
        if not runs:
            return {}

        run_id_to_week = {}
        for run in runs:
            run_date = run.date
            if isinstance(run_date, _datetime):
                run_date = run_date.date()
            delta = (run_date - start_date).days
            if delta >= 0:
                week_num = delta // 7 + 1
                run_id_to_week[run.id] = week_num

        feedbacks = (
            db.query(RunFeedback)
            .filter(RunFeedback.run_log_id.in_(list(run_id_to_week.keys())))
            .all()
        )

        weekly_data: dict[int, dict] = {}
        for fb in feedbacks:
            week_num = run_id_to_week.get(fb.run_log_id)
            if week_num is None:
                continue

            if week_num not in weekly_data:
                weekly_data[week_num] = {
                    "sentiments": [],
                    "pace_texts": [],
                    "hr_texts": [],
                    "effort_texts": [],
                    "volume_texts": [],
                    "pattern_texts": [],
                    "run_count": 0,
                }

            weekly_data[week_num]["sentiments"].append(fb.overall_sentiment)
            weekly_data[week_num]["run_count"] += 1

            if fb.pace_feedback:
                weekly_data[week_num]["pace_texts"].append(fb.pace_feedback)
            if fb.hr_zone_feedback:
                weekly_data[week_num]["hr_texts"].append(fb.hr_zone_feedback)
            if fb.effort_feedback:
                weekly_data[week_num]["effort_texts"].append(fb.effort_feedback)
            if fb.volume_feedback:
                weekly_data[week_num]["volume_texts"].append(fb.volume_feedback)
            if fb.pattern_feedback:
                weekly_data[week_num]["pattern_texts"].append(fb.pattern_feedback)

        summaries = {}
        for week_num, data in weekly_data.items():
            summary = _build_week_summary(data, week_num)
            if summary:
                summaries[week_num] = summary

        return summaries


def _build_week_summary(data: dict, week_num: int) -> Optional[dict]:
    """Convert aggregated weekly feedback into a summary dict for the template."""
    sentiments = data["sentiments"]
    run_count = data["run_count"]
    warning_count = sentiments.count("warning")
    positive_count = sentiments.count("positive")

    dominant_sentiment = "info"
    if warning_count > positive_count and warning_count >= 2:
        dominant_sentiment = "warning"
    elif positive_count > warning_count and positive_count >= 2:
        dominant_sentiment = "positive"
    elif warning_count > 0:
        dominant_sentiment = "warning"

    highlights = []

    pace_texts = data["pace_texts"]
    if len(pace_texts) >= 2:
        fast_count = sum(1 for t in pace_texts if "fast" in t.lower() or "too quick" in t.lower())
        slow_count = sum(1 for t in pace_texts if "slow" in t.lower() or "slower" in t.lower())
        if fast_count >= 2:
            highlights.append(
                f"{fast_count} of {run_count} runs were too fast — use HR Zone 2 to pace easy runs"
            )
        elif slow_count >= 2:
            highlights.append(
                f"{slow_count} of {run_count} runs were slower than planned — check recovery status"
            )

    effort_texts = data["effort_texts"]
    if len(effort_texts) >= 2:
        hard_count = sum(
            1 for t in effort_texts
            if "too hard" in t.lower() or "too high" in t.lower()
        )
        easy_count = sum(
            1 for t in effort_texts
            if "too easy" in t.lower() or "feels light" in t.lower()
        )
        if hard_count >= 2 and not highlights:
            highlights.append(
                f"Effort consistently high ({hard_count} runs) — consider dialing back intensity"
            )
        elif easy_count >= 2 and not highlights:
            highlights.append(
                f"Workouts feeling easy ({easy_count} runs) — you may be ready to increase volume"
            )

    volume_texts = data["volume_texts"]
    if volume_texts:
        behind = sum(1 for t in volume_texts if "behind" in t.lower() or "short" in t.lower())
        ahead = sum(1 for t in volume_texts if "ahead" in t.lower() or "exceed" in t.lower())
        if behind >= 2:
            highlights.append("Weekly volume falling behind plan — try adding an easy recovery run")
        elif ahead >= 2 and not highlights:
            highlights.append("Consistently exceeding weekly volume — great execution")

    pattern_texts = data["pattern_texts"]
    if pattern_texts:
        highlights.append(pattern_texts[-1])

    if not highlights:
        if positive_count >= 2:
            highlights.append("Solid week — workouts are on target. Keep it up!")
        elif run_count >= 1:
            return None

    return {
        "week": week_num,
        "summary": highlights[0],
        "highlights": highlights[1:] if len(highlights) > 1 else [],
        "sentiment": dominant_sentiment,
        "run_count": run_count,
        "total_runs_with_feedback": len(sentiments),
    }
