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

from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog

# Minimum distance (km) for a run to be useful for VDOT estimation.
# Very short runs produce unreliable VDOT values.
MIN_DISTANCE_KM = 2.0

# How many top VDOTs to consider when estimating current fitness.
# Using the median of the top N is robust to 1-2 outliers while
# still reflecting the user's best genuine efforts.
TOP_N_VDOTS = 3

# Number of candidate runs to fetch before applying confidence weighting.
_CANDIDATE_POOL_SIZE = 10

# Confidence multiplier by user-tagged workout type. Higher = more reliable
# VDOT indicator. Used as a fallback when the derived effort_class is unset.
_EFFORT_TYPE_WEIGHT: dict[str, float] = {
    "race": 1.5,
    "interval": 1.3,
    "tempo": 1.2,
    "hill": 1.1,
    "long": 1.0,
    "easy": 0.7,
    "recovery": 0.5,
    "rest": 0.3,
}
_DEFAULT_EFFORT_WEIGHT = 0.8

# Multiplier by derived effort_class (see effort_classifier). The classifier
# infers race/tempo/easy from pace percentile and perceived effort because
# user-tagged workout_type is unreliable in practice (Strava defaults to easy).
_EFFORT_CLASS_WEIGHT: dict[str, float] = {
    "race_effort": 1.5,
    "tempo_effort": 1.2,
    "easy_effort": 0.7,
}


def _effort_weight(effort_class: Optional[str], workout_type: Optional[str]) -> float:
    """Resolve confidence weight, preferring derived class over the user tag."""
    if effort_class and effort_class in _EFFORT_CLASS_WEIGHT:
        return _EFFORT_CLASS_WEIGHT[effort_class]
    return _EFFORT_TYPE_WEIGHT.get(workout_type or "", _DEFAULT_EFFORT_WEIGHT)

# Extreme-outlier filter for VDOT aggregation. Tukey's IQR rule alone is too
# tight on tightly clustered training paces (a 3-point real PR can fall outside
# the bound when IQR is < 1). We pair it with a ratio-against-median bound so
# the filter only triggers when a value is BOTH statistically extreme AND large
# in absolute terms -- which is what GPS / auto-pause artifacts actually look
# like (typically >= 1.4x the cluster median). Genuine PBs are rarely > 1.2x.
_OUTLIER_IQR_K = 3.0
_OUTLIER_RATIO = 1.35
_OUTLIER_MIN_SAMPLE = 5

# Endurance calibration: a runner whose flat-ground VDOT is derived from short
# fast efforts will overshoot at long distances if their training doesn't
# include long fast runs. We compare predicted-from-VDOT to actual on the
# runner's recent long runs and apply the median ratio as a multiplier.
_ENDURANCE_MIN_TARGET_KM = 10.0
_ENDURANCE_LONG_RUN_FRACTION = 0.7    # candidate runs >= 70% of target distance
_ENDURANCE_TRAIL_THRESHOLD = 20.0     # m/km gain → counts as trail, excluded
_ENDURANCE_MIN_SAMPLE = 3
_ENDURANCE_APPLY_THRESHOLD = 1.05     # ignore <5% gaps as noise
_ENDURANCE_MAX_FACTOR = 1.5           # cap so calibration can't run away


