"""Service for adapting training plans based on performance data."""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan, User

logger = logging.getLogger(__name__)

# Regex to strip legacy adaptation/recalibration notes from workout notes
_ANNOTATION_RE = re.compile(r"\s*\((Adapted|Recalibrated|Adjusted):[^)]*\)")


def _to_date(value) -> Optional[datetime]:
    """Coerce a date or datetime to a plain date object."""
    if value is None:
        return None
    if hasattr(value, "date") and callable(value.date):
        return value.date()
    return value


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

    # ------------------------------------------------------------------
    # Baseline backfill
    # ------------------------------------------------------------------

    @staticmethod
    def _backfill_baselines(
        training_plan: "TrainingPlan",
        db: Session,
    ) -> None:
        """Ensure every DailyWorkout has a baseline_distance_km.

        For plans created before the column existed, sets baseline to
        current distance_km.
        """
        workouts_needing_backfill = (
            db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == training_plan.id,
                DailyWorkout.baseline_distance_km.is_(None),
                DailyWorkout.distance_km.isnot(None),
                DailyWorkout.distance_km > 0,
            )
            .all()
        )
        if not workouts_needing_backfill:
            return

        for workout in workouts_needing_backfill:
            workout.baseline_distance_km = workout.distance_km
        db.flush()

    @staticmethod
    def _parse_plan_data_lookups(
        training_plan: "TrainingPlan",
    ) -> tuple[list[dict], dict[int, dict], dict[tuple[int, int], dict]]:
        """Parse plan_data JSON and build lookup dicts for plan syncing.

        Returns (plan_data, pd_week, pd_workout) where:
        - plan_data: the parsed list of week dicts
        - pd_week: {week_number: week_dict}
        - pd_workout: {(week_number, day): workout_dict}
        """
        plan_data = json.loads(training_plan.plan_data)
        pd_week: dict[int, dict] = {}
        pd_workout: dict[tuple[int, int], dict] = {}
        for wk in plan_data:
            pd_week[wk["week"]] = wk
            for wo in wk.get("daily_workouts", []):
                pd_workout[(wk["week"], wo["day"])] = wo
        return plan_data, pd_week, pd_workout

    @staticmethod
    def _batch_workouts_by_week(
        week_ids: list[str],
        db: Session,
    ) -> dict[str, list["DailyWorkout"]]:
        """Fetch all DailyWorkouts for the given WeeklyPlan IDs in one query.

        Returns {weekly_plan_id: [DailyWorkout, ...]}.
        """
        all_workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id.in_(week_ids))
            .all()
        )
        grouped: dict[str, list] = defaultdict(list)
        for w in all_workouts:
            grouped[w.weekly_plan_id].append(w)
        return grouped

    # ------------------------------------------------------------------
    # Performance analysis (read-only)
    # ------------------------------------------------------------------

    def analyze_performance(
        self,
        training_plan_id: str,
        db: Session
    ) -> Dict[str, any]:
        """Analyze user's performance on a training plan.

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

        # Get planned workouts count (excluding rest and recovery days)
        planned_workouts = (
            db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == training_plan_id,
                DailyWorkout.workout_type.notin_(["rest", "recovery"]),
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

    # ------------------------------------------------------------------
    # Skipped workout detection
    # ------------------------------------------------------------------

    def detect_skipped_workouts(
        self,
        plan_id: str,
        db: Session,
    ) -> Dict[str, int]:
        """Detect skipped and rescheduled workouts up to today.

        A workout is "unlinked" if no RunLog references it directly.
        Among unlinked workouts:
        - "rescheduled" = that week's total volume was still met (>= 80%)
        - "skipped" = truly missed (week volume not met)

        Returns:
            Dict with ``skipped`` and ``rescheduled`` counts.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id
        ).first()

        if not training_plan:
            return {"skipped": 0, "rescheduled": 0}

        sd = training_plan.start_date or training_plan.created_at
        plan_start_date = _to_date(sd)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()

        daily_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type.notin_(["rest", "recovery"]),
            )
            .all()
        )

        # Batch: fetch all linked workout IDs in one query
        linked_workout_ids = set(
            row[0] for row in
            db.query(RunLog.daily_workout_id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.isnot(None),
            )
            .all()
        )

        # Group unlinked past workouts by week
        unlinked_by_week: Dict[int, int] = defaultdict(int)

        for workout, week_number in daily_workouts:
            workout_date = plan_start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1)
            )
            if workout_date > today:
                continue
            if workout.id not in linked_workout_ids:
                unlinked_by_week[week_number] += 1

        if not unlinked_by_week:
            return {"skipped": 0, "rescheduled": 0}

        # Batch: fetch all run volumes for this plan in one query, bucket in Python
        all_plan_runs = (
            db.query(RunLog.date, RunLog.distance_km)
            .filter(RunLog.training_plan_id == plan_id)
            .all()
        )
        weekly_actual_km: Dict[int, float] = defaultdict(float)
        for run_date, dist in all_plan_runs:
            rd = _to_date(run_date)
            if rd and plan_start_date:
                delta = (rd - plan_start_date).days
                if delta >= 0:
                    wk = delta // 7 + 1
                    weekly_actual_km[wk] += dist or 0.0

        weekly_plans = {
            wp.week_number: wp
            for wp in db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        }

        skipped = 0
        rescheduled = 0

        for week_num, unlinked_count in unlinked_by_week.items():
            wp = weekly_plans.get(week_num)
            if not wp:
                skipped += unlinked_count
                continue

            planned_km = wp.total_km or 0
            actual_km = weekly_actual_km.get(week_num, 0.0)
            if planned_km > 0 and actual_km >= planned_km * 0.8:
                rescheduled += unlinked_count
            else:
                skipped += unlinked_count

        return {"skipped": skipped, "rescheduled": rescheduled}

    # ------------------------------------------------------------------
    # Retroactive run-to-plan mapping
    # ------------------------------------------------------------------

    def map_runs_to_plan(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
        *,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """Match unlinked RunLog entries to plan DailyWorkouts by week.

        Assigns every run between the plan start_date and today to its
        corresponding training week, then greedily matches runs to the best
        available workout within that week.  Runs with no available workout
        are linked as volume-only.  This ensures no run in the plan period
        goes unmapped.

        Args:
            plan_id: Training plan ID.
            user_id: User ID.
            db: Database session.
            dry_run: If True, return proposed mappings without persisting.

        Returns:
            Dict with ``mapped`` count and ``proposals`` list.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"mapped": 0, "proposals": [], "error": "Plan not found"}

        if not training_plan.start_date:
            return {"mapped": 0, "proposals": [], "error": "Plan has no start date. Set a start date first."}

        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        num_weeks = training_plan.weeks_duration
        logger.info(
            "map_runs_to_plan: plan=%s, start_date=%s, today=%s, weeks=%d",
            plan_id, start_date, today, num_weeks,
        )

        # ----------------------------------------------------------
        # 1. Build available workouts by week (all types incl. rest)
        # ----------------------------------------------------------
        all_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        )

        already_linked_ids = set(
            row[0] for row in
            db.query(RunLog.daily_workout_id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.isnot(None),
            )
            .all()
        )

        # Group available (not-yet-linked, past) workouts by week
        workouts_by_week: Dict[int, list] = defaultdict(list)
        for workout, week_number in all_workouts:
            if workout.id in already_linked_ids:
                continue
            workout_date = start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1),
            )
            if workout_date > today:
                continue
            workouts_by_week[week_number].append((workout, workout_date))

        logger.info(
            "map_runs_to_plan: %d total workouts, %d already linked, "
            "%d available across %d weeks",
            len(all_workouts), len(already_linked_ids),
            sum(len(v) for v in workouts_by_week.values()),
            len(workouts_by_week),
        )

        # ----------------------------------------------------------
        # 2. Get all mappable runs (start_date to today)
        # ----------------------------------------------------------
        unlinked_runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= start_date,
                RunLog.date <= today,
                or_(
                    RunLog.training_plan_id.is_(None),
                    RunLog.training_plan_id != plan_id,
                    and_(
                        RunLog.training_plan_id == plan_id,
                        RunLog.daily_workout_id.is_(None),
                    ),
                ),
            )
            .all()
        )

        logger.info(
            "map_runs_to_plan: %d unlinked runs in [%s, %s]",
            len(unlinked_runs), start_date, today,
        )

        if not unlinked_runs:
            return {"mapped": 0, "proposals": [], "message": "No unlinked runs to map."}

        # ----------------------------------------------------------
        # 3. Assign each run to its training week
        # ----------------------------------------------------------
        runs_by_week: Dict[int, list] = defaultdict(list)
        for run in unlinked_runs:
            run_date = _to_date(run.date)
            delta_days = (run_date - start_date).days
            week_number = (delta_days // 7) + 1
            # Clamp to plan boundaries
            week_number = max(1, min(week_number, num_weeks))
            runs_by_week[week_number].append(run)

        # ----------------------------------------------------------
        # 4. Per-week greedy matching: score = days_off * 3 + km_diff
        # ----------------------------------------------------------
        def _match_score(date_penalty: float, dist_diff: float) -> float:
            return date_penalty * 3.0 + dist_diff

        proposals = []
        used_run_ids: set = set()

        all_week_numbers = sorted(
            set(list(runs_by_week.keys()) + list(workouts_by_week.keys()))
        )

        for wn in all_week_numbers:
            week_runs = runs_by_week.get(wn, [])
            week_workouts = workouts_by_week.get(wn, [])

            # Build edges between every (run, workout) pair in this week
            edges: list[tuple[float, object, object, object]] = []
            for run in week_runs:
                run_date = _to_date(run.date)
                for workout, workout_date in week_workouts:
                    date_penalty = abs((run_date - workout_date).days)
                    dist_diff = abs(
                        (run.distance_km or 0) - (workout.distance_km or 0)
                    )
                    # Prefer real workouts over rest/recovery for runs with
                    # meaningful distance (>1 km).  Adds a small penalty so
                    # rest slots are used only when no better option exists.
                    rest_penalty = 0.0
                    if workout.workout_type in ("rest", "recovery") and (run.distance_km or 0) > 1:
                        rest_penalty = 10.0
                    score = _match_score(date_penalty, dist_diff) + rest_penalty
                    edges.append((score, run, workout, workout_date))

            # Greedy: best score first
            edges.sort(key=lambda e: e[0])
            matched_run_ids: set = set()
            matched_workout_ids: set = set()

            for score, run, workout, workout_date in edges:
                if run.id in matched_run_ids or workout.id in matched_workout_ids:
                    continue
                matched_run_ids.add(run.id)
                matched_workout_ids.add(workout.id)
                used_run_ids.add(run.id)

                run_date = _to_date(run.date)
                proposals.append({
                    "run_id": run.id,
                    "workout_id": workout.id,
                    "week": wn,
                    "day": workout.day_of_week,
                    "workout_type": workout.workout_type,
                    "planned_distance": workout.distance_km,
                    "actual_distance": run.distance_km,
                    "run_date": str(run_date),
                    "workout_date": str(workout_date),
                    "match_type": "workout",
                })

            # Remaining unmatched runs -> volume-only for this week
            for run in week_runs:
                if run.id in matched_run_ids or run.id in used_run_ids:
                    continue
                used_run_ids.add(run.id)
                run_date = _to_date(run.date)
                proposals.append({
                    "run_id": run.id,
                    "workout_id": None,
                    "week": wn,
                    "day": None,
                    "workout_type": None,
                    "planned_distance": None,
                    "actual_distance": run.distance_km,
                    "run_date": str(run_date),
                    "workout_date": None,
                    "match_type": "weekly_volume",
                })

        if not proposals:
            return {
                "mapped": 0, "proposals": [],
                "message": "No matching runs found.",
            }

        if dry_run:
            return {"mapped": 0, "proposals": proposals, "dry_run": True}

        # ----------------------------------------------------------
        # 5. Persist mappings
        # ----------------------------------------------------------
        proposal_run_ids = [p["run_id"] for p in proposals]
        runs_by_id = {
            r.id: r
            for r in db.query(RunLog).filter(RunLog.id.in_(proposal_run_ids)).all()
        }
        for p in proposals:
            run = runs_by_id.get(p["run_id"])
            if run:
                run.daily_workout_id = (
                    p["workout_id"] if p["match_type"] == "workout" else None
                )
                run.training_plan_id = plan_id

        db.commit()

        return {
            "mapped": len(proposals),
            "proposals": proposals,
        }

    # ------------------------------------------------------------------
    # Unified plan adjustment (14-day sliding window)
    # ------------------------------------------------------------------

    def adjust_plan(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Dict[str, any]:
        """Adjust future plan weeks using a 14-day sliding window with 3 signals.

        Combines volume adherence (50%), perceived effort (30%), and
        completion rate (20%) into a single multiplier that is applied to
        all future non-rest workouts from their baseline distances.

        Args:
            plan_id: Training plan ID.
            user_id: User ID (for ownership verification).
            db: Database session.

        Returns:
            Dict with adjustment results.
        """
        # 1. Load plan, verify ownership and start_date
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"adjusted": False, "reason": "Plan not found"}

        if not training_plan.start_date:
            return {"adjusted": False, "reason": "Plan has no start date."}

        # 2. Auto-map any unmapped runs before adjusting
        self.map_runs_to_plan(plan_id, user_id, db)

        # 3. Backfill baselines for legacy plans
        self._backfill_baselines(training_plan, db)

        # 3. Determine current week
        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        days_elapsed = (today - start_date).days
        current_week = max(1, days_elapsed // 7 + 1)

        # 4. Get runs in the last 14 days linked to this plan
        window_start = today - timedelta(days=14)
        runs_in_window = (
            db.query(RunLog)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.date >= window_start,
            )
            .all()
        )

        if len(runs_in_window) < 3:
            return {
                "adjusted": False,
                "reason": "Not enough recent data (need at least 3 runs in the last 14 days)",
                "runs_in_window": len(runs_in_window),
            }

        # ----------------------------------------------------------
        # Signal 1 -- Volume adherence (weight 50%)
        # ----------------------------------------------------------
        # Compute planned km in window from non-rest DailyWorkouts
        all_workouts_with_week = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type != "rest",
            )
            .all()
        )

        planned_km_in_window = 0.0
        # Build a set of workout IDs whose scheduled date is in window AND in the past
        workouts_in_window_ids = set()
        for workout, week_number in all_workouts_with_week:
            scheduled_date = start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1),
            )
            if window_start <= scheduled_date <= today:
                planned_km_in_window += workout.baseline_distance_km or workout.distance_km or 0
                workouts_in_window_ids.add(workout.id)

        actual_km_in_window = sum(r.distance_km or 0 for r in runs_in_window)

        if planned_km_in_window > 0:
            volume_ratio = actual_km_in_window / planned_km_in_window
        else:
            volume_ratio = 1.0
        # Clamp to [0.5, 1.5]
        volume_ratio = max(0.5, min(1.5, volume_ratio))

        # ----------------------------------------------------------
        # Signal 2 -- Effort signal (weight 30%)
        # ----------------------------------------------------------
        efforts = [
            r.perceived_effort for r in runs_in_window
            if r.perceived_effort is not None
        ]
        if not efforts:
            effort_factor = 1.0
            avg_effort = None
        else:
            avg_effort = sum(efforts) / len(efforts)
            if avg_effort <= 3:
                effort_factor = 1.08
            elif avg_effort <= 5:
                effort_factor = 1.03
            elif avg_effort <= 7:
                effort_factor = 1.00
            elif avg_effort <= 8.5:
                effort_factor = 0.95
            else:
                effort_factor = 0.88

        # ----------------------------------------------------------
        # Signal 3 -- Completion rate (weight 20%)
        # ----------------------------------------------------------
        # scheduled_in_window: non-rest workouts whose scheduled date
        # is in the 14-day window AND in the past (<= today)
        scheduled_in_window = len(workouts_in_window_ids)

        # completed_in_window: those with a linked RunLog
        if workouts_in_window_ids:
            completed_in_window = (
                db.query(RunLog)
                .filter(
                    RunLog.training_plan_id == plan_id,
                    RunLog.daily_workout_id.in_(workouts_in_window_ids),
                )
                .count()
            )
        else:
            completed_in_window = 0

        completion_rate = (
            completed_in_window / scheduled_in_window
            if scheduled_in_window > 0
            else 0.0
        )

        if completion_rate >= 0.9:
            completion_factor = 1.05
        elif completion_rate >= 0.7:
            completion_factor = 1.00
        elif completion_rate >= 0.5:
            completion_factor = 0.92
        else:
            completion_factor = 0.85

        # ----------------------------------------------------------
        # Combine signals
        # ----------------------------------------------------------
        raw_multiplier = (
            (volume_ratio * 0.50)
            + (effort_factor * 0.30)
            + (completion_factor * 0.20)
        )
        multiplier = round(max(0.80, min(1.15, raw_multiplier)), 2)

        # ----------------------------------------------------------
        # Apply to future weeks
        # ----------------------------------------------------------
        future_weeks = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number > current_week,
            )
            .all()
        )

        if not future_weeks:
            return {
                "adjusted": False,
                "multiplier": multiplier,
                "volume_ratio": round(volume_ratio, 2),
                "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
                "completion_rate": round(completion_rate, 2),
                "runs_in_window": len(runs_in_window),
                "weeks_changed": 0,
                "reason": "No future weeks remaining to adjust.",
            }

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(training_plan)

        workouts_by_week = self._batch_workouts_by_week(
            [week.id for week in future_weeks], db
        )

        weeks_changed = 0
        any_distance_changed = False

        for week in future_weeks:
            workouts = workouts_by_week.get(week.id, [])
            week_changed = False

            for workout in workouts:
                if (
                    workout.workout_type == "rest"
                    or not workout.distance_km
                    or workout.distance_km <= 0
                ):
                    continue

                base_distance = workout.baseline_distance_km or workout.distance_km
                new_distance = max(1.0, round(base_distance * multiplier, 1))
                old_distance = workout.distance_km

                if new_distance == old_distance:
                    continue

                workout.distance_km = new_distance
                any_distance_changed = True
                week_changed = True

                # Strip old annotations and append new one
                clean_notes = _ANNOTATION_RE.sub("", workout.notes or "").strip()
                if multiplier != 1.0:
                    adjust_note = f"(Adjusted: x{multiplier})"
                    workout.notes = (
                        f"{clean_notes} {adjust_note}".strip()
                        if clean_notes
                        else adjust_note
                    )
                else:
                    workout.notes = clean_notes or None

                # Sync plan_data JSON
                pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                if pd_wo is not None:
                    pd_wo["distance"] = new_distance
                    pd_clean = _ANNOTATION_RE.sub(
                        "", pd_wo.get("notes", pd_wo.get("description", ""))
                    ).strip()
                    if multiplier != 1.0:
                        pd_wo["notes"] = (
                            f"{pd_clean} {adjust_note}".strip()
                            if pd_clean
                            else adjust_note
                        )
                    else:
                        pd_wo["notes"] = pd_clean

            if week_changed:
                weeks_changed += 1
                new_total = round(
                    sum(w.distance_km for w in workouts if w.distance_km), 1
                )
                week.total_km = new_total
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = new_total

        # Persist
        training_plan.adjustment_multiplier = multiplier
        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        # Build human-readable reason
        direction = "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
        reason_parts = [f"Future weeks {direction} (x{multiplier})."]
        reason_parts.append(
            f"Volume ratio: {round(volume_ratio, 2)}, "
            f"completion: {round(completion_rate * 100)}%."
        )
        if avg_effort is not None:
            reason_parts.append(f"Avg effort: {round(avg_effort, 1)}/10.")

        return {
            "adjusted": any_distance_changed,
            "multiplier": multiplier,
            "volume_ratio": round(volume_ratio, 2),
            "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
            "completion_rate": round(completion_rate, 2),
            "runs_in_window": len(runs_in_window),
            "weeks_changed": weeks_changed,
            "reason": " ".join(reason_parts),
        }
