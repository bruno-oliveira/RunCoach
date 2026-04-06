"""Service for adapting training plans based on performance data."""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan, User
from app.services.race_predictor_service import RacePredictorService
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

# Regex to strip legacy adaptation/recalibration notes from workout notes
_ANNOTATION_RE = re.compile(r"\s*\((Adapted|Recalibrated|Adjusted):[^)]*\)")


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
        plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []
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
    ) -> Dict[str, Any]:
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

        adherence_rate = min(100.0, total_logged / planned_workouts * 100) if planned_workouts > 0 else 0

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

    def _calculate_pace_consistency(self, paces: List[float]) -> Optional[float]:
        """Calculate coefficient of variation for pace."""
        if len(paces) < 2:
            return None

        avg_pace = sum(paces) / len(paces)
        variance = sum((p - avg_pace) ** 2 for p in paces) / (len(paces) - 1)
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
        *,
        since: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """Detect skipped and rescheduled workouts up to today.

        A workout is "unlinked" if no RunLog references it directly.
        Among unlinked workouts:
        - "rescheduled" = that week's total volume was still met (>= 80%)
        - "skipped" = truly missed (week volume not met)

        Args:
            since: If provided, only count workouts scheduled after this date.
                   Used to avoid re-flagging misses that were already addressed
                   by a prior adjustment.

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
        since_date = _to_date(since) if since else None

        for workout, week_number in daily_workouts:
            workout_date = plan_start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1)
            )
            if workout_date > today:
                continue
            # Skip workouts that were already accounted for by a prior adjustment
            if since_date and workout_date <= since_date:
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
    ) -> Dict[str, Any]:
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
        # Use tomorrow for upper-bound queries so today's runs are included.
        # SQLite compares dates as strings, so "2026-03-23 07:36:20" > "2026-03-23"
        # and a <= today filter would exclude all runs logged today.
        tomorrow = today + timedelta(days=1)
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
                RunLog.date < tomorrow,
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
    ) -> Dict[str, Any]:
        """Adjust future plan weeks using full-history weighted signals.

        Uses exponential decay (half-life = 3 weeks) so all past workouts
        contribute, but recent performance weighs more heavily.  Combines
        volume adherence (50%), perceived effort (30%), and completion
        rate (20%) into a single multiplier applied to all future non-rest
        workouts from their baseline distances.

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

        # 4. Determine current week
        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        days_elapsed = (today - start_date).days
        current_week = max(1, days_elapsed // 7 + 1)

        # 5. Get ALL runs linked to this plan (not just a 14-day window)
        all_plan_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan_id)
            .all()
        )

        if len(all_plan_runs) < 3:
            return {
                "adjusted": False,
                "reason": (
                    "Not enough data (need at least 3 logged runs "
                    "linked to this plan)"
                ),
                "total_runs": len(all_plan_runs),
            }

        # Exponential-decay weight: half-life of 3 weeks
        half_life_weeks = 3.0

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / half_life_weeks)

        # ----------------------------------------------------------
        # Gather all past non-rest workouts with their scheduled dates
        # ----------------------------------------------------------
        all_workouts_with_week = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type != "rest",
            )
            .all()
        )

        # Build lookup: workout_id -> scheduled_date (only past)
        past_workouts: List[Tuple] = []  # (workout, scheduled_date)
        past_workout_ids: set = set()
        for workout, week_number in all_workouts_with_week:
            scheduled_date = start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1),
            )
            if scheduled_date <= today:
                past_workouts.append((workout, scheduled_date))
                past_workout_ids.add(workout.id)

        if not past_workouts:
            return {
                "adjusted": False,
                "reason": "No past workouts to evaluate yet.",
            }

        # Compute signals and combined multiplier
        signals = self._compute_adjustment_signals(
            all_plan_runs, past_workouts, past_workout_ids,
            today, plan_id, db, _recency_weight,
        )
        multiplier = signals["multiplier"]

        # Apply to current and future weeks (skip past workouts in current week)
        current_day_of_week = today.isoweekday()  # 1=Mon … 7=Sun
        adjustable_weeks = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number >= current_week,
            )
            .all()
        )

        if not adjustable_weeks:
            return {
                "adjusted": False,
                **{k: signals[k] for k in (
                    "multiplier", "volume_ratio", "avg_effort", "completion_rate",
                )},
                "total_runs": len(all_plan_runs),
                "weeks_changed": 0,
                "reason": "No remaining workouts to adjust.",
            }

        weeks_changed, any_distance_changed = self._apply_adjustment_to_future_weeks(
            training_plan, adjustable_weeks, multiplier, db,
            current_week=current_week,
            current_day_of_week=current_day_of_week,
        )

        # Persist
        training_plan.adjustment_multiplier = multiplier
        training_plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

        # Build human-readable reason
        volume_ratio = signals["volume_ratio"]
        completion_rate = signals["completion_rate"]
        avg_effort = signals["avg_effort"]
        direction = "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
        reason_parts = [f"Remaining workouts {direction} (x{multiplier})."]
        reason_parts.append(
            f"Volume ratio: {round(volume_ratio, 2)}, "
            f"completion: {round(completion_rate * 100)}%."
        )
        if avg_effort is not None:
            reason_parts.append(f"Avg effort: {round(avg_effort, 1)}/10.")

        logger.info(
            "adjust_plan result: multiplier=%.2f raw=%.3f "
            "volume_ratio=%.2f effort_factor=%.2f(avg=%.1f) "
            "completion_factor=%.2f(rate=%.2f) runs=%d",
            multiplier,
            signals["raw_multiplier"],
            volume_ratio,
            signals["effort_factor"],
            avg_effort if avg_effort is not None else 0,
            signals["completion_factor"],
            completion_rate,
            len(all_plan_runs),
        )

        return {
            "adjusted": any_distance_changed,
            **signals,
            "total_runs": len(all_plan_runs),
            "weeks_changed": weeks_changed,
            "reason": " ".join(reason_parts),
        }

    def _compute_adjustment_signals(
        self,
        all_plan_runs: List,
        past_workouts: List[Tuple],
        past_workout_ids: set,
        today,
        plan_id: str,
        db: Session,
        recency_weight_fn,
    ) -> Dict[str, Any]:
        """Compute volume, effort, and completion signals for plan adjustment."""
        # Volume adherence (weight 50%)
        planned_weighted = 0.0
        for workout, sched_date in past_workouts:
            w = recency_weight_fn(sched_date)
            dist = workout.baseline_distance_km or workout.distance_km or 0
            planned_weighted += dist * w

        actual_weighted = 0.0
        for run in all_plan_runs:
            run_date = _to_date(run.date) if run.date else today
            w = recency_weight_fn(run_date)
            actual_weighted += (run.distance_km or 0) * w

        volume_ratio = max(0.5, min(1.5,
            actual_weighted / planned_weighted if planned_weighted > 0 else 1.0
        ))

        # Effort signal (weight 30%)
        effort_sum = 0.0
        effort_weight_sum = 0.0
        for run in all_plan_runs:
            if run.perceived_effort is not None:
                run_date = _to_date(run.date) if run.date else today
                w = recency_weight_fn(run_date)
                effort_sum += run.perceived_effort * w
                effort_weight_sum += w

        if effort_weight_sum > 0:
            avg_effort = effort_sum / effort_weight_sum
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
        else:
            effort_factor = 1.0
            avg_effort = None

        # Completion rate (weight 20%)
        completed_ids = set()
        if past_workout_ids:
            completed_rows = (
                db.query(RunLog.daily_workout_id)
                .filter(
                    RunLog.training_plan_id == plan_id,
                    RunLog.daily_workout_id.in_(past_workout_ids),
                )
                .all()
            )
            completed_ids = {row[0] for row in completed_rows}

        scheduled_weighted = 0.0
        completed_weighted = 0.0
        for workout, sched_date in past_workouts:
            w = recency_weight_fn(sched_date)
            scheduled_weighted += w
            if workout.id in completed_ids:
                completed_weighted += w

        completion_rate = (
            completed_weighted / scheduled_weighted
            if scheduled_weighted > 0 else 0.0
        )

        if completion_rate >= 0.9:
            completion_factor = 1.05
        elif completion_rate >= 0.7:
            completion_factor = 1.00
        elif completion_rate >= 0.5:
            completion_factor = 0.95
        else:
            completion_factor = 0.90

        # Combine signals
        raw_multiplier = (
            (volume_ratio * 0.50)
            + (effort_factor * 0.30)
            + (completion_factor * 0.20)
        )
        multiplier = round(max(0.85, min(1.15, raw_multiplier)), 2)

        return {
            "multiplier": multiplier,
            "volume_ratio": round(volume_ratio, 2),
            "effort_factor": round(effort_factor, 2),
            "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
            "completion_rate": round(completion_rate, 2),
            "completion_factor": round(completion_factor, 2),
            "raw_multiplier": round(raw_multiplier, 3),
        }

    def _apply_adjustment_to_future_weeks(
        self,
        training_plan: TrainingPlan,
        future_weeks: List,
        multiplier: float,
        db: Session,
        *,
        current_week: int | None = None,
        current_day_of_week: int | None = None,
    ) -> Tuple[int, bool]:
        """Apply the adjustment multiplier to future weeks. Returns (weeks_changed, any_distance_changed).

        When *current_week* and *current_day_of_week* are provided, workouts
        in the current week that are already past (day < current_day_of_week)
        are left untouched.
        """
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

                # Skip workouts already past in the current week
                if (
                    current_week is not None
                    and current_day_of_week is not None
                    and week.week_number == current_week
                    and workout.day_of_week < current_day_of_week
                ):
                    continue

                base_distance = workout.baseline_distance_km or workout.distance_km

                # Protect long runs: keep at baseline when reducing
                if workout.workout_type == "long" and multiplier < 1.0:
                    new_distance = round(base_distance, 1)
                elif workout.workout_type in ("interval", "tempo", "hill"):
                    # Quality workouts get half the adjustment to avoid
                    # over-inflating/deflating structured work
                    quality_mult = 1.0 + (multiplier - 1.0) * 0.5
                    new_distance = max(1.0, round(base_distance * quality_mult, 1))
                else:
                    new_distance = max(1.0, round(base_distance * multiplier, 1))
                old_distance = workout.distance_km

                if new_distance == old_distance:
                    continue

                workout.distance_km = new_distance
                any_distance_changed = True
                week_changed = True

                is_protected = (
                    workout.workout_type == "long" and multiplier < 1.0
                )

                # Strip old annotations and append new one
                clean_notes = _ANNOTATION_RE.sub("", workout.notes or "").strip()
                if multiplier != 1.0 and not is_protected:
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
                    if multiplier != 1.0 and not is_protected:
                        adjust_note = f"(Adjusted: x{multiplier})"
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

        training_plan.plan_data = json.dumps(plan_data)
        return weeks_changed, any_distance_changed

    def reset_adjustment(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Reset plan to original baseline distances, removing any adjustment.

        Restores every workout's distance_km from baseline_distance_km,
        clears the adjustment_multiplier, and strips adjustment annotations.

        Args:
            plan_id: Training plan ID.
            user_id: User ID (for ownership verification).
            db: Database session.

        Returns:
            Dict with reset results.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"reset": False, "reason": "Plan not found"}

        if not training_plan.adjustment_multiplier:
            return {"reset": False, "reason": "Plan has no active adjustment."}

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(
            training_plan
        )

        all_weeks = (
            db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        )

        workouts_by_week = self._batch_workouts_by_week(
            [week.id for week in all_weeks], db
        )

        weeks_changed = 0
        for week in all_weeks:
            workouts = workouts_by_week.get(week.id, [])
            week_changed = False

            for workout in workouts:
                if not workout.baseline_distance_km:
                    # Strip annotation even if no baseline
                    clean = _ANNOTATION_RE.sub(
                        "", workout.notes or ""
                    ).strip()
                    if clean != (workout.notes or "").strip():
                        workout.notes = clean or None
                    continue

                if workout.distance_km != workout.baseline_distance_km:
                    workout.distance_km = workout.baseline_distance_km
                    week_changed = True

                # Strip adjustment annotations
                clean_notes = _ANNOTATION_RE.sub(
                    "", workout.notes or ""
                ).strip()
                workout.notes = clean_notes or None

                # Sync plan_data JSON
                pd_wo = pd_workout.get(
                    (week.week_number, workout.day_of_week)
                )
                if pd_wo is not None:
                    pd_wo["distance"] = workout.baseline_distance_km
                    pd_clean = _ANNOTATION_RE.sub(
                        "",
                        pd_wo.get("notes", pd_wo.get("description", "")),
                    ).strip()
                    pd_wo["notes"] = pd_clean

            if week_changed:
                weeks_changed += 1
                new_total = round(
                    sum(
                        w.distance_km
                        for w in workouts
                        if w.distance_km
                    ),
                    1,
                )
                week.total_km = new_total
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = new_total

        training_plan.adjustment_multiplier = None
        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        return {
            "reset": True,
            "weeks_changed": weeks_changed,
            "reason": "Plan restored to original distances.",
        }

    # ------------------------------------------------------------------
    # Proactive adaptation alerts
    # ------------------------------------------------------------------

    def check_alerts(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Check if a plan needs a proactive adaptation alert.

        Evaluates:
        - Weekly volume deficit > 25% for 2+ consecutive weeks
        - Effort trending "increasing" for 3+ weeks
        - No runs logged in 7+ days (potential injury/break)
        - VDOT declining over 4+ week window

        Returns an alert dict if a condition is met, or None.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan or not training_plan.start_date:
            return None

        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        delta_days = (today - start_date).days
        if delta_days < 7:
            return None

        current_week = min((delta_days // 7) + 1, training_plan.weeks_duration or 0)
        if current_week < 2:
            return None

        plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []

        # Get runs
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= datetime.combine(start_date, datetime.min.time()),
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        # ── Check 1: No runs in 7+ days ──
        if runs:
            last_run_date = _to_date(runs[-1].date)
            if last_run_date and (today - last_run_date).days >= 7:
                alert = {
                    "type": "no_recent_runs",
                    "severity": "high",
                    "message": f"No runs logged in {(today - last_run_date).days} days. Are you taking a break or dealing with an injury?",
                    "created_at": today.isoformat(),
                }
                training_plan.adaptation_alert = json.dumps(alert)
                db.commit()
                return alert

        # ── Check 2: Volume deficit for 2+ consecutive weeks ──
        weekly_actual = defaultdict(float)
        for run in runs:
            rd = _to_date(run.date)
            if rd and start_date:
                d = (rd - start_date).days
                if d >= 0:
                    wk = d // 7 + 1
                    weekly_actual[wk] += run.distance_km or 0

        consecutive_deficit = 0
        for wk_num in range(max(1, current_week - 4), current_week + 1):
            week_data = next((w for w in plan_data if w.get("week") == wk_num), None)
            if not week_data:
                continue
            planned = week_data.get("total_km", 0)
            actual = weekly_actual.get(wk_num, 0)
            if planned > 0 and actual < planned * 0.75:
                consecutive_deficit += 1
            else:
                consecutive_deficit = 0

        if consecutive_deficit >= 2:
            alert = {
                "type": "volume_deficit",
                "severity": "medium",
                "message": f"Weekly volume has been 25%+ below target for {consecutive_deficit} consecutive weeks.",
                "created_at": today.isoformat(),
            }
            training_plan.adaptation_alert = json.dumps(alert)
            db.commit()
            return alert

        # ── Check 3: Effort trend increasing ──
        perf = self.analyze_performance(plan_id, db)
        if perf.get("effort_trend") == "increasing":
            avg_effort = perf.get("avg_effort")
            if avg_effort and avg_effort >= 7:
                alert = {
                    "type": "high_effort",
                    "severity": "medium",
                    "message": "Effort is trending upward and averaging above 7/10. Fatigue may be building.",
                    "created_at": today.isoformat(),
                }
                training_plan.adaptation_alert = json.dumps(alert)
                db.commit()
                return alert

        # ── Check 4: VDOT declining ──
        predictions = RacePredictorService.get_predictions_for_user(user_id, db)
        if predictions.get("vdot_trend") == "declining":
            alert = {
                "type": "vdot_declining",
                "severity": "low",
                "message": "Your VDOT has been declining. Consider adding quality speed work or reviewing recovery.",
                "created_at": today.isoformat(),
            }
            training_plan.adaptation_alert = json.dumps(alert)
            db.commit()
            return alert

        # No alerts — clear any existing one
        if training_plan.adaptation_alert is not None:
            training_plan.adaptation_alert = None
            db.commit()

        return None

    def recalibrate(
        self,
        plan_id: str,
        user_id: str,
        strategy: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Recalibrate remaining plan weeks based on a user-chosen strategy.

        Strategies:
        - "time_off": Rebuild remaining weeks with a gentler ramp
        - "ahead": Bump up remaining weeks' targets
        - "new_goal": Not handled here (requires new goal_time from UI)
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"ok": False, "error": "Plan not found"}

        start_date = _to_date(training_plan.start_date)
        if not start_date:
            return {"ok": False, "error": "Plan has no start date"}

        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        current_week = min(
            ((today - start_date).days // 7) + 1,
            training_plan.weeks_duration or 0,
        )

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(training_plan)

        weekly_plans = {
            wp.week_number: wp
            for wp in db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        }

        week_ids = [wp.id for wp in weekly_plans.values()]
        workouts_by_week = self._batch_workouts_by_week(week_ids, db)

        if strategy == "time_off":
            factor = 0.8  # reduce remaining by 20% then ramp back
        elif strategy == "ahead":
            factor = 1.1  # bump up by 10%
        else:
            return {"ok": False, "error": f"Unknown strategy: {strategy}"}

        weeks_changed = 0
        for week in weekly_plans.values():
            if week.week_number <= current_week:
                continue

            workouts = workouts_by_week.get(week.id, [])
            week_changed = False

            # For time_off: gentler ramp — reduce more for nearer weeks, less for later
            if strategy == "time_off":
                weeks_from_now = week.week_number - current_week
                total_remaining = training_plan.weeks_duration - current_week
                ramp = weeks_from_now / max(total_remaining, 1)
                week_factor = 0.7 + 0.3 * ramp  # 70% to 100% ramp
            else:
                week_factor = factor

            for workout in workouts:
                if not workout.distance_km or workout.workout_type in ("rest", "recovery"):
                    continue
                new_dist = round(workout.distance_km * week_factor, 1)
                if abs(new_dist - workout.distance_km) > 0.05:
                    workout.distance_km = new_dist
                    week_changed = True
                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo:
                        pd_wo["distance"] = new_dist

            if week_changed:
                weeks_changed += 1
                new_total = round(
                    sum(w.distance_km for w in workouts if w.distance_km), 1
                )
                week.total_km = new_total
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = new_total

        training_plan.plan_data = json.dumps(plan_data)
        # Clear the alert after recalibration
        training_plan.adaptation_alert = None
        training_plan.last_adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

        strategy_labels = {
            "time_off": "Plan recalibrated with a gentler ramp from current fitness.",
            "ahead": "Plan targets increased based on your strong performance.",
        }

        return {
            "ok": True,
            "strategy": strategy,
            "weeks_changed": weeks_changed,
            "reason": strategy_labels.get(strategy, "Plan recalibrated."),
        }

    # ------------------------------------------------------------------
    # Weekly inline suggestions
    # ------------------------------------------------------------------

    def get_weekly_suggestions(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Generate per-week suggestion cards for in-plan display.

        Returns a list of suggestion objects, each tied to a specific
        upcoming week in the plan.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan or not training_plan.start_date:
            return []

        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        total_weeks = training_plan.weeks_duration or 0

        delta_days = (today - start_date).days
        if delta_days < 0:
            return []

        current_week = min((delta_days // 7) + 1, total_weeks)

        # Get performance analysis
        perf = self.analyze_performance(plan_id, db)
        skipped = self.detect_skipped_workouts(plan_id, db)
        adherence = perf.get("adherence_rate", 0)
        effort_trend = perf.get("effort_trend", "stable")
        avg_effort = perf.get("avg_effort")

        # Get planned data
        plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []

        # Get recent run volumes by week
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.training_plan_id == plan_id,
            )
            .order_by(RunLog.date.asc())
            .all()
        )

        weekly_actual = defaultdict(float)
        for run in runs:
            rd = _to_date(run.date)
            if rd and start_date:
                d = (rd - start_date).days
                if d >= 0:
                    wk = d // 7 + 1
                    weekly_actual[wk] += run.distance_km or 0

        # Check for consecutive weeks exceeding or falling short
        exceeding_count = 0
        deficit_count = 0
        for wk in range(max(1, current_week - 3), current_week + 1):
            week_data = next((w for w in plan_data if w.get("week") == wk), None)
            if not week_data:
                continue
            planned = week_data.get("total_km", 0)
            actual = weekly_actual.get(wk, 0)
            if planned > 0:
                ratio = actual / planned
                if ratio >= 1.05:
                    exceeding_count += 1
                elif ratio < 0.75:
                    deficit_count += 1

        # Compute the adjustment multiplier if it exists
        multiplier = training_plan.adjustment_multiplier

        # Generate suggestions for upcoming weeks
        suggestions = []

        for week_data in plan_data:
            wk_num = week_data.get("week", 0)
            if wk_num <= current_week or wk_num > current_week + 3:
                continue  # Only show suggestions for next 3 upcoming weeks

            week_suggestions = []

            # Exceeding targets pattern
            if exceeding_count >= 3:
                pct = "+" + str(round((multiplier - 1) * 100)) + "%" if multiplier and multiplier > 1 else "+8%"
                week_suggestions.append({
                    "type": "exceeding",
                    "message": f"You've exceeded targets {exceeding_count} weeks in a row — this week's distances have been bumped {pct}",
                    "action": "accept",
                })

            # Deficit pattern
            if deficit_count >= 2 and not any(s["type"] == "exceeding" for s in week_suggestions):
                week_suggestions.append({
                    "type": "deficit",
                    "message": "Volume has been below target — consider adding an extra easy run this week",
                    "action": "accept",
                })

            # Long run suggestion
            long_wo = next(
                (wo for wo in week_data.get("daily_workouts", []) if wo.get("type") == "long"),
                None,
            )
            if long_wo and skipped.get("skipped", 0) > 2:
                km = long_wo.get("distance", 0)
                week_suggestions.append({
                    "type": "long_run",
                    "message": f"Long run completion is behind — consider extending Sunday's run to {round(km + 2)}km",
                    "action": "accept",
                })

            # Effort trend
            if effort_trend == "increasing" and avg_effort and avg_effort > 7:
                # Check if this is a recovery week
                is_recovery = week_data.get("phase", "").lower() in ("recovery", "taper")
                if is_recovery:
                    week_suggestions.append({
                        "type": "effort_recovery",
                        "message": "Effort trending high — this recovery week is well-timed",
                        "action": None,
                    })
                else:
                    week_suggestions.append({
                        "type": "effort_high",
                        "message": "Effort is trending high — consider reducing intensity this week",
                        "action": "reduce",
                    })

            # Low adherence
            if adherence < 60 and not any(s["type"] in ("deficit",) for s in week_suggestions):
                week_suggestions.append({
                    "type": "adherence",
                    "message": "Consistency is low — focus on completing the key workouts this week",
                    "action": None,
                })

            if week_suggestions:
                suggestions.append({
                    "week": wk_num,
                    "suggestions": week_suggestions[:2],  # max 2 per week
                })

        return suggestions
