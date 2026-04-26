"""HR zone analyzer — aggregate HR zone data for adaptation signals."""

from typing import List, Optional, Dict, Any
from datetime import date
from collections import defaultdict

from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.utils import to_date as _to_date


class HRZoneAnalyzer:
    """Analyze HR zone adherence across a set of runs."""

    @staticmethod
    def analyze_runs(
        runs: List,
        hr_zones: list[dict],
        *,
        recency_weight_fn=None,
        today=None,
    ) -> Dict[str, Any]:
        """Analyze HR zone adherence for a list of runs.

        Args:
            runs: List of RunLog instances with avg_heart_rate
            hr_zones: Zone list from HRZoneCalculator.calculate_zones()
            recency_weight_fn: Function to weight by recency
            today: Reference date for weighting

        Returns:
            Dict with adherence metrics and trend.
        """
        if not hr_zones or not runs:
            return {
                "adherence_rate": 1.0,
                "avg_deviation": 0.0,
                "avg_abs_deviation": 0.0,
                "high_zone_run_count": 0,
                "trend": "insufficient_data",
                "per_type_adherence": {},
                "run_count": 0,
            }

        deviations = []
        weighted_dev_sum = 0.0
        weighted_abs_dev_sum = 0.0
        weight_sum = 0.0
        on_target_count = 0
        high_zone_count = 0

        per_type_on_target: Dict[str, int] = defaultdict(int)
        per_type_total: Dict[str, int] = defaultdict(int)

        for run in runs:
            if not run.avg_heart_rate:
                continue

            actual_zone = HRZoneCalculator.classify_hr(
                run.avg_heart_rate, hr_zones
            )

            target_zone = None
            if hasattr(run, 'daily_workout') and run.daily_workout:
                if hasattr(run.daily_workout, 'hr_zone_target'):
                    target_zone = run.daily_workout.hr_zone_target

            if not target_zone:
                wtype = (run.workout_type or "easy").lower()
                target_zone = HRZoneCalculator.get_workout_zone(wtype)

            deviation = actual_zone - target_zone

            run_date = _to_date(run.date) if run.date else today
            weight = recency_weight_fn(run_date) if recency_weight_fn else 1.0

            deviations.append((deviation, weight, run.workout_type or "easy"))
            weighted_dev_sum += deviation * weight
            weighted_abs_dev_sum += abs(deviation) * weight
            weight_sum += weight

            if deviation == 0:
                on_target_count += 1
                per_type_on_target[run.workout_type or "easy"] += 1

            if deviation >= 2:
                high_zone_count += 1

            per_type_total[run.workout_type or "easy"] += 1

        if weight_sum == 0:
            return {
                "adherence_rate": 1.0,
                "avg_deviation": 0.0,
                "avg_abs_deviation": 0.0,
                "high_zone_run_count": 0,
                "trend": "insufficient_data",
                "per_type_adherence": {},
                "run_count": 0,
            }

        avg_deviation = weighted_dev_sum / weight_sum
        avg_abs_deviation = weighted_abs_dev_sum / weight_sum
        adherence_rate = on_target_count / len(deviations) if deviations else 1.0

        # Compute trend
        trend = HRZoneAnalyzer._compute_trend(deviations)

        # Per-type adherence
        per_type_adherence = {}
        for wtype in per_type_total:
            total = per_type_total[wtype]
            on_target = per_type_on_target.get(wtype, 0)
            per_type_adherence[wtype] = on_target / total if total > 0 else 1.0

        return {
            "adherence_rate": round(adherence_rate, 2),
            "avg_deviation": round(avg_deviation, 2),
            "avg_abs_deviation": round(avg_abs_deviation, 2),
            "high_zone_run_count": high_zone_count,
            "trend": trend,
            "per_type_adherence": per_type_adherence,
            "run_count": len(deviations),
        }

    @staticmethod
    def _compute_trend(deviations: List[tuple]) -> str:
        """Compute HR zone deviation trend.

        Args:
            deviations: List of (deviation, weight, workout_type) tuples

        Returns:
            "improving", "degrading", "stable", or "insufficient_data"
        """
        if len(deviations) < 4:
            return "insufficient_data"

        mid_point = len(deviations) // 2
        first_half = [d[0] for d in deviations[:mid_point]]
        second_half = [d[0] for d in deviations[mid_point:]]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        diff = second_avg - first_avg

        if diff > 0.5:
            return "degrading"
        elif diff < -0.5:
            return "improving"
        return "stable"
