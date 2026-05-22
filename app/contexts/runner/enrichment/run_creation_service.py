"""Orchestrates the multi-step process of creating a run log entry.

Handles: workout ownership validation, run creation, quality scoring,
VDOT enrichment, feedback generation, and adaptive plan evaluation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.enrichment.run_enrichment_service import (
    build_race_comparison,
    enrich_vdot_and_prediction,
    run_to_response,
)
from app.contexts.runner.fitness.feedback_service import FeedbackService
from app.contexts.runner.queries import (
    TRAIL_ELEVATION_M_PER_KM,
    count_prior_trail_runs,
)
from app.core.training.quality_scorer import calculate_quality_score
from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import validate_plan_ownership
from app.models import DailyWorkout, RunLog, User
from app.schemas import RunLogCreate, RunLogResponse

logger = logging.getLogger(__name__)


class RunCreationService:
    """Composes the steps required when a user logs a new run."""

    def create_run(
        self,
        run_log: RunLogCreate,
        current_user: User,
        db: Session,
    ) -> RunLogResponse:
        validated_workout = self._validate_inputs(run_log, current_user, db)
        new_run = self._persist_run(run_log, current_user, validated_workout, db)

        vdot_recalibration = enrich_vdot_and_prediction(
            new_run,
            run_log.distance_km,
            run_log.duration_minutes,
            current_user.id,
            db,
        )
        db.commit()

        self._post_commit_feedback(new_run, db)
        auto_adjust_result = self._post_commit_adaptation(new_run, current_user, db)

        logger.info(
            "Run log created for user %s: %skm in %smin",
            current_user.id,
            run_log.distance_km,
            run_log.duration_minutes,
        )

        return self._build_response(
            new_run,
            run_log.duration_minutes,
            current_user,
            db,
            vdot_recalibration,
            auto_adjust_result,
        )

    # ------------------------------------------------------------------ steps

    def _validate_inputs(
        self,
        run_log: RunLogCreate,
        current_user: User,
        db: Session,
    ) -> Optional[DailyWorkout]:
        if run_log.training_plan_id:
            validate_plan_ownership(run_log.training_plan_id, db, current_user)

        validated_workout: Optional[DailyWorkout] = None
        if run_log.daily_workout_id:
            validated_workout = SQLAlchemyPlanRepository(db).get_user_workout(
                run_log.daily_workout_id, current_user.id
            )
            if not validated_workout:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Workout not found or access denied",
                )
        return validated_workout

    def _persist_run(
        self,
        run_log: RunLogCreate,
        current_user: User,
        validated_workout: Optional[DailyWorkout],
        db: Session,
    ) -> RunLog:
        avg_pace_min_km = run_log.duration_minutes / run_log.distance_km
        new_run = RunLog(
            user_id=current_user.id,
            training_plan_id=run_log.training_plan_id,
            daily_workout_id=run_log.daily_workout_id,
            date=run_log.date or datetime.now(timezone.utc).replace(tzinfo=None),
            distance_km=run_log.distance_km,
            duration_minutes=run_log.duration_minutes,
            avg_pace_min_km=avg_pace_min_km,
            avg_heart_rate=run_log.avg_heart_rate,
            max_heart_rate=run_log.max_heart_rate,
            avg_cadence=run_log.avg_cadence,
            elevation_gain_m=run_log.elevation_gain_m,
            notes=run_log.notes,
            workout_type=run_log.workout_type,
            perceived_effort=run_log.perceived_effort,
        )

        if validated_workout and run_log.perceived_effort:
            workout_type = (
                validated_workout.workout_type or run_log.workout_type or "easy"
            )
            score, label = calculate_quality_score(
                actual_effort=run_log.perceived_effort,
                actual_pace_min_km=avg_pace_min_km,
                workout_type=workout_type,
                planned_pace_min_km=getattr(
                    validated_workout, "planned_pace_min_km", None
                ),
            )
            new_run.effort_quality_score = score
            new_run.quality_label = label

        db.add(new_run)
        db.flush()
        return new_run

    def _post_commit_feedback(self, new_run: RunLog, db: Session) -> None:
        try:
            FeedbackService.generate_and_store(new_run, db)
        except Exception:
            logger.warning(
                "Feedback generation failed for run %s", new_run.id, exc_info=True
            )

    def _post_commit_adaptation(
        self, new_run: RunLog, current_user: User, db: Session
    ) -> Optional[dict]:
        if not new_run.training_plan_id:
            return None
        try:
            from app.contexts.plan.adaptation import AdaptationService

            service = AdaptationService()
            return service.evaluate_recommendation(
                new_run.training_plan_id,
                current_user.id,
                db,
            ) or {"action": "no_change_needed"}
        except Exception:
            logger.warning(
                "Weekly recommendation evaluation failed for run %s",
                new_run.id,
                exc_info=True,
            )
            return None

    def _build_response(
        self,
        new_run: RunLog,
        duration_minutes: float,
        current_user: User,
        db: Session,
        vdot_recalibration: Optional[dict],
        auto_adjust_result: Optional[dict],
    ) -> RunLogResponse:
        response_data = run_to_response(new_run)
        if new_run.vdot:
            elevation_map = None
            trail_count = None
            if (
                new_run.elevation_gain_m
                and new_run.distance_km > 0
                and new_run.elevation_gain_m / new_run.distance_km
                >= TRAIL_ELEVATION_M_PER_KM
            ):
                trail_count = count_prior_trail_runs(current_user.id, db)
                elevation_map = {"trail": new_run.elevation_gain_m}
            response_data.predictions = VDOTCalculator.predict_times(
                new_run.vdot,
                trail_runs_count=trail_count,
                elevation_map=elevation_map,
            )
        response_data.race_comparison = build_race_comparison(new_run, duration_minutes)
        if vdot_recalibration:
            response_data.vdot_recalibration = vdot_recalibration
        if auto_adjust_result:
            response_data.auto_adjust = auto_adjust_result
        return response_data
