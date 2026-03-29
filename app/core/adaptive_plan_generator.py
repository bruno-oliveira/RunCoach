"""Adaptive training plan generator based on user performance data."""

import copy
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import RunLog, User, TrainingPlan
from app.core.plan_generator import TrainingPlanGenerator
from app.schemas import RunLogResponse

logger = logging.getLogger(__name__)


class AdaptivePlanGenerator:
    """Generates adaptive training plans based on user's actual running data."""

    def __init__(self):
        self.base_generator = TrainingPlanGenerator()

    def calculate_current_fitness_metrics(self, user_id: str, db: Session) -> Dict[str, Any]:
        """
        Calculate user's current fitness metrics from their run logs.

        Returns:
            Dict containing:
                - avg_weekly_km: Average weekly distance
                - current_pace: Current average pace (min/km)
                - avg_heart_rate: Average heart rate
                - improvement_trend: Velocity improvement rate
                - fitness_score: Overall fitness score (0-100)
                - preferred_workout_types: Most frequent workout types
        """
        from sqlalchemy import func, desc

        # Get runs from the last 8 weeks
        eight_weeks_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=8)
        recent_runs = (
            db.query(RunLog)
            .filter(RunLog.user_id == user_id, RunLog.date >= eight_weeks_ago)
            .order_by(RunLog.date.desc())
            .all()
        )

        if not recent_runs:
            logger.warning(f"No run logs found for user {user_id}")
            return {
                "avg_weekly_km": 0,
                "current_pace": None,
                "avg_heart_rate": None,
                "improvement_trend": 0,
                "fitness_score": 0,
                "preferred_workout_types": [],
                "total_runs_last_8_weeks": 0,
            }

        # Calculate average weekly distance
        total_distance = sum(run.distance_km for run in recent_runs)
        weeks_span = max(1, min(8, (recent_runs[0].date - recent_runs[-1].date).days / 7))
        avg_weekly_km = total_distance / weeks_span

        # Calculate current pace
        runs_with_pace = [run for run in recent_runs if run.avg_pace_min_km is not None]
        current_pace = sum(run.avg_pace_min_km for run in runs_with_pace) / len(runs_with_pace) if runs_with_pace else None

        # Calculate average heart rate
        runs_with_hr = [run for run in recent_runs if run.avg_heart_rate is not None]
        avg_heart_rate = sum(run.avg_heart_rate for run in runs_with_hr) / len(runs_with_hr) if runs_with_hr else None

        # Calculate improvement trend (pace improvement over time)
        if len(recent_runs) >= 2:
            first_pace = recent_runs[-1].avg_pace_min_km
            last_pace = recent_runs[0].avg_pace_min_km
            if first_pace and last_pace:
                improvement_trend = (first_pace - last_pace) / first_pace * 100  # Percentage improvement
            else:
                improvement_trend = 0
        else:
            improvement_trend = 0

        # Calculate fitness score (0-100) based on multiple factors
        fitness_score = self._calculate_fitness_score(
            avg_weekly_km, current_pace, improvement_trend, len(recent_runs)
        )

        # Find preferred workout types
        workout_counts = {}
        for run in recent_runs:
            if run.workout_type:
                workout_counts[run.workout_type] = workout_counts.get(run.workout_type, 0) + 1

        preferred_workout_types = sorted(
            workout_counts.items(), key=lambda x: x[1], reverse=True
        )[:3]
        preferred_workout_types = [wt[0] for wt in preferred_workout_types]

        return {
            "avg_weekly_km": round(avg_weekly_km, 1),
            "current_pace": round(current_pace, 2) if current_pace else None,
            "avg_heart_rate": int(avg_heart_rate) if avg_heart_rate else None,
            "improvement_trend": round(improvement_trend, 2),
            "fitness_score": fitness_score,
            "preferred_workout_types": preferred_workout_types,
            "total_runs_last_8_weeks": len(recent_runs),
        }

    # Fitness score component weights and thresholds
    VOLUME_MAX_POINTS = 40
    VOLUME_FULL_KM_PER_WEEK = 50
    PACE_MAX_POINTS = 30
    PACE_ELITE_THRESHOLD = 5.0       # min/km — elite/sub-elite
    PACE_GOOD_THRESHOLD = 6.0        # min/km — good recreational
    PACE_DEVELOPING_THRESHOLD = 7.0  # min/km — developing runner
    PACE_SLOW_THRESHOLD = 8.0        # min/km — beginning runner
    IMPROVEMENT_MAX_POINTS = 20
    IMPROVEMENT_FULL_PCT = 10        # 10% improvement = full points
    CONSISTENCY_MAX_POINTS = 10
    CONSISTENCY_FULL_RUNS = 20       # 20 runs in 8 weeks = full points

    def _calculate_fitness_score(
        self, weekly_km: float, pace: Optional[float], improvement: float, run_count: int
    ) -> int:
        """Calculate a fitness score from 0-100.

        Uses percentile-based pace scoring so recreational runners (5:00-8:00 min/km)
        receive realistic scores instead of being unfairly penalised against a 4:00/km elite
        baseline.
        """
        score = 0

        # Volume component
        volume_score = min(self.VOLUME_MAX_POINTS, (weekly_km / self.VOLUME_FULL_KM_PER_WEEK) * self.VOLUME_MAX_POINTS)
        score += volume_score

        # Pace component: percentile-based ranges
        if pace:
            if pace < self.PACE_ELITE_THRESHOLD:
                pace_score = float(self.PACE_MAX_POINTS)
            elif pace < self.PACE_GOOD_THRESHOLD:
                pace_score = 20.0 + (self.PACE_GOOD_THRESHOLD - pace) * 10.0
            elif pace < self.PACE_DEVELOPING_THRESHOLD:
                pace_score = 12.0 + (self.PACE_DEVELOPING_THRESHOLD - pace) * 8.0
            elif pace < self.PACE_SLOW_THRESHOLD:
                pace_score = 5.0 + (self.PACE_SLOW_THRESHOLD - pace) * 7.0
            else:
                pace_score = max(0.0, 5.0 - (pace - self.PACE_SLOW_THRESHOLD) * 2.5)
            score += pace_score

        # Improvement component
        improvement_score = min(self.IMPROVEMENT_MAX_POINTS, max(0, improvement * (self.IMPROVEMENT_MAX_POINTS / self.IMPROVEMENT_FULL_PCT)))
        score += improvement_score

        # Consistency component
        consistency_score = min(self.CONSISTENCY_MAX_POINTS, (run_count / self.CONSISTENCY_FULL_RUNS) * self.CONSISTENCY_MAX_POINTS)
        score += consistency_score

        return int(min(100, max(0, score)))

    def generate_adaptive_plan(
        self,
        user_id: str,
        target_distance: float,
        weeks: int,
        max_runs_per_week: int,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        Generate an adaptive training plan based on user's performance data.

        Args:
            user_id: User ID
            target_distance: Target race distance in km
            weeks: Training duration in weeks
            max_runs_per_week: Maximum runs per week
            db: Database session

        Returns:
            List of weekly training plans with adaptive adjustments
        """
        # Get user's current fitness metrics
        metrics = self.calculate_current_fitness_metrics(user_id, db)

        logger.info(f"Generating adaptive plan for user {user_id}")
        logger.info(f"Current metrics: {metrics}")

        # Calculate adaptive starting point
        if metrics["avg_weekly_km"] > 0:
            current_km = metrics["avg_weekly_km"]
        else:
            # Fallback to default if no data
            current_km = 10.0

        # Generate base plan using the existing generator
        base_plan = self.base_generator.generate_plan(
            current_km=current_km,
            target_distance=target_distance,
            weeks=weeks,
            max_runs_per_week=max_runs_per_week,
        )

        # Apply adaptive adjustments
        adaptive_plan = self._apply_adaptive_adjustments(
            base_plan, metrics, target_distance, user_id, db
        )

        return adaptive_plan

    def _apply_adaptive_adjustments(
        self,
        base_plan: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        target_distance: float,
        user_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Apply targeted adaptive adjustments based on specific fitness dimensions.

        Instead of a single fitness multiplier, adjustments are applied per-dimension:
        - Volume: scaled by how close avg_weekly_km is to plan expectations
        - Intensity: quality workouts annotated based on improvement trend
        - HR zones: relative to estimated max HR (not absolute thresholds)
        """
        adaptive_plan = []

        # Estimate max HR from data (highest recorded) or use age-based fallback
        est_max_hr = self._estimate_max_hr(user_id, db, metrics)

        for week in base_plan:
            adjusted_week = copy.deepcopy(week)

            # ── Volume adjustment (capped at ±15% of base plan) ───────────
            if metrics["avg_weekly_km"] > 0:
                plan_week_km = week["total_km"]
                # If runner is already exceeding the plan's expectation, nudge up slightly
                # If below, keep the plan conservative (don't reduce further)
                ratio = metrics["avg_weekly_km"] / max(plan_week_km, 1)
                if ratio > 1.15:
                    volume_factor = 1.10  # runner is well ahead — modest bump
                elif ratio > 0.9:
                    volume_factor = 1.0   # on track — no change
                else:
                    volume_factor = 0.95  # behind — slight ease, let them build
                adjusted_week["total_km"] = round(plan_week_km * volume_factor, 1)

            # ── Intensity annotations (deterministic, not random) ─────────
            if metrics["improvement_trend"] > 5:
                # Rapidly improving: annotate long runs with progressive finish
                for workout in adjusted_week["daily_workouts"]:
                    if workout["type"] == "long":
                        workout["description"] = workout.get("description", "") + (
                            " (You're improving fast — try a progressive finish: "
                            "last 20% at a comfortably hard effort)"
                        )
            elif metrics["improvement_trend"] < -2:
                # Declining: ease quality sessions
                for workout in adjusted_week["daily_workouts"]:
                    if workout["type"] in ["interval", "tempo"]:
                        workout["description"] = workout.get("description", "") + (
                            " (Recent trend suggests fatigue — prioritise form over speed, "
                            "cut intervals short if RPE exceeds 8)"
                        )

            # ── HR-relative tips (using % of max HR, not absolute values) ─
            tips = adjusted_week.setdefault("training_tips", [])
            if metrics["avg_heart_rate"] and est_max_hr:
                hr_pct = metrics["avg_heart_rate"] / est_max_hr
                if hr_pct > 0.82:
                    tips.append(
                        f"Your avg HR ({metrics['avg_heart_rate']} bpm, ~{hr_pct:.0%} of est. max) "
                        "suggests most runs are too hard. Aim for easy runs below 75% of max HR."
                    )
                elif hr_pct < 0.68:
                    tips.append(
                        f"Your avg HR ({metrics['avg_heart_rate']} bpm, ~{hr_pct:.0%} of est. max) "
                        "shows a strong aerobic base. You can handle more quality sessions."
                    )

            adaptive_plan.append(adjusted_week)

        # Append improvement tip only to the first week
        if metrics["improvement_trend"] > 0 and adaptive_plan:
            adaptive_plan[0].setdefault("training_tips", []).append(
                f"You're improving {metrics['improvement_trend']:.1f}% — keep up the great work!"
            )

        return adaptive_plan

    def _estimate_max_hr(self, user_id: str, db: Session, metrics: Dict[str, Any]) -> Optional[int]:
        """Estimate max HR from the user's highest recorded HR, or fall back to 200."""
        from sqlalchemy import func

        result = db.query(func.max(RunLog.max_heart_rate)).filter(
            RunLog.user_id == user_id,
            RunLog.max_heart_rate.isnot(None),
        ).scalar()

        if result and result > 140:
            return int(result)
        # Fallback: conservative estimate (avoids age-based assumptions)
        return 200

    def analyze_performance_gaps(self, user_id: str, target_distance: float, db: Session) -> Dict[str, Any]:
        """
        Analyze gaps between current performance and race requirements.

        Returns:
            Dict containing:
                - mileage_gap: Additional weekly km needed
                - pace_goal: Target race pace based on current data
                - key_weaknesses: Areas needing improvement
                - recommendations: Specific recommendations
        """
        metrics = self.calculate_current_fitness_metrics(user_id, db)

        # Define target paces for each distance
        target_paces = {
            5.0: 5.5,   # 5K: 5:30 min/km
            10.0: 5.8,  # 10K: 5:48 min/km
            21.1: 6.2,  # Half: 6:12 min/km
            30.0: 6.8,  # 30K/Trail: 6:48 min/km
            42.2: 7.2,  # Marathon: 7:12 min/km
        }

        target_pace = target_paces.get(target_distance, 6.0)
        required_weekly_km = {
            5.0: 25,
            10.0: 30,
            21.1: 45,
            30.0: 50,
            42.2: 60,
        }.get(target_distance, 30)

        mileage_gap = max(0, required_weekly_km - metrics["avg_weekly_km"])

        key_weaknesses = []
        recommendations = []

        if metrics["avg_weekly_km"] < required_weekly_km * 0.7:
            key_weaknesses.append("Insufficient weekly volume")
            recommendations.append(
                f"Increase weekly mileage gradually by 10% until reaching {required_weekly_km}km/week"
            )

        if metrics["current_pace"] and metrics["current_pace"] > target_pace * 1.15:
            key_weaknesses.append("Pace significantly above target")
            recommendations.append("Include more tempo runs and intervals to improve speed")

        if metrics["avg_heart_rate"] and metrics["avg_heart_rate"] > 165:
            key_weaknesses.append("High heart rate at current pace")
            recommendations.append("Focus on building aerobic base with more easy running")

        if metrics["improvement_trend"] < 0:
            key_weaknesses.append("Declining performance trend")
            recommendations.append("Review recovery strategies and consider a lighter week")

        return {
            "current_metrics": metrics,
            "target_pace": target_pace,
            "target_weekly_km": required_weekly_km,
            "mileage_gap": round(mileage_gap, 1),
            "key_weaknesses": key_weaknesses,
            "recommendations": recommendations,
        }

    def get_training_suggestions(
        self, user_id: str, db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get personalized training suggestions based on recent performance.

        Returns:
            List of suggestions with priority and description
        """
        metrics = self.calculate_current_fitness_metrics(user_id, db)
        suggestions = []

        # Volume-based suggestions
        if metrics["avg_weekly_km"] < 20:
            suggestions.append({
                "priority": "high",
                "category": "volume",
                "suggestion": "Build your aerobic base with consistent easy runs",
                "action": "Aim for 3-4 runs per week, gradually increasing distance",
            })
        elif metrics["avg_weekly_km"] > 60:
            suggestions.append({
                "priority": "medium",
                "category": "recovery",
                "suggestion": "Ensure adequate recovery at high volumes",
                "action": "Include regular rest days and easy recovery runs",
            })

        # Pace-based suggestions
        if metrics["current_pace"] and metrics["current_pace"] > 7.0:
            suggestions.append({
                "priority": "high",
                "category": "speed",
                "suggestion": "Incorporate speed work to improve pace",
                "action": "Add strides after easy runs and one weekly tempo session",
            })

        # Improvement-based suggestions
        if metrics["improvement_trend"] > 5:
            suggestions.append({
                "priority": "low",
                "category": "maintenance",
                "suggestion": "Great progress! Maintain current training approach",
                "action": "Continue with your current plan, monitor for signs of overtraining",
            })
        elif metrics["improvement_trend"] < -3:
            suggestions.append({
                "priority": "high",
                "category": "recovery",
                "suggestion": "Performance declining - focus on recovery",
                "action": "Reduce volume by 20% for 1-2 weeks, prioritize sleep and nutrition",
            })

        # Consistency-based suggestions
        if metrics["total_runs_last_8_weeks"] < 10:
            suggestions.append({
                "priority": "high",
                "category": "consistency",
                "suggestion": "Build training consistency",
                "action": "Set a goal to run at least 3 times per week consistently",
            })

        # Workout type preferences
        if metrics["preferred_workout_types"]:
            preferred = metrics["preferred_workout_types"][0]
            if preferred == "easy":
                suggestions.append({
                    "priority": "medium",
                    "category": "balance",
                    "suggestion": "Consider adding more quality workouts",
                    "action": "Include one tempo or interval session per week",
                })

        return suggestions[:5]  # Return top 5 suggestions
