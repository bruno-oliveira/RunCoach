"""SQLAlchemy implementation of IPlanRepository for the Plan context."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session, selectinload

from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from app.schemas import PlanRequest


class SQLAlchemyPlanRepository:
    """Persistence adapter for ``TrainingPlan``.

    Wraps SQLAlchemy ``Session`` operations behind the ``IPlanRepository``
    protocol so services in the plan context don't depend on SQLAlchemy
    directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(
        self, plan_id: str, *, include_weeks: bool = False
    ) -> Optional[TrainingPlan]:
        q = self.session.query(TrainingPlan).filter(TrainingPlan.id == plan_id)
        if include_weeks:
            q = q.options(
                selectinload(TrainingPlan.weekly_plans).selectinload(
                    WeeklyPlan.daily_workouts
                )
            )
        return q.first()

    def get_for_user(
        self, plan_id: str, user_id: str, *, include_weeks: bool = False
    ) -> Optional[TrainingPlan]:
        from sqlalchemy.orm import Query

        q: Query = self.session.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        )
        if include_weeks:
            q = q.options(
                selectinload(TrainingPlan.weekly_plans).selectinload(
                    WeeklyPlan.daily_workouts
                )
            )
        return q.first()

    def list_by_user(self, user_id: str) -> List[TrainingPlan]:
        return (
            self.session.query(TrainingPlan)
            .filter(TrainingPlan.user_id == user_id)
            .all()
        )

    def list_by_user_recent_first(self, user_id: str) -> List[TrainingPlan]:
        """List a user's plans ordered by most-recently-created first."""
        return (
            self.session.query(TrainingPlan)
            .filter(TrainingPlan.user_id == user_id)
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )

    def get_by_share_token(self, share_token: str) -> Optional[TrainingPlan]:
        return (
            self.session.query(TrainingPlan)
            .filter(TrainingPlan.share_token == share_token)
            .first()
        )

    def find_duplicate(
        self,
        user_id: str,
        request: PlanRequest,
        race_time_seconds: Optional[int],
    ) -> Optional[TrainingPlan]:
        filters = [
            TrainingPlan.user_id == user_id,
            TrainingPlan.current_weekly_km == request.current_km,
            TrainingPlan.target_distance == str(request.target_distance),
            TrainingPlan.weeks_duration == request.weeks,
            TrainingPlan.max_runs_per_week == request.max_runs_per_week,
            TrainingPlan.is_trail == request.is_trail,
            TrainingPlan.is_backyard == request.is_backyard,
        ]
        # Two backyard plans over the same projected distance can still be
        # different goals (36 and 48 loops both clamp to 163 km), so the
        # loop count has to be part of the identity.
        if request.is_backyard:
            filters.append(
                TrainingPlan.backyard_target_loops == request.backyard_target_loops
            )
            filters.append(TrainingPlan.backyard_loop_km == request.backyard_loop_km)
        resolved_training_terrain = request.resolved_training_terrain()
        if resolved_training_terrain is not None:
            filters.append(TrainingPlan.training_terrain == resolved_training_terrain)
        else:
            filters.append(TrainingPlan.training_terrain.is_(None))
        if request.target_elevation_gain_m is not None:
            filters.append(
                TrainingPlan.target_elevation_gain_m == request.target_elevation_gain_m
            )
        else:
            filters.append(TrainingPlan.target_elevation_gain_m.is_(None))
        if request.body_weight_kg is not None:
            filters.append(TrainingPlan.body_weight_kg == request.body_weight_kg)
        else:
            filters.append(TrainingPlan.body_weight_kg.is_(None))
        if request.recent_race_distance_km is not None:
            filters.append(
                TrainingPlan.recent_race_distance_km == request.recent_race_distance_km
            )
        else:
            filters.append(TrainingPlan.recent_race_distance_km.is_(None))
        if race_time_seconds is not None:
            filters.append(TrainingPlan.recent_race_time_seconds == race_time_seconds)
        else:
            filters.append(TrainingPlan.recent_race_time_seconds.is_(None))
        if request.vdot is not None:
            filters.append(TrainingPlan.vdot == request.vdot)
        else:
            filters.append(TrainingPlan.vdot.is_(None))
        return self.session.query(TrainingPlan).filter(*filters).first()

    def save(self, plan: TrainingPlan) -> None:
        self.session.add(plan)

    def delete(self, plan: TrainingPlan) -> None:
        self.session.delete(plan)

    # -- Week / workout lookups -------------------------------------------------

    def get_user_workout(
        self, daily_workout_id: str, user_id: str
    ) -> Optional[DailyWorkout]:
        """Fetch a DailyWorkout while enforcing the parent plan belongs to ``user_id``."""
        return (
            self.session.query(DailyWorkout)
            .join(WeeklyPlan, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
            .join(TrainingPlan, WeeklyPlan.training_plan_id == TrainingPlan.id)
            .filter(
                DailyWorkout.id == daily_workout_id,
                TrainingPlan.user_id == user_id,
            )
            .first()
        )

    def get_weekly_plan(self, plan_id: str, week_number: int) -> Optional[WeeklyPlan]:
        return (
            self.session.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number == week_number,
            )
            .first()
        )

    def get_daily_workout(
        self, weekly_plan_id: str, day_of_week: int
    ) -> Optional[DailyWorkout]:
        return (
            self.session.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == weekly_plan_id,
                DailyWorkout.day_of_week == day_of_week,
            )
            .first()
        )

    def list_daily_workouts(self, weekly_plan_id: str) -> List[DailyWorkout]:
        return (
            self.session.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == weekly_plan_id)
            .all()
        )

    def earliest_start_date(self, user_id: str):
        """Earliest non-null start_date across a user's plans, or None."""
        row = (
            self.session.query(TrainingPlan.start_date)
            .filter(
                TrainingPlan.user_id == user_id,
                TrainingPlan.start_date.isnot(None),
            )
            .order_by(TrainingPlan.start_date.asc())
            .first()
        )
        return row[0] if row else None


__all__ = ["SQLAlchemyPlanRepository"]
