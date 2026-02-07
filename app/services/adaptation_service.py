"""Service for adapting training plans based on performance data."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan

logger = logging.getLogger(__name__)


class AdaptationService:
    """Service for analyzing run performance and adapting training plans."""

    def __init__(self):
        self.EFFORT_THRESHOLDS = {
            "too_easy": 3,  # Effort <= 3 is too easy
            "easy": 5,      # Effort <= 5 is manageable
            "hard": 7,      # Effort >= 7 is challenging
            "too_hard": 9,  # Effort >= 9 is too difficult
        }
        
        self.PACE_VARIANCE_THRESHOLD = 0.15  # 15% variance from expected
        self.MIN_RUNS_FOR_ADAPTATION = 3  # Need at least 3 runs to adapt

    def analyze_performance(
        self, 
        training_plan_id: str, 
        db: Session
    ) -> Dict[str, any]:
        """
        Analyze user's performance on a training plan.
        
        Returns metrics about adherence, effort levels, and pace.
        """
        # Get all logged runs for this plan
        runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == training_plan_id)
            .order_by(RunLog.date)
            .all()
        )
        
        if not runs:
            return {
                "total_runs": 0,
                "adherence_rate": 0.0,
                "avg_effort": None,
                "effort_trend": "insufficient_data",
                "pace_consistency": None,
                "recommendations": ["Log more runs to get personalized feedback"],
            }
        
        # Calculate metrics
        total_logged = len(runs)
        
        # Get planned workouts count (excluding rest days)
        planned_workouts = (
            db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == training_plan_id,
                DailyWorkout.workout_type != "rest"
            )
            .count()
        )
        
        adherence_rate = (total_logged / planned_workouts * 100) if planned_workouts > 0 else 0
        
        # Effort analysis
        efforts = [r.perceived_effort for r in runs if r.perceived_effort is not None]
        avg_effort = sum(efforts) / len(efforts) if efforts else None
        
        # Analyze effort trend (last 5 vs first 5 runs)
        effort_trend = self._analyze_effort_trend(efforts)
        
        # Pace consistency
        paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km]
        pace_consistency = self._calculate_pace_consistency(paces) if paces else None
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            avg_effort, effort_trend, adherence_rate, pace_consistency
        )
        
        return {
            "total_runs": total_logged,
            "planned_workouts": planned_workouts,
            "adherence_rate": round(adherence_rate, 1),
            "avg_effort": round(avg_effort, 1) if avg_effort else None,
            "effort_trend": effort_trend,
            "pace_consistency": pace_consistency,
            "recommendations": recommendations,
        }

    def _analyze_effort_trend(self, efforts: List[int]) -> str:
        """Analyze if effort is increasing, decreasing, or stable."""
        if len(efforts) < 4:
            return "insufficient_data"
        
        mid_point = len(efforts) // 2
        first_half_avg = sum(efforts[:mid_point]) / mid_point
        second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
        
        diff = second_half_avg - first_half_avg
        
        if diff > 1.0:
            return "increasing"  # Getting harder - may need to back off
        elif diff < -1.0:
            return "decreasing"  # Getting easier - adapting well
        else:
            return "stable"

    def _calculate_pace_consistency(self, paces: List[float]) -> float:
        """Calculate coefficient of variation for pace."""
        if len(paces) < 2:
            return None
        
        avg_pace = sum(paces) / len(paces)
        variance = sum((p - avg_pace) ** 2 for p in paces) / len(paces)
        std_dev = variance ** 0.5
        
        # Coefficient of variation (lower is more consistent)
        cv = (std_dev / avg_pace) * 100 if avg_pace > 0 else 100
        return round(cv, 2)

    def _generate_recommendations(
        self,
        avg_effort: Optional[float],
        effort_trend: str,
        adherence_rate: float,
        pace_consistency: Optional[float],
    ) -> List[str]:
        """Generate actionable recommendations based on performance."""
        recommendations = []
        
        # Adherence recommendations
        if adherence_rate < 50:
            recommendations.append("Try to complete more planned workouts for better results")
        elif adherence_rate > 90:
            recommendations.append("Excellent adherence! Keep up the great work!")
        
        # Effort recommendations
        if avg_effort:
            if avg_effort <= self.EFFORT_THRESHOLDS["too_easy"]:
                recommendations.append("Your runs feel too easy - consider increasing intensity or distance")
            elif avg_effort >= self.EFFORT_THRESHOLDS["too_hard"]:
                recommendations.append("You're pushing too hard - consider reducing intensity to avoid burnout")
            elif self.EFFORT_THRESHOLDS["easy"] < avg_effort < self.EFFORT_THRESHOLDS["hard"]:
                recommendations.append("Your effort levels look optimal!")
        
        # Trend recommendations
        if effort_trend == "increasing":
            recommendations.append("Fatigue may be building - ensure adequate recovery")
        elif effort_trend == "decreasing":
            recommendations.append("You're adapting well to the training load!")
        
        # Pace consistency
        if pace_consistency:
            if pace_consistency < 5:
                recommendations.append("Your pacing is very consistent - great control!")
            elif pace_consistency > 15:
                recommendations.append("Work on more consistent pacing across runs")
        
        return recommendations if recommendations else ["Keep logging runs for personalized insights"]

    def should_adapt_plan(
        self,
        training_plan_id: str,
        db: Session,
    ) -> Tuple[bool, str]:
        """
        Determine if a plan should be adapted based on performance.
        
        Returns (should_adapt: bool, reason: str)
        """
        analysis = self.analyze_performance(training_plan_id, db)
        
        if analysis["total_runs"] < self.MIN_RUNS_FOR_ADAPTATION:
            return False, "Not enough data yet"
        
        avg_effort = analysis.get("avg_effort")
        effort_trend = analysis.get("effort_trend")
        adherence = analysis.get("adherence_rate", 0)
        
        # Adaptation triggers
        if avg_effort and avg_effort >= self.EFFORT_THRESHOLDS["too_hard"]:
            return True, "Effort consistently too high - reducing load"
        
        if avg_effort and avg_effort <= self.EFFORT_THRESHOLDS["too_easy"]:
            return True, "Effort consistently too low - increasing challenge"
        
        if effort_trend == "increasing" and avg_effort and avg_effort > 7:
            return True, "Fatigue building - adding recovery"
        
        if adherence < 60:
            return True, "Low adherence - plan may be too aggressive"
        
        return False, "No adaptation needed - plan is appropriate"

    def adapt_future_weeks(
        self,
        training_plan_id: str,
        db: Session,
        current_week: int,
    ) -> Dict[str, any]:
        """
        Adapt future weeks of a training plan based on performance.
        
        Only modifies weeks that haven't been completed yet.
        """
        should_adapt, reason = self.should_adapt_plan(training_plan_id, db)
        
        if not should_adapt:
            return {
                "adapted": False,
                "reason": reason,
                "changes": []
            }
        
        analysis = self.analyze_performance(training_plan_id, db)
        avg_effort = analysis.get("avg_effort")
        
        # Determine adjustment factor
        if avg_effort and avg_effort >= self.EFFORT_THRESHOLDS["too_hard"]:
            distance_multiplier = 0.9  # Reduce by 10%
            adjustment_type = "reduction"
        elif avg_effort and avg_effort <= self.EFFORT_THRESHOLDS["too_easy"]:
            distance_multiplier = 1.1  # Increase by 10%
            adjustment_type = "increase"
        else:
            distance_multiplier = 0.95  # Conservative reduction
            adjustment_type = "recovery"
        
        # Get future weeks (current week + 1 onwards)
        future_weeks = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == training_plan_id,
                WeeklyPlan.week_number > current_week
            )
            .all()
        )
        
        changes = []
        for week in future_weeks:
            # Get workouts for this week
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == week.id)
                .all()
            )
            
            week_changes = []
            for workout in workouts:
                if workout.workout_type != "rest" and workout.distance_km > 0:
                    old_distance = workout.distance_km
                    new_distance = round(old_distance * distance_multiplier, 1)
                    
                    workout.distance_km = new_distance
                    workout.notes = f"Adapted: {workout.notes or ''} (adjusted from {old_distance}km based on performance)"
                    
                    week_changes.append({
                        "day": workout.day_of_week,
                        "workout_type": workout.workout_type,
                        "old_distance": old_distance,
                        "new_distance": new_distance,
                    })
            
            if week_changes:
                # Update weekly total
                new_total = sum(w.distance_km for w in workouts if w.distance_km)
                week.total_km = new_total
                
                changes.append({
                    "week": week.week_number,
                    "workouts_adjusted": week_changes,
                    "new_total_km": round(new_total, 1),
                })
        
        db.commit()

        return {
            "adapted": True,
            "reason": reason,
            "adjustment_type": adjustment_type,
            "changes": changes,
        }

    def detect_skipped_workouts(
        self,
        plan_id: str,
        db: Session,
    ) -> int:
        """
        Detect how many planned workouts have been skipped up to today.

        A workout is considered skipped if:
        - It's not a rest day
        - The workout date is in the past (including today)
        - No RunLog exists for this workout (either directly or via date matching)

        Args:
            plan_id: Training plan ID
            db: Database session

        Returns:
            Count of skipped workouts
        """
        from app.models import DailyWorkout, WeeklyPlan, RunLog, TrainingPlan

        # Get training plan to calculate dates
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id
        ).first()

        if not training_plan:
            return 0

        plan_start_date = training_plan.created_at.date()
        today = datetime.utcnow().date()

        # Get all daily workouts with their week numbers
        daily_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type != "rest"
            )
            .all()
        )

        skipped_count = 0

        for workout, week_number in daily_workouts:
            # Calculate workout date
            workout_date = plan_start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1)
            )

            # Only consider workouts up to today
            if workout_date > today:
                continue

            # Check if run log exists for this workout
            run_log_exists = db.query(RunLog).filter(
                RunLog.daily_workout_id == workout.id
            ).first()

            if not run_log_exists:
                skipped_count += 1
                logger.debug(
                    f"Skipped workout detected: Week {week_number}, "
                    f"Day {workout.day_of_week} ({workout_date})"
                )

        return skipped_count