def _vdot_outlier_threshold(vdots: List[float]) -> Optional[float]:
    """Upper bound above which a VDOT is treated as an artifact, or None.

    Returns the larger of the Tukey IQR bound and a ratio-of-median bound so
    a single rule fits both tightly clustered training paces and high-variance
    samples. Returns None when the sample is too small to estimate either.
    """
    if len(vdots) < _OUTLIER_MIN_SAMPLE:
        return None
    sorted_vdots = sorted(vdots)
    n = len(sorted_vdots)
    q1 = sorted_vdots[n // 4]
    q3 = sorted_vdots[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return None
    iqr_bound = q3 + _OUTLIER_IQR_K * iqr
    ratio_bound = statistics.median(sorted_vdots) * _OUTLIER_RATIO
    return max(iqr_bound, ratio_bound)


class RacePredictorService:
    """Service for race predictions and VDOT trend analysis."""

    @staticmethod
    def calculate_vdot_from_run(run: RunLog) -> Optional[float]:
        """Calculate VDOT from any run with sufficient distance.

        Hilly runs (>20m of elevation gain per km) are skipped -- VDOT assumes
        flat ground and would otherwise underestimate the runner's true fitness.
        """
        if run.distance_km < MIN_DISTANCE_KM or run.duration_minutes <= 0:
            return None
        return VDOTCalculator.calculate_vdot(
            run.distance_km,
            int(run.duration_minutes * 60),
            elevation_gain_m=run.elevation_gain_m,
        )

    @staticmethod
    def get_vdot_history(user_id: str, weeks: int = 12, *, db: Session) -> List[Dict]:
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
    def get_best_recent_vdot(user_id: str, weeks: int = 12, *, db: Session) -> Optional[float]:
        """Get a confidence-weighted VDOT estimate from recent runs.

        Fetches a pool of top-VDOT candidates and weights each by:
        - Distance (longer runs yield more reliable VDOT estimates)
        - Workout type (race/interval > tempo > easy/recovery)
        - Perceived effort (high effort ≥ 7 boosts confidence)

        Extreme outliers (VDOT > Q3 + 3*IQR of the user's window) are dropped
        before weighting -- they're almost always GPS / auto-pause artifacts.

        The top N entries by weight are combined via weighted average.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        cutoff_date_naive = cutoff_date.replace(tzinfo=None)

        all_window_vdots = [
            v for (v,) in db.query(RunLog.vdot)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
                RunLog.date >= cutoff_date_naive,
            )
            .all()
        ]
        outlier_threshold = _vdot_outlier_threshold(all_window_vdots)

        candidate_query = db.query(
            RunLog.vdot,
            RunLog.distance_km,
            RunLog.workout_type,
            RunLog.perceived_effort,
            RunLog.effort_class,
        ).filter(
            RunLog.user_id == user_id,
            RunLog.vdot.isnot(None),
            RunLog.distance_km >= MIN_DISTANCE_KM,
            RunLog.date >= cutoff_date_naive,
        )
        if outlier_threshold is not None:
            candidate_query = candidate_query.filter(RunLog.vdot <= outlier_threshold)

        candidates = (
            candidate_query
            .order_by(RunLog.vdot.desc())
            .limit(_CANDIDATE_POOL_SIZE)
            .all()
        )

        if not candidates:
            return None

        weighted_entries = []
        for vdot, distance_km, workout_type, perceived_effort, effort_class in candidates:
            distance_weight = min(distance_km / 10.0, 1.5)
            effort_weight = _effort_weight(effort_class, workout_type)
            pe_multiplier = 1.2 if (perceived_effort and perceived_effort >= 7) else 1.0
            total_weight = distance_weight * effort_weight * pe_multiplier
            weighted_entries.append((vdot, total_weight))

        weighted_entries.sort(key=lambda x: x[1], reverse=True)
        top_entries = weighted_entries[:TOP_N_VDOTS]

        total_w = sum(w for _, w in top_entries)
        if total_w <= 0:
            return round(statistics.median([v for v, _ in top_entries]), 1)

        weighted_vdot = sum(v * w for v, w in top_entries) / total_w
        return round(weighted_vdot, 1)

    @staticmethod
    def compute_endurance_factor(
        user_id: str,
        target_distance_km: float,
        db: Session,
        weeks: int = 12,
        current_vdot: Optional[float] = None,
    ) -> float:
        """Multiplier that calibrates VDOT predictions to the runner's long-run reality.

        VDOT extrapolates from short, fast efforts to long-distance race times under
        the assumption that the runner trains across distances. For runners whose
        long runs are slower than what their VDOT predicts, this returns the median
        of (actual / predicted) on flat long runs; clamped to [1.0, MAX_FACTOR],
        applied only when ratio >= APPLY_THRESHOLD and at least MIN_SAMPLE long
        runs are available.

        Returns 1.0 (no correction) for short distances or when sample is too thin.
        """
        if target_distance_km < _ENDURANCE_MIN_TARGET_KM:
            return 1.0

        min_distance = target_distance_km * _ENDURANCE_LONG_RUN_FRACTION
        cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).replace(tzinfo=None)

        long_runs = (
            db.query(RunLog.distance_km, RunLog.duration_minutes, RunLog.elevation_gain_m)
            .filter(
                RunLog.user_id == user_id,
                RunLog.distance_km >= min_distance,
                RunLog.duration_minutes > 0,
                RunLog.date >= cutoff,
            )
            .all()
        )

        # Exclude trail runs -- elevation is handled separately by the prediction;
        # mixing them here would conflate course profile with endurance gap.
        flat_runs = [
            (d, m, e) for (d, m, e) in long_runs
            if not (e and d > 0 and e / d >= _ENDURANCE_TRAIL_THRESHOLD)
        ]
        if len(flat_runs) < _ENDURANCE_MIN_SAMPLE:
            return 1.0

        if current_vdot is None:
            current_vdot = RacePredictorService.get_best_recent_vdot(
                user_id, weeks=weeks, db=db
            )
        if not current_vdot:
            return 1.0

        ratios = []
        for distance_km, duration_minutes, elevation_gain_m in flat_runs:
            predicted_seconds = VDOTCalculator.predict_time_for_distance(
                current_vdot, distance_km, elevation_gain_m=elevation_gain_m
            )
            if not predicted_seconds:
                continue
            actual_seconds = duration_minutes * 60.0
            ratios.append(actual_seconds / predicted_seconds)

        if len(ratios) < _ENDURANCE_MIN_SAMPLE:
            return 1.0

        factor = statistics.median(ratios)
        if factor < _ENDURANCE_APPLY_THRESHOLD:
            return 1.0
        return min(factor, _ENDURANCE_MAX_FACTOR)

    @staticmethod
    def get_best_effort(user_id: str, db: Session) -> Optional[Dict]:
        """Get the best genuine effort for a user.

        Uses the median-of-top-N approach plus an IQR outlier filter on
        all-time VDOTs to avoid returning a GPS-glitch outlier as the
        user's "best effort".
        """
        all_vdots = [
            v for (v,) in db.query(RunLog.vdot)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
            )
            .all()
        ]
        outlier_threshold = _vdot_outlier_threshold(all_vdots)

        top_runs_query = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.vdot.isnot(None),
                RunLog.distance_km >= MIN_DISTANCE_KM,
            )
        )
        if outlier_threshold is not None:
            top_runs_query = top_runs_query.filter(RunLog.vdot <= outlier_threshold)

        top_runs = (
            top_runs_query
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

        trail_profile = RacePredictorService._get_user_trail_elevation_profile(user_id, db)

        predictions: Dict[str, Dict[str, Any]] = {}
        from app.core.training.vdot_calculator import STANDARD_RACE_DISTANCES
        for name, distance in STANDARD_RACE_DISTANCES.items():
            elev = None
            trail_count = None
            if name == "trail" and trail_profile["avg_m_per_km"]:
                elev = trail_profile["avg_m_per_km"] * distance
                trail_count = trail_profile["count"]

            endurance_factor = RacePredictorService.compute_endurance_factor(
                user_id, distance, db, current_vdot=current_vdot
            )
            seconds = VDOTCalculator.predict_time_for_distance(
                current_vdot, distance,
                elevation_gain_m=elev,
                trail_runs_count=trail_count,
                endurance_factor=endurance_factor,
            )
            if not seconds:
                continue
            range_data = VDOTCalculator.get_confidence_range(
                current_vdot, distance,
                elevation_gain_m=elev,
                trail_runs_count=trail_count,
                endurance_factor=endurance_factor,
            )
            predictions[name] = {
                "seconds": seconds,
                "formatted": VDOTCalculator.format_duration(seconds),
                "distance_km": distance,
                "range": {
                    "fast": VDOTCalculator.format_duration(range_data["fast"]),
                    "slow": VDOTCalculator.format_duration(range_data["slow"]),
                },
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
    def get_trail_runs_count(user_id: str, db: Session) -> int:
        """How many of the user's logged runs qualify as trail runs.

        Uses the same ≥20 m/km threshold as the VDOT calculator so the
        signal stays consistent across services. Drives the trail
        inexperience factor in race-time predictions for ultra plans.
        """
        return RacePredictorService._get_user_trail_elevation_profile(user_id, db)["count"]

    @staticmethod
    def _get_user_trail_elevation_profile(user_id: str, db: Session) -> Dict[str, Any]:
        """Compute user's typical trail elevation per km and trail run count."""
        trail_runs = (
            db.query(RunLog.distance_km, RunLog.elevation_gain_m)
            .filter(
                RunLog.user_id == user_id,
                RunLog.distance_km > 0,
                RunLog.elevation_gain_m.isnot(None),
            )
            .all()
        )
        trail_entries = [
            (d, e) for d, e in trail_runs
            if d and e and e / d >= 20.0
        ]
        if not trail_entries:
            return {"avg_m_per_km": None, "count": 0}
        count = len(trail_entries)
        avg_m_per_km = statistics.median([e / d for d, e in trail_entries])
        return {"avg_m_per_km": avg_m_per_km, "count": count}

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

            run_ts = (run.date - datetime(1970, 1, 1)).total_seconds() if run.date else 0
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
