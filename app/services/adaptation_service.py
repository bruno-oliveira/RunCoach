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
from app.utils import format_pace_bare

logger = logging.getLogger(__name__)


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
        current distance_km. If the plan already has a strava_adapted_multiplier,
        the baseline is reverse-computed as distance / multiplier.
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

        strava_mult = training_plan.strava_adapted_multiplier
        recal_mult = training_plan.recalibration_multiplier
        for workout in workouts_needing_backfill:
            base = workout.distance_km
            # Reverse existing multipliers to recover original baseline
            if strava_mult and strava_mult != 0:
                base = base / strava_mult
            if recal_mult and recal_mult != 0:
                base = base / recal_mult
            workout.baseline_distance_km = round(base, 2)
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
        """Adapt future weeks based on performance (delegates to recalibrate).

        This endpoint is kept for backward compatibility. It now delegates
        to recalibrate_plan() which incorporates both adherence and effort
        signals into a single adjustment.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == training_plan_id,
        ).first()
        if not training_plan:
            return {"adapted": False, "reason": "Plan not found", "changes": []}

        result = self.recalibrate_plan(training_plan_id, training_plan.user_id, db)

        # Map recalibrate response to adapt response format
        if result.get("recalibrated"):
            return {
                "adapted": True,
                "reason": result["reason"],
                "adjustment_type": "recalibration",
                "changes": result["changes"],
            }
        return {
            "adapted": False,
            "reason": result.get("reason", "No adaptation needed"),
            "changes": [],
        }

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

    def adapt_plan_from_fitness(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Dict[str, any]:
        """
        Adapt remaining plan weeks based on Strava-synced fitness metrics.

        Uses AdaptivePlanGenerator to compute fitness from all RunLog data
        (including Strava-synced runs) and adjusts future weeks accordingly.

        If the plan was previously adapted, the old multiplier is reversed before
        the new one is applied so distances never compound across repeated calls.

        Args:
            plan_id: Training plan ID
            user_id: User ID
            db: Database session

        Returns:
            Dict with adaptation results including fitness metrics and changes
        """
        from app.core.adaptive_plan_generator import AdaptivePlanGenerator

        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"adapted": False, "reason": "Plan not found", "changes": []}

        # Backfill baselines for legacy plans
        self._backfill_baselines(training_plan, db)

        # Calculate fitness metrics from all run logs
        adaptive_gen = AdaptivePlanGenerator()
        metrics = adaptive_gen.calculate_current_fitness_metrics(user_id, db)

        if metrics["fitness_score"] == 0:
            return {
                "adapted": False,
                "reason": "No run data available to adapt from",
                "fitness": metrics,
                "changes": [],
            }

        # Determine current week based on plan start date
        start_date = _to_date(training_plan.start_date or training_plan.created_at)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        days_elapsed = (today - start_date).days
        current_week = max(1, days_elapsed // 7 + 1)

        # Fitness-based multiplier: score 50 -> 1.0x, higher -> increase, lower -> decrease
        new_multiplier = 0.8 + (metrics["fitness_score"] / 100) * 0.4  # 0.8-1.2x
        recal_mult = training_plan.recalibration_multiplier or 1.0

        # Get future weeks
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
                "adapted": False,
                "reason": "No future weeks remaining to adapt",
                "fitness": metrics,
                "changes": [],
            }

        # Regex to strip any previously appended adaptation note from workout.notes
        _adapted_note_re = re.compile(r"\s*\(Adapted:[^)]*\)")

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(training_plan)

        # Batch-load all workouts for future weeks
        workouts_by_week = self._batch_workouts_by_week(
            [week.id for week in future_weeks], db
        )

        changes = []
        for week in future_weeks:
            workouts = workouts_by_week.get(week.id, [])

            week_changes = []
            for workout in workouts:
                if workout.workout_type != "rest" and workout.distance_km and workout.distance_km > 0:
                    base_distance = workout.baseline_distance_km or workout.distance_km
                    new_distance = max(1.0, round(base_distance * new_multiplier * recal_mult, 1))
                    old_distance = workout.distance_km

                    if new_distance == old_distance:
                        continue

                    workout.distance_km = new_distance

                    if metrics["current_pace"]:
                        pace_str = f"{format_pace_bare(metrics['current_pace'])} min/km"
                        adapt_note = (
                            f"(Adapted: {round(base_distance, 1)}->{new_distance}km, "
                            f"target pace ~{pace_str})"
                        )
                    else:
                        adapt_note = f"(Adapted: {round(base_distance, 1)}->{new_distance}km)"

                    clean_notes = _adapted_note_re.sub("", workout.notes or "").strip()
                    workout.notes = f"{clean_notes} {adapt_note}".strip() if clean_notes else adapt_note

                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo is not None:
                        pd_wo["distance"] = new_distance
                        pd_clean = _adapted_note_re.sub(
                            "", pd_wo.get("notes", pd_wo.get("description", ""))
                        ).strip()
                        pd_wo["notes"] = f"{pd_clean} {adapt_note}".strip() if pd_clean else adapt_note

                    week_changes.append({
                        "day": workout.day_of_week,
                        "workout_type": workout.workout_type,
                        "old_distance": old_distance,
                        "new_distance": new_distance,
                    })

            if week_changes:
                new_total = sum(w.distance_km for w in workouts if w.distance_km)
                week.total_km = round(new_total, 1)
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = round(new_total, 1)
                changes.append({
                    "week": week.week_number,
                    "workouts_adjusted": week_changes,
                    "new_total_km": round(new_total, 1),
                })

        if not changes:
            return {
                "adapted": False,
                "reason": (
                    "Your plan distances already match your current fitness level "
                    f"(score {metrics['fitness_score']}/100, "
                    f"avg {metrics['avg_weekly_km']}km/week). "
                    "No adjustments needed."
                ),
                "fitness": metrics,
                "fitness_multiplier": round(new_multiplier, 2),
                "changes": [],
            }

        # Persist the multiplier
        training_plan.strava_adapted_multiplier = round(new_multiplier, 4)

        training_plan.plan_data = json.dumps(plan_data)

        db.commit()

        first_adapted = changes[0]["week"]
        last_adapted = changes[-1]["week"]

        return {
            "adapted": True,
            "reason": (
                f"Adjusted weeks {first_adapted}-{last_adapted} based on "
                f"Strava data: avg {metrics['avg_weekly_km']}km/week, "
                f"fitness score {metrics['fitness_score']}/100"
            ),
            "fitness": metrics,
            "fitness_multiplier": round(new_multiplier, 2),
            "changes": changes,
        }

    def reset_strava_adaptation(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Dict[str, any]:
        """Reverse a previous Strava adaptation, restoring distances.

        Uses baseline_distance_km * (recalibration_multiplier or 1.0) to
        compute the correct post-reset distance. Falls back to parsing
        the adaptation note for legacy workouts without a baseline.
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"reset": False, "reason": "Plan not found"}

        if not training_plan.strava_adapted_multiplier:
            return {"reset": False, "reason": "Plan has not been Strava-adapted"}

        # Backfill baselines so we can compute reset distances
        self._backfill_baselines(training_plan, db)

        adapted_re = re.compile(r"\s*\(Adapted:\s*([\d.]+)->[\d.]+km[^)]*\)")
        recal_mult = training_plan.recalibration_multiplier or 1.0

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(training_plan)

        all_weeks = (
            db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        )
        workouts_by_week = self._batch_workouts_by_week(
            [week.id for week in all_weeks], db
        )

        reset_count = 0
        for week in all_weeks:
            workouts = workouts_by_week.get(week.id, [])
            week_changed = False
            for workout in workouts:
                notes = workout.notes or ""
                m = adapted_re.search(notes)
                if m:
                    # Use baseline if available, otherwise fall back to note
                    if workout.baseline_distance_km:
                        restored = round(workout.baseline_distance_km * recal_mult, 1)
                    else:
                        restored = float(m.group(1))
                    workout.distance_km = restored
                    workout.notes = adapted_re.sub("", notes).strip() or None
                    reset_count += 1
                    week_changed = True

                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo is not None:
                        pd_wo["distance"] = restored
                        pd_notes = adapted_re.sub(
                            "", pd_wo.get("notes", pd_wo.get("description", ""))
                        ).strip()
                        pd_wo["notes"] = pd_notes

            if week_changed:
                new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
                week.total_km = new_total
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = new_total

        training_plan.strava_adapted_multiplier = None
        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        return {
            "reset": True,
            "reason": f"Removed Strava adaptation from {reset_count} workout(s). Distances restored.",
        }

    # ------------------------------------------------------------------
    # Feature: Retroactive run-to-plan mapping
    # ------------------------------------------------------------------

    def map_runs_to_plan(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
        *,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """Match unlinked RunLog entries to plan DailyWorkouts by date proximity.

        Requires the plan to have a start_date set. For each non-rest DailyWorkout
        whose calendar date is in the past, looks for an unlinked RunLog within
        ±1 day. When multiple candidate runs match a workout, the closest by date
        then by distance similarity is preferred.

        Args:
            plan_id: Training plan ID.
            user_id: User ID.
            db: Database session.
            dry_run: If True, return proposed mappings without persisting.

        Returns:
            Dict with ``mapped`` count, ``proposals`` list, and ``skipped`` count.
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
        logger.info(
            "map_runs_to_plan: plan=%s, start_date=%s (type=%s), today=%s",
            plan_id, start_date, type(start_date).__name__, today,
        )

        # Total runs for this user (for diagnostics)
        total_user_runs = db.query(func.count(RunLog.id)).filter(
            RunLog.user_id == user_id
        ).scalar()
        logger.info("map_runs_to_plan: total runs for user = %d", total_user_runs)

        # Build list of (DailyWorkout, computed_date) for non-rest past workouts
        # that do NOT already have a linked RunLog.
        daily_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type.notin_(["rest", "recovery"]),
            )
            .all()
        )

        # Also fetch rest/recovery workouts — runs done on planned rest days
        # should still show up on the plan (matched in a later pass).
        rest_recovery_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                DailyWorkout.workout_type.in_(["rest", "recovery"]),
            )
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

        workout_candidates = []
        for workout, week_number in daily_workouts:
            if workout.id in already_linked_ids:
                continue
            workout_date = start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1),
            )
            if workout_date > today:
                continue
            workout_candidates.append((workout, week_number, workout_date))

        logger.info(
            "map_runs_to_plan: %d daily_workouts, %d already_linked, "
            "%d workout_candidates (past & unmapped)",
            len(daily_workouts), len(already_linked_ids), len(workout_candidates),
        )
        if workout_candidates:
            dates = [str(wd) for _, _, wd in workout_candidates[:5]]
            logger.info("map_runs_to_plan: first candidate dates = %s", dates)

        if not workout_candidates:
            # Diagnose: were all filtered by future date or already linked?
            future_count = 0
            linked_count = 0
            for workout, week_number in daily_workouts:
                if workout.id in already_linked_ids:
                    linked_count += 1
                    continue
                workout_date = start_date + timedelta(
                    weeks=(week_number - 1),
                    days=(workout.day_of_week - 1),
                )
                if workout_date > today:
                    future_count += 1
            logger.info(
                "map_runs_to_plan: 0 candidates — %d future, %d already linked, "
                "%d total workouts",
                future_count, linked_count, len(daily_workouts),
            )
            return {
                "mapped": 0, "proposals": [],
                "message": "No unmapped past workouts found.",
                "debug": {
                    "total_user_runs": total_user_runs,
                    "total_workouts": len(daily_workouts),
                    "already_linked": linked_count,
                    "future": future_count,
                    "start_date": str(start_date),
                    "today": str(today),
                },
            }

        # Get runs available for (re-)mapping.  This includes:
        #   1. Fresh runs not linked to any plan (training_plan_id IS NULL)
        #   2. Runs linked to a different plan (can be re-mapped)
        #   3. Runs already on THIS plan but volume-only (daily_workout_id
        #      IS NULL) — these can be upgraded to workout matches when the
        #      user re-maps after shifting workouts around.
        unlinked_runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
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
            "map_runs_to_plan: %d unlinked runs available (not linked to plan %s)",
            len(unlinked_runs), plan_id[:8],
        )
        if unlinked_runs:
            run_dates = sorted(set(str(_to_date(r.date)) for r in unlinked_runs[:20]))
            logger.info("map_runs_to_plan: sample run dates = %s", run_dates[:10])

        if not unlinked_runs:
            # All runs are already linked to this plan
            linked_to_this_plan = db.query(func.count(RunLog.id)).filter(
                RunLog.user_id == user_id,
                RunLog.training_plan_id == plan_id,
            ).scalar()
            logger.info(
                "map_runs_to_plan: 0 unlinked runs — %d already linked to this plan",
                linked_to_this_plan,
            )
            return {
                "mapped": 0, "proposals": [],
                "message": "No unlinked runs to map.",
                "debug": {
                    "total_user_runs": total_user_runs,
                    "workout_candidates": len(workout_candidates),
                    "already_linked_to_this_plan": linked_to_this_plan,
                },
            }

        # Index runs by date for fast lookup
        from collections import defaultdict
        runs_by_date: Dict[any, list] = defaultdict(list)
        for run in unlinked_runs:
            run_date = _to_date(run.date)
            runs_by_date[run_date].append(run)

        proposals = []
        used_run_ids = set()

        def _match_score(date_penalty: float, dist_diff: float) -> float:
            """Combined score balancing date proximity and distance similarity.

            Each day offset costs 3 points, so a 1-day shift is equivalent to
            a 3 km distance mismatch.  This prevents a same-day run with a huge
            distance gap from beating a 1-day-off run with near-perfect distance
            — the main cause of mis-mappings reported by users.
            """
            return date_penalty * 3.0 + dist_diff

        # --- First pass: build all candidate edges, then greedily assign ---
        # Collect (score, workout_index, run) triples for global sorting so
        # that the best overall edges are assigned first instead of letting
        # early workouts "steal" runs from later, better matches.
        all_edges: list[tuple[float, int, object, int, object]] = []
        #                    score, wo_idx, workout,  week_number, run

        for wo_idx, (workout, week_number, workout_date) in enumerate(
            sorted(workout_candidates, key=lambda x: x[2])
        ):
            for offset in [0, -1, 1, -2, 2]:
                check_date = workout_date + timedelta(days=offset)
                for run in runs_by_date.get(check_date, []):
                    date_penalty = abs(offset)
                    dist_diff = abs(
                        (run.distance_km or 0) - (workout.distance_km or 0)
                    )
                    score = _match_score(date_penalty, dist_diff)
                    all_edges.append(
                        (score, wo_idx, workout, week_number, run, workout_date)
                    )

        # Sort by score (best first) and greedily assign — this gives the
        # globally best edges priority rather than letting chronologically
        # earlier workouts claim runs that would be a much better fit later.
        all_edges.sort(key=lambda e: e[0])
        matched_wo_indices: set[int] = set()

        for score, wo_idx, workout, week_number, run, workout_date in all_edges:
            if wo_idx in matched_wo_indices or run.id in used_run_ids:
                continue
            matched_wo_indices.add(wo_idx)
            used_run_ids.add(run.id)

            run_date = _to_date(run.date)
            proposals.append({
                "run_id": run.id,
                "workout_id": workout.id,
                "week": week_number,
                "day": workout.day_of_week,
                "workout_type": workout.workout_type,
                "planned_distance": workout.distance_km,
                "actual_distance": run.distance_km,
                "run_date": str(run_date),
                "workout_date": str(workout_date),
                "match_type": "workout",
            })

        # --- Weekly pass ---
        # Runs that weren't matched in the ±2-day workout pass are matched
        # here using a full-week window.  When an unmatched run falls in a
        # training week that still has unmatched workouts, pair them by
        # distance similarity (so a shifted Tuesday tempo run still counts
        # as completing the Thursday tempo workout).  Remaining runs with
        # no workout to pair get linked as volume-only.
        matched_workout_ids = {
            p["workout_id"] for p in proposals if p["workout_id"]
        }
        unmatched_workouts_by_week: Dict[int, list] = defaultdict(list)
        for workout, week_number, workout_date in workout_candidates:
            if workout.id not in matched_workout_ids:
                unmatched_workouts_by_week[week_number].append(
                    (workout, workout_date)
                )

        weekly_plans = (
            db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        )
        for wp in weekly_plans:
            week_start = start_date + timedelta(weeks=(wp.week_number - 1))
            week_end = week_start + timedelta(days=6)
            if week_start > today:
                continue

            # Collect unmatched runs in this week
            week_runs = []
            for d in range((min(week_end, today) - week_start).days + 1):
                check_date = week_start + timedelta(days=d)
                for run in runs_by_date.get(check_date, []):
                    if run.id not in used_run_ids:
                        week_runs.append(run)

            for run in week_runs:
                if run.id in used_run_ids:
                    continue

                run_date = _to_date(run.date)

                # Try to pair with the closest unmatched workout in this week
                best_wo = None
                best_score = float("inf")
                for wo, wo_date in unmatched_workouts_by_week.get(
                    wp.week_number, []
                ):
                    if wo.id in matched_workout_ids:
                        continue
                    date_diff = abs((run_date - wo_date).days)
                    dist_diff = abs(
                        (run.distance_km or 0) - (wo.distance_km or 0)
                    )
                    score = _match_score(date_diff, dist_diff)
                    if score < best_score:
                        best_score = score
                        best_wo = (wo, wo_date)

                used_run_ids.add(run.id)

                if best_wo:
                    wo, wo_date = best_wo
                    matched_workout_ids.add(wo.id)
                    proposals.append({
                        "run_id": run.id,
                        "workout_id": wo.id,
                        "week": wp.week_number,
                        "day": wo.day_of_week,
                        "workout_type": wo.workout_type,
                        "planned_distance": wo.distance_km,
                        "actual_distance": run.distance_km,
                        "run_date": str(run_date),
                        "workout_date": str(wo_date),
                        "match_type": "workout",
                    })
                else:
                    proposals.append({
                        "run_id": run.id,
                        "workout_id": None,
                        "week": wp.week_number,
                        "day": None,
                        "workout_type": None,
                        "planned_distance": None,
                        "actual_distance": run.distance_km,
                        "run_date": str(run_date),
                        "workout_date": None,
                        "match_type": "weekly_volume",
                    })

        # --- Rest/recovery pass ---
        # Runs matched as volume-only may actually fall on a rest or recovery
        # day.  Linking them to that workout makes them visible on the plan
        # card so the user sees "I ran on a rest day" instead of the run
        # silently disappearing.
        rest_candidates = []
        for workout, week_number in rest_recovery_workouts:
            if workout.id in already_linked_ids:
                continue
            workout_date = start_date + timedelta(
                weeks=(week_number - 1),
                days=(workout.day_of_week - 1),
            )
            if workout_date > today:
                continue
            rest_candidates.append((workout, week_number, workout_date))

        if rest_candidates:
            rest_by_date: Dict[any, tuple] = {}
            for workout, week_number, workout_date in rest_candidates:
                # Keep one rest workout per date (first wins — usually only one)
                if workout_date not in rest_by_date:
                    rest_by_date[workout_date] = (workout, week_number, workout_date)

            matched_rest_ids: set = set()
            for i, p in enumerate(proposals):
                if p["match_type"] != "weekly_volume":
                    continue
                run_date_str = p["run_date"]
                # Try exact date, then ±1 day
                try:
                    rd = datetime.strptime(run_date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                for offset in [0, -1, 1]:
                    check = rd + timedelta(days=offset)
                    rest_match = rest_by_date.get(check)
                    if rest_match and rest_match[0].id not in matched_rest_ids:
                        wo, wn, wd = rest_match
                        matched_rest_ids.add(wo.id)
                        # Upgrade volume-only → rest-day workout match
                        proposals[i] = {
                            **p,
                            "workout_id": wo.id,
                            "week": wn,
                            "day": wo.day_of_week,
                            "workout_type": wo.workout_type,
                            "planned_distance": wo.distance_km,
                            "workout_date": str(wd),
                            "match_type": "workout",
                        }
                        break

        if not proposals:
            candidate_dates = sorted(str(wd) for _, _, wd in workout_candidates[:10])
            run_dates = sorted(set(str(_to_date(r.date)) for r in unlinked_runs[:20]))
            logger.info(
                "map_runs_to_plan: 0 proposals — candidate dates: %s, run dates: %s",
                candidate_dates, run_dates[:10],
            )
            return {
                "mapped": 0, "proposals": [],
                "message": "No matching runs found for unmapped workouts.",
                "debug": {
                    "workout_candidate_dates": candidate_dates,
                    "run_dates": run_dates[:10],
                    "workout_candidates_count": len(workout_candidates),
                    "unlinked_runs_count": len(unlinked_runs),
                },
            }

        if dry_run:
            return {"mapped": 0, "proposals": proposals, "dry_run": True}

        # Apply mappings — build lookup dict to avoid per-proposal queries
        proposal_run_ids = [p["run_id"] for p in proposals]
        runs_by_id = {
            r.id: r
            for r in db.query(RunLog).filter(RunLog.id.in_(proposal_run_ids)).all()
        }
        for p in proposals:
            run = runs_by_id.get(p["run_id"])
            if run:
                # Clear any stale daily_workout_id from a previous plan first,
                # then set if this proposal has a direct workout match.
                run.daily_workout_id = (
                    p["workout_id"] if p["match_type"] == "workout" else None
                )
                # Both types get linked to the plan for volume tracking
                run.training_plan_id = plan_id

        db.commit()

        return {
            "mapped": len(proposals),
            "proposals": proposals,
        }

    # ------------------------------------------------------------------
    # Feature: Plan recalibration based on actual adherence
    # ------------------------------------------------------------------

    def _calculate_weekly_volume_adherence(
        self,
        training_plan: "TrainingPlan",
        current_week: int,
        db: Session,
    ) -> float:
        """Calculate adherence based on weekly volume rather than per-workout.

        For each completed week, compares total actual km (all linked runs)
        against the WeeklyPlan.total_km.  A week with actual >= 80% of planned
        counts as "volume met".

        Returns ratio of volume-met weeks / total past weeks, as a percentage.
        """
        if not training_plan.start_date:
            return 0.0

        start_date = _to_date(training_plan.start_date)
        plan_id = training_plan.id

        past_weeks = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number < current_week,
            )
            .all()
        )
        if not past_weeks:
            return 0.0

        # Single query: fetch all runs for the plan, bucket by week in Python
        all_runs = (
            db.query(RunLog.date, RunLog.distance_km)
            .filter(RunLog.training_plan_id == plan_id)
            .all()
        )
        weekly_actual: Dict[int, float] = defaultdict(float)
        for run_date, dist in all_runs:
            rd = _to_date(run_date)
            if rd and start_date:
                delta = (rd - start_date).days
                if delta >= 0:
                    wk = delta // 7 + 1
                    weekly_actual[wk] += dist or 0.0

        volume_met = 0
        for week in past_weeks:
            planned_km = week.total_km or 0
            actual_km = weekly_actual.get(week.week_number, 0.0)
            if planned_km > 0 and actual_km >= planned_km * 0.8:
                volume_met += 1

        return (volume_met / len(past_weeks) * 100) if past_weeks else 0.0

    def recalibrate_plan(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
    ) -> Dict[str, any]:
        """Recalibrate future plan weeks based on adherence, volume, and effort.

        Combines three signals into a single multiplier:
        1. Workout adherence (per-workout completion) — blended with volume adherence
        2. Volume adherence (weekly total km vs planned) — gives credit for rescheduled runs
        3. Perceived effort trend — biases multiplier when effort is too high/low

        Computes from baseline_distance_km to prevent compounding across
        repeated calls or with Strava adaptation.

        Logic:
        - Combined adherence >= 90%: nudge up 5%
        - 70-89%: keep as-is
        - 50-69%: reduce 10%
        - < 50%: reduce 15%
        - Effort bias: avg >= 9 → -0.05, avg <= 3 → +0.05, increasing + avg > 7 → -0.03
        - Final multiplier clamped to [0.80, 1.15]
        """
        training_plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user_id,
        ).first()

        if not training_plan:
            return {"recalibrated": False, "reason": "Plan not found", "changes": []}

        if not training_plan.start_date:
            return {"recalibrated": False, "reason": "Plan has no start date.", "changes": []}

        # Backfill baselines for legacy plans
        self._backfill_baselines(training_plan, db)

        start_date = _to_date(training_plan.start_date)
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        days_elapsed = (today - start_date).days
        current_week = max(1, days_elapsed // 7 + 1)

        # --- Workout adherence ---
        past_workouts = (
            db.query(DailyWorkout, WeeklyPlan.week_number)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan_id,
                WeeklyPlan.week_number < current_week,
                DailyWorkout.workout_type.notin_(["rest", "recovery"]),
            )
            .all()
        )

        if not past_workouts:
            return {
                "recalibrated": False,
                "reason": "No completed weeks to analyse yet.",
                "changes": [],
            }

        workout_ids = [w.id for w, _ in past_workouts]
        linked_runs = (
            db.query(RunLog)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.in_(workout_ids),
            )
            .all()
        )
        linked_map = {r.daily_workout_id: r for r in linked_runs}

        total_planned = len(past_workouts)
        completed = len(linked_map)
        workout_adherence = (completed / total_planned * 100) if total_planned > 0 else 0

        # --- Volume adherence ---
        volume_adherence = self._calculate_weekly_volume_adherence(training_plan, current_week, db)

        # Blend: 50/50
        combined_adherence = 0.5 * workout_adherence + 0.5 * volume_adherence

        # Compare planned vs actual volume for completed workouts
        planned_km_total = sum(w.distance_km or 0 for w, _ in past_workouts if w.id in linked_map)
        actual_km_total = sum(r.distance_km or 0 for r in linked_runs)
        volume_ratio = (actual_km_total / planned_km_total) if planned_km_total > 0 else 1.0

        # --- Adherence-based multiplier ---
        if combined_adherence >= 90:
            base_mult = 1.05
        elif combined_adherence >= 70:
            base_mult = 1.0
        elif combined_adherence >= 50:
            base_mult = 0.90
        else:
            base_mult = 0.85

        # Adjust for actual volume
        if volume_ratio > 1.1 and base_mult < 1.1:
            base_mult = min(base_mult + 0.05, 1.15)
        elif volume_ratio < 0.8 and base_mult > 0.85:
            base_mult = max(base_mult - 0.05, 0.80)

        # --- Effort bias (Phase 4) ---
        plan_runs = (
            db.query(RunLog)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.perceived_effort.isnot(None),
            )
            .order_by(RunLog.date)
            .all()
        )
        efforts = [r.perceived_effort for r in plan_runs]
        avg_effort = sum(efforts) / len(efforts) if efforts else None
        effort_trend = self._analyze_effort_trend(efforts)

        if avg_effort is not None:
            if avg_effort >= 9:
                base_mult -= 0.05
            elif avg_effort <= 3:
                base_mult += 0.05
            if effort_trend == "increasing" and avg_effort > 7:
                base_mult -= 0.03

        # Clamp
        multiplier = round(max(0.80, min(1.15, base_mult)), 2)

        strava_mult = training_plan.strava_adapted_multiplier or 1.0

        # Get future weeks
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
                "recalibrated": False,
                "reason": "No future weeks remaining to recalibrate.",
                "adherence_pct": round(combined_adherence, 1),
                "changes": [],
            }

        plan_data, pd_week, pd_workout = self._parse_plan_data_lookups(training_plan)
        _recal_re = re.compile(r"\s*\(Recalibrated:[^)]*\)")

        workouts_by_week = self._batch_workouts_by_week(
            [week.id for week in future_weeks], db
        )

        changes = []
        for week in future_weeks:
            workouts = workouts_by_week.get(week.id, [])

            week_changes = []
            for workout in workouts:
                if workout.workout_type != "rest" and workout.distance_km and workout.distance_km > 0:
                    # Compute from baseline: baseline * strava_mult * recal_mult
                    base_distance = workout.baseline_distance_km or workout.distance_km
                    new_distance = max(1.0, round(base_distance * strava_mult * multiplier, 1))
                    old_distance = workout.distance_km

                    if new_distance == old_distance:
                        continue

                    workout.distance_km = new_distance
                    recal_note = f"(Recalibrated: {round(base_distance, 1)}->{new_distance}km, {round(combined_adherence)}% adherence)"

                    clean_notes = _recal_re.sub("", workout.notes or "").strip()
                    workout.notes = f"{clean_notes} {recal_note}".strip() if clean_notes else recal_note

                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo is not None:
                        pd_wo["distance"] = new_distance
                        pd_clean = _recal_re.sub(
                            "", pd_wo.get("notes", pd_wo.get("description", ""))
                        ).strip()
                        pd_wo["notes"] = f"{pd_clean} {recal_note}".strip() if pd_clean else recal_note

                    week_changes.append({
                        "day": workout.day_of_week,
                        "workout_type": workout.workout_type,
                        "old_distance": old_distance,
                        "new_distance": new_distance,
                    })

            if week_changes:
                new_total = round(sum(w.distance_km for w in workouts if w.distance_km), 1)
                week.total_km = new_total
                if week.week_number in pd_week:
                    pd_week[week.week_number]["total_km"] = new_total
                changes.append({
                    "week": week.week_number,
                    "workouts_adjusted": week_changes,
                    "new_total_km": new_total,
                })

        if not changes:
            return {
                "recalibrated": False,
                "reason": "Distances already match your current performance.",
                "adherence_pct": round(combined_adherence, 1),
                "multiplier": multiplier,
                "avg_effort": round(avg_effort, 1) if avg_effort else None,
                "effort_trend": effort_trend,
                "changes": [],
            }

        # Persist multiplier and plan data
        training_plan.recalibration_multiplier = multiplier
        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        direction = "increased" if multiplier > 1.0 else "reduced" if multiplier < 1.0 else "kept"
        first_wk = changes[0]["week"]
        last_wk = changes[-1]["week"]

        reason_parts = [
            f"Weeks {first_wk}-{last_wk} {direction} based on "
            f"{round(combined_adherence)}% adherence ({completed}/{total_planned} workouts, "
            f"{round(volume_adherence)}% weekly volume met)."
        ]
        if avg_effort is not None:
            reason_parts.append(f"Avg effort: {round(avg_effort, 1)}/10 ({effort_trend}).")

        return {
            "recalibrated": True,
            "reason": " ".join(reason_parts),
            "adherence_pct": round(combined_adherence, 1),
            "workout_adherence_pct": round(workout_adherence, 1),
            "volume_adherence_pct": round(volume_adherence, 1),
            "completed": completed,
            "total_planned": total_planned,
            "volume_ratio": round(volume_ratio, 2),
            "multiplier": multiplier,
            "avg_effort": round(avg_effort, 1) if avg_effort else None,
            "effort_trend": effort_trend,
            "changes": changes,
        }
