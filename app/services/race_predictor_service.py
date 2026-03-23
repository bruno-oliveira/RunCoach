"""Race predictor service for performance predictions and VDOT trend analysis."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.vdot_calculator import VDOTCalculator
from app.models import RunLog


class RacePredictorService:
    """Service for race predictions and VDOT trend analysis."""

    @staticmethod
    def calculate_vdot_from_run(run: RunLog) -> Optional[float]:
        """Calculate VDOT from a race-type run."""
        if run.distance_km <= 0 or run.duration_minutes <= 0:
            return None
        return VDOTCalculator.calculate_vdot(
            run.distance_km, int(run.duration_minutes * 60)
        )

    @staticmethod
    def get_vdot_history(user_id: str, weeks: int = 12, db: Session) -> List[Dict]:
        """Get VDOT history from recent race runs for trend analysis."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        cutoff_date_naive = cutoff_date.replace(tzinfo=None)

        races = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.workout_type == "race",
                RunLog.vdot.isnot(None),
                RunLog.date >= cutoff_date_naive,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        return [
            {
                "date": run.date.isoformat() if run.date else None,
                "distance_km": run.distance_km,
                "duration_minutes": run.duration_minutes,
                "vdot": run.vdot,
            }
            for run in races
        ]

    @staticmethod
    def get_best_recent_vdot(user_id: str, weeks: int = 12, db: Session) -> Optional[float]:
        """Get best VDOT from races in the last N weeks."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        cutoff_date_naive = cutoff_date.replace(tzinfo=None)

        best_race = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.workout_type == "race",
                RunLog.vdot.isnot(None),
                RunLog.date >= cutoff_date_naive,
            )
            .order_by(RunLog.vdot.desc())
            .first()
        )

        return best_race.vdot if best_race else None

    @staticmethod
    def get_last_race(user_id: str, db: Session) -> Optional[Dict]:
        """Get the most recent race for a user."""
        last_race = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.workout_type == "race",
                RunLog.vdot.isnot(None),
            )
            .order_by(RunLog.date.desc())
            .first()
        )

        if not last_race:
            return None

        return {
            "date": last_race.date.isoformat() if last_race.date else None,
            "distance_km": last_race.distance_km,
            "time": VDOTCalculator.format_duration(int(last_race.duration_minutes * 60)),
            "vdot": last_race.vdot,
        }

    @staticmethod
    def calculate_vdot_trend(vdot_history: List[Dict]) -> str:
        """Calculate VDOT trend from history.

        Returns: improving | stable | declining
        """
        if len(vdot_history) < 2:
            return "stable"

        first_vdot = vdot_history[0]["vdot"]
        last_vdot = vdot_history[-1]["vdot"]
        change = last_vdot - first_vdot

        if change > 0.5:
            return "improving"
        elif change < -0.5:
            return "declining"
        return "stable"

    @staticmethod
    def get_predictions_for_user(user_id: str, db: Session) -> Dict[str, Any]:
        """Get race predictions based on user's best recent VDOT."""
        current_vdot = RacePredictorService.get_best_recent_vdot(user_id, weeks=12, db=db)

        if not current_vdot:
            return {
                "current_vdot": None,
                "vdot_trend": "stable",
                "predictions": {},
                "last_race": None,
                "race_count": 0,
                "has_sufficient_data": False,
            }

        vdot_history = RacePredictorService.get_vdot_history(user_id, weeks=12, db=db)
        trend = RacePredictorService.calculate_vdot_trend(vdot_history)
        last_race = RacePredictorService.get_last_race(user_id, db=db)

        predictions = VDOTCalculator.predict_times(current_vdot)
        for name in predictions:
            range_data = VDOTCalculator.get_confidence_range(
                current_vdot, predictions[name]["distance_km"]
            )
            predictions[name]["range"] = {
                "fast": VDOTCalculator.format_duration(range_data["fast"]),
                "slow": VDOTCalculator.format_duration(range_data["slow"]),
            }

        return {
            "current_vdot": current_vdot,
            "vdot_trend": trend,
            "predictions": predictions,
            "last_race": last_race,
            "race_count": len(vdot_history),
            "has_sufficient_data": True,
        }

    @staticmethod
    def analyze_fitness_gap(
        current_vdot: float,
        target_distance: float,
        goal_time_seconds: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Analyze gap between current fitness and race goal."""
        predicted_time = VDOTCalculator.predict_time_for_distance(current_vdot, target_distance)

        if not predicted_time:
            return {
                "predicted_time": None,
                "goal_time": goal_time_seconds,
                "gap_seconds": 0,
                "gap_label": "Unable to calculate",
                "vdot_required": None,
                "feasible": False,
                "recommendation": "Unable to analyze gap.",
            }

        gap_seconds = goal_time_seconds - predicted_time

        if gap_seconds > 0:
            gap_label = f"{VDOTCalculator.format_duration(gap_seconds)} slower than predicted"
        elif gap_seconds < 0:
            gap_label = f"{VDOTCalculator.format_duration(abs(gap_seconds))} faster than predicted"
        else:
            gap_label = "On target"

        vdot_required = None
        feasible = False
        recommendation = ""

        if gap_seconds > 0:
            search_vdot = current_vdot
            for _ in range(100):
                test_time = VDOTCalculator.predict_time_for_distance(search_vdot, target_distance)
                if test_time and test_time <= goal_time_seconds:
                    vdot_required = round(search_vdot, 1)
                    break
                search_vdot += 0.1
                if search_vdot > 85:
                    break

            if vdot_required:
                vdot_gap = vdot_required - current_vdot
                if vdot_gap <= 2.0:
                    feasible = True
                    recommendation = (
                        f"Your goal requires VDOT {vdot_required}. "
                        "This is challenging but achievable with focused training."
                    )
                elif vdot_gap <= 4.0:
                    feasible = True
                    recommendation = (
                        f"Your goal requires VDOT {vdot_required} ({vdot_gap:.1f} units above current). "
                        "This is ambitious. Consider extending your training timeline."
                    )
                else:
                    feasible = False
                    recommendation = (
                        f"Your goal requires VDOT {vdot_required} ({vdot_gap:.1f} units above current). "
                        "This represents a significant fitness jump. Consider a more realistic intermediate goal."
                    )
        else:
            feasible = True
            recommendation = "Your goal time is faster than your current fitness predicts. Great target!"

        return {
            "predicted_time": predicted_time,
            "predicted_time_formatted": VDOTCalculator.format_duration(predicted_time),
            "goal_time": goal_time_seconds,
            "goal_time_formatted": VDOTCalculator.format_duration(goal_time_seconds),
            "gap_seconds": gap_seconds,
            "gap_label": gap_label,
            "vdot_required": vdot_required,
            "feasible": feasible,
            "recommendation": recommendation,
        }
