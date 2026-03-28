"""Race predictor service for performance predictions and VDOT trend analysis.

Estimates fitness from ALL logged runs (not just race-tagged ones).  Uses the
median of the top-3 VDOTs in a recent window to be robust against GPS glitches,
auto-pause artifacts, and other data quality issues that can inflate a single
run's VDOT far beyond the user's actual fitness.
"""

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.vdot_calculator import VDOTCalculator
from app.models import RunLog

# Minimum distance (km) for a run to be useful for VDOT estimation.
# Very short runs produce unreliable VDOT values.
MIN_DISTANCE_KM = 2.0

# How many top VDOTs to consider when estimating current fitness.
# Using the median of the top N is robust to 1-2 outliers while
# still reflecting the user's best genuine efforts.
TOP_N_VDOTS = 3


class RacePredictorService:
    """Service for race predictions and VDOT trend analysis."""

    @staticmethod
    def calculate_vdot_from_run(run: RunLog) -> Optional[float]:
        """Calculate VDOT from any run with sufficient distance."""
        if run.distance_km < MIN_DISTANCE_KM or run.duration_minutes <= 0:
            return None
        return VDOTCalculator.calculate_vdot(
            run.distance_km, int(run.duration_minutes * 60)
        )

    @staticmethod
    def get_vdot_history(user_id: str, weeks: int = 12, db: Session = None) -> List[Dict]:
        """Get VDOT history from recent runs for trend analysis.

        Uses all runs with a stored VDOT (not just races).
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        cutoff_date_naive = cutoff_date.replace(tzinfo=None)

        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
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
            for run in runs
        ]

    @staticmethod
    def get_best_recent_vdot(user_id: str, weeks: int = 12, db: Session = None) -> Optional[float]:
        """Get a robust VDOT estimate from recent runs.

        Uses the median of the top N VDOTs instead of a raw MAX. This is
        resilient to GPS glitches and auto-pause artifacts that can inflate
        a single run's VDOT far above the user's actual fitness.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        cutoff_date_naive = cutoff_date.replace(tzinfo=None)

        top_runs = (
            db.query(RunLog.vdot)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
                RunLog.date >= cutoff_date_naive,
            )
            .order_by(RunLog.vdot.desc())
            .limit(TOP_N_VDOTS)
            .all()
        )

        if not top_runs:
            return None

        vdots = [row[0] for row in top_runs]
        return round(statistics.median(vdots), 1)

    @staticmethod
    def get_best_effort(user_id: str, db: Session) -> Optional[Dict]:
        """Get the best genuine effort for a user.

        Uses the median-of-top-N approach to avoid returning a GPS-glitch
        outlier as the user's "best effort".
        """
        top_runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
            )
            .order_by(RunLog.vdot.desc())
            .limit(TOP_N_VDOTS)
            .all()
        )

        if not top_runs:
            return None

        # Pick the run closest to the median VDOT of the top N
        vdots = [r.vdot for r in top_runs]
        median_vdot = statistics.median(vdots)
        best_run = min(top_runs, key=lambda r: abs(r.vdot - median_vdot))

        return {
            "date": best_run.date.isoformat() if best_run.date else None,
            "distance_km": best_run.distance_km,
            "time": VDOTCalculator.format_duration(int(best_run.duration_minutes * 60)),
            "vdot": best_run.vdot,
            "workout_type": best_run.workout_type,
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
        """Get race predictions based on user's best recent VDOT from all runs."""
        current_vdot = RacePredictorService.get_best_recent_vdot(user_id, weeks=12, db=db)

        if not current_vdot:
            return {
                "current_vdot": None,
                "vdot_trend": "stable",
                "predictions": {},
                "best_effort": None,
                "run_count": 0,
                "has_sufficient_data": False,
            }

        vdot_history = RacePredictorService.get_vdot_history(user_id, weeks=12, db=db)
        trend = RacePredictorService.calculate_vdot_trend(vdot_history)
        best_effort = RacePredictorService.get_best_effort(user_id, db=db)

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
            "best_effort": best_effort,
            "run_count": len(vdot_history),
            "has_sufficient_data": True,
        }

    @staticmethod
    def get_race_history(
        user_id: str,
        limit: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Get recent runs with predicted vs actual comparison data.

        For each run, compares the actual finish time against what the user's
        prior fitness (best VDOT before that run) predicted. Uses a sliding
        window median-of-top-N for robustness against outliers.

        Returns dict with runs (newest first), total count, and avg accuracy.
        """
        all_runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        WINDOW_WEEKS = 12

        prior_vdots: list[tuple[float, float]] = []  # (date_ts, vdot)
        enriched = []

        for run in all_runs:
            actual_seconds = int(run.duration_minutes * 60) if run.duration_minutes else None

            run_ts = run.date.timestamp() if run.date else 0
            cutoff_ts = run_ts - WINDOW_WEEKS * 7 * 86400
            window_vdots = sorted(
                [v for ts, v in prior_vdots if ts >= cutoff_ts],
                reverse=True,
            )
            if window_vdots:
                top_vdots = window_vdots[:TOP_N_VDOTS]
                rolling_vdot = statistics.median(top_vdots)
            else:
                rolling_vdot = None

            predicted_seconds = None
            if run.predicted_time_seconds:
                predicted_seconds = int(run.predicted_time_seconds)
            elif rolling_vdot:
                pred = VDOTCalculator.predict_time_for_distance(
                    rolling_vdot, run.distance_km
                )
                if pred:
                    predicted_seconds = pred

            comparison = None
            if actual_seconds and predicted_seconds:
                delta = actual_seconds - predicted_seconds
                accuracy_pct = round((1 - abs(delta) / predicted_seconds) * 100, 1)
                comparison = {
                    "predicted_seconds": predicted_seconds,
                    "predicted_formatted": VDOTCalculator.format_duration(predicted_seconds),
                    "actual_seconds": actual_seconds,
                    "actual_formatted": VDOTCalculator.format_duration(actual_seconds),
                    "delta_seconds": delta,
                    "delta_formatted": VDOTCalculator.format_duration(abs(delta)),
                    "faster_than_predicted": delta < 0,
                    "accuracy_pct": accuracy_pct,
                }

            distance_name = RacePredictorService._closest_distance_name(run.distance_km)

            enriched.append({
                "id": run.id,
                "date": run.date.isoformat() if run.date else None,
                "distance_km": run.distance_km,
                "distance_name": distance_name,
                "workout_type": run.workout_type,
                "actual_seconds": actual_seconds,
                "actual_formatted": VDOTCalculator.format_duration(actual_seconds) if actual_seconds else None,
                "avg_pace_min_km": round(run.avg_pace_min_km, 2) if run.avg_pace_min_km else None,
                "vdot": run.vdot,
                "comparison": comparison,
                "notes": run.notes,
            })

            if run.vdot:
                prior_vdots.append((run_ts, run.vdot))

        results = list(reversed(enriched))[:limit]

        with_predictions = [r for r in results if r["comparison"]]
        avg_accuracy = None
        if with_predictions:
            avg_accuracy = round(
                sum(r["comparison"]["accuracy_pct"] for r in with_predictions)
                / len(with_predictions),
                1,
            )

        return {
            "runs": results,
            "total": len(results),
            "runs_with_predictions": len(with_predictions),
            "avg_prediction_accuracy": avg_accuracy,
        }

    @staticmethod
    def _closest_distance_name(distance_km: float) -> str:
        """Find the closest standard race distance name for a given km."""
        distance_names = {
            5.0: "5K", 10.0: "10K", 21.1: "Half Marathon",
            21.0975: "Half Marathon", 30.0: "Trail",
            42.2: "Marathon", 42.195: "Marathon",
        }
        for dist, name in distance_names.items():
            if abs(distance_km - dist) < 1.0:
                return name
        return f"{distance_km:.1f}K"

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
