"""
Performance Training Plan Generator

Generates speed-focused training plans for experienced runners targeting
race time improvements.  Delegates to shared core modules for periodization
and mileage progression, then layers performance-specific pace zones and
segment-based workout structure.
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training import mileage_progression, phase_calculator
from app.core.training.goal_pace_model import (
    GoalPaceContext,
    goal_vdot_from_time,
    progressive_pace_zones,
)
from app.core.training.strength_plan import derive_experience_level
from app.core.training.training_constants import calculate_week_in_phase
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_builders import attach_strength_sessions

from .base_plan_generator import BasePlanGenerator
from .performance_workout_builders import (
    generate_fartlek_workout,
    generate_long_run,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_vo2max_workout,
)
from .phase_scaffold import build_phases_rich
from .segment_steps import apply_steps_model

logger = logging.getLogger(__name__)

# Performance-specific phase metadata (quality_percent drives how many
# quality sessions appear each week; descriptions shown in the UI).
_PHASE_METADATA = {
    "base": {"quality_percent": 30, "description": "Build aerobic foundation"},
    "build": {"quality_percent": 50, "description": "Add intensity and volume"},
    "peak": {"quality_percent": 60, "description": "Peak intensity and sharpness"},
    "taper": {
        "quality_percent": 40,
        "description": "Reduce volume, maintain sharpness",
    },
}

# Map performance workout types to KeyWorkoutLibrary types for overlay.
# Fartlek has no library equivalent and stays formulaic.
_LIBRARY_TYPE_MAP = {
    "vo2max": "interval",
    "tempo": "tempo",
    "race_pace": "tempo",
}

# Map performance workout types to coaching-note types (the coaching notes
# generator uses regular plan type names).
_COACHING_TYPE_MAP = {
    "vo2max": "interval",
    "race_pace": "tempo",
    "fartlek": "interval",
}


class PerformancePlanGenerator(BasePlanGenerator):
    """Generates performance-focused training plans with pace-based zones.

    Delegates to the same core modules as TrainingPlanGenerator:
    - phase_calculator: distance-aware phase distribution with recovery weeks
    - mileage_progression: 10% rule enforcement with VDOT-adjusted peak
    - key_workout_library: curated race-specific workouts (build/peak phases)

    Adds performance-specific value:
    - 5-zone pace-based training zones (with optional HR)
    - Segment-based workout structure for zone visualization

    Shared weekly-assembly machinery (easy-run scheduling, rest padding, key
    workout overlay, and quality structural caps) lives in BasePlanGenerator.
    """

    LIBRARY_TYPE_MAP = _LIBRARY_TYPE_MAP

    PHASE_QUALITY_PRIORITY = {
        "base": ["tempo", "fartlek"],
        "build": ["tempo", "vo2max"],
        "peak": ["vo2max", "race_pace"],
        "taper": ["race_pace", "tempo"],
    }

    def calculate_training_zones(
        self,
        goal_pace: float,
        max_hr: Optional[int] = None,
        vdot_zones: Optional[Dict] = None,
        race_distance_km: Optional[float] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate 5 training zones based on goal pace and optionally max HR.

        Delegates to the shared zone_calculator. The performance plan anchors
        zone 5 to the user's chosen `goal_pace` rather than VDOT-derived
        marathon pace; `race_distance_km` lets the race-pace band carry the HR
        effort that distance is actually run at.
        """
        from app.core.training.zone_calculator import calculate_zones

        return calculate_zones(
            vdot_zones=vdot_zones,
            goal_pace=goal_pace,
            max_hr=max_hr,
            race_distance_km=race_distance_km,
        )

    # ------------------------------------------------------------------
    # Weekly plan assembly
    # ------------------------------------------------------------------

    def _generate_weekly_plan(
        self,
        week_number: int,
        phase: str,
        phases_rich: Dict,
        zones: Dict,
        weekly_km: float,
        target_distance: float,
        runs_per_week: int,
        is_recovery: bool,
        vdot_zones: Optional[Dict] = None,
        week_in_phase: int = 0,
        experience_level: str = "intermediate",
    ) -> Dict[str, Any]:
        quality_percent = phases_rich[phase]["quality_percent"]

        if is_recovery:
            # Recovery weeks: at most 1 light quality session
            quality_workouts_needed = 1 if runs_per_week >= 4 else 0
        else:
            quality_workouts_needed = max(1, int(runs_per_week * quality_percent / 100))

        daily_workouts = []
        total_assigned_km = 0

        workout_schedule = []

        # Long run on Saturday (day 6)
        workout_schedule.append(
            {
                "day": 6,
                "workout_generator": lambda: generate_long_run(
                    zones, weekly_km, week_number, phase, target_distance
                ),
            }
        )

        # Quality workouts on Tuesday (day 2) and Friday (day 5)
        if quality_workouts_needed > 0:
            quality_days = [2, 4] if runs_per_week >= 4 else [2]
            quality_types = self.PHASE_QUALITY_PRIORITY.get(phase, ["tempo", "vo2max"])

            _generators = {
                "tempo": lambda: generate_tempo_workout(
                    zones, weekly_km, week_number, phase
                ),
                "vo2max": lambda: generate_vo2max_workout(
                    zones, weekly_km, week_number, phase
                ),
                "race_pace": lambda: generate_race_pace_workout(
                    zones, weekly_km, week_number, phase, target_distance
                ),
                "fartlek": lambda: generate_fartlek_workout(
                    zones, weekly_km, week_number, phase
                ),
            }

            for i, day in enumerate(quality_days[:quality_workouts_needed]):
                workout_type = quality_types[(week_number - 1 + i) % len(quality_types)]
                generator = _generators.get(workout_type, _generators["fartlek"])
                workout_schedule.append({"day": day, "workout_generator": generator})

        for item in workout_schedule:
            workout = item["workout_generator"]()
            workout["day"] = item["day"]
            daily_workouts.append(workout)
            total_assigned_km += workout["distance"]

        # Apply quality caps against the long run, then sync segments
        self._enforce_quality_caps(daily_workouts, target_distance, phase)
        total_assigned_km = sum(w["distance"] for w in daily_workouts)

        # Fill remaining days with well-spaced easy runs, then rest
        remaining_km = weekly_km - total_assigned_km
        self._fill_easy_runs(daily_workouts, zones, runs_per_week, remaining_km)
        self._fill_rest_days(daily_workouts)

        # Overlay key workouts and coaching rationale.
        # _enforce_quality_caps above already synced segments and description;
        # overlay then replaces description + steps with curated key-workout
        # content, bounded to a long-run-relative ceiling so a fixed
        # prescription never balloons past the week's long run.
        quality_ceiling = self._key_workout_ceiling(daily_workouts)
        quality_slot_counts: Dict[str, int] = {}
        for workout in daily_workouts:
            if workout.get("quality", False):
                # Second same-type quality slot in a week rotates to a
                # different library session instead of duplicating the first.
                wtype = str(workout["type"])
                slot_index = quality_slot_counts.get(wtype, 0)
                quality_slot_counts[wtype] = slot_index + 1
                self._overlay_key_workout(
                    workout,
                    phase,
                    target_distance,
                    week_in_phase,
                    vdot_zones,
                    max_distance=quality_ceiling,
                    slot_index=slot_index,
                    weekly_km=weekly_km,
                )
            wtype = str(workout["type"])
            coaching_type = _COACHING_TYPE_MAP.get(wtype, wtype)
            workout["coaching_rationale"] = generate_coaching_note(
                coaching_type,
                phase,
                week_number,
                target_distance,
                is_recovery,
                pace_zones=vdot_zones,
            )

        # Unify the representation: the formulaic base/easy/long/fartlek
        # sessions are still segment-based at this point (caps and prose were
        # reconciled against segments above); project them onto the same
        # structured steps model the curated overlay and road generator emit so
        # every stored workout renders, enriches, and adapts identically.
        apply_steps_model(daily_workouts, target_distance)

        strength_sessions = attach_strength_sessions(
            daily_workouts,
            week_number,
            phase,
            experience_level=experience_level,
            target_distance=target_distance,
        )

        actual_total_km = sum(w["distance"] for w in daily_workouts)
        is_valid, validation_msg = self._validate_week_plan(
            daily_workouts, actual_total_km, weekly_km
        )

        return {
            "week": week_number,
            "phase": phase,
            "phase_description": phases_rich[phase]["description"],
            "is_recovery": is_recovery,
            "total_km": round(actual_total_km, 1),
            "quality_workouts": sum(
                1 for w in daily_workouts if w.get("quality", False)
            ),
            "daily_workouts": daily_workouts,
            "strength_training": strength_sessions,
            "validation": {"valid": is_valid, "message": validation_msg},
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_week_plan(
        workouts: List[Dict], total_km: float, target_km: float
    ) -> tuple:
        """Validate a week's workouts follow training principles."""
        long_runs = [w for w in workouts if w["type"] == "long"]
        long_dist = long_runs[0]["distance"] if long_runs else 0

        for workout in workouts:
            if workout.get("quality", False) and workout["distance"] > long_dist * 1.1:
                return False, (
                    f"Quality workout {workout['type']} ({workout['distance']:.1f}km) "
                    f"exceeds long run ({long_dist:.1f}km)"
                )

            if workout["type"] == "easy" and 0 < workout["distance"] < 2.0:
                return False, f"Easy run too short ({workout['distance']:.1f}km)"

            # Sanity-check that the rendered structure (steps or segments)
            # totals the workout's distance. Logs at debug; never blocks plan.
            wdist = workout.get("distance", 0)
            if wdist > 0:
                steps = workout.get("steps") or []
                if steps:
                    step_total_m = sum(
                        (s.get("distance_m") or 0) * s.get("repeat", 1) for s in steps
                    )
                    if step_total_m > 0 and abs(step_total_m / 1000 - wdist) > 1.0:
                        logger.debug(
                            "Step total %.1fkm != workout distance %.1fkm for %s",
                            step_total_m / 1000,
                            wdist,
                            workout.get("type"),
                        )
                else:
                    segs = workout.get("segments") or []
                    if segs:
                        seg_total = sum(s.get("distance_km", 0) for s in segs)
                        if abs(seg_total - wdist) > 0.5:
                            logger.debug(
                                "Segment total %.1fkm != workout distance %.1fkm for %s",
                                seg_total,
                                wdist,
                                workout.get("type"),
                            )

        tolerance = target_km * 0.15
        if total_km < target_km - tolerance:
            return (
                False,
                f"Volume shortfall: target {target_km:.1f}km, got {total_km:.1f}km",
            )

        return True, "Valid"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        target_distance: float,
        current_pace: float,
        goal_pace: float,
        weeks: int,
        current_weekly_km: float,
        runs_per_week: int = 5,
        max_heart_rate: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a complete performance training plan."""
        if goal_pace >= current_pace:
            raise ValueError("Goal pace must be faster than current pace")

        improvement = (current_pace - goal_pace) / current_pace
        if improvement > 0.15:
            raise ValueError("Goal pace improvement >15% is not realistic")

        weeks = max(6, min(16, weeks))

        # --- Shared modules: phase calculation & mileage progression ---
        phase_durations = phase_calculator.calculate_phases(weeks, target_distance)
        phases_rich = build_phases_rich(phase_durations, _PHASE_METADATA)

        # --- VDOT & pace zones (goal-aware, progressive) ---
        # Current fitness anchors the early weeks; a goal VDOT (implied by the
        # goal pace at the target distance) anchors race weeks. Each week trains
        # off a VDOT blended between the two, so every training pace — easy,
        # threshold, interval — sharpens toward the goal across the block rather
        # than sitting at the runner's current fitness. Race-pace work stays
        # pinned to the exact goal pace (handled in calculate_training_zones).
        vdot = None
        vdot_zones = None
        if current_pace:
            implied_seconds = int(current_pace * target_distance * 60)
            vdot = VDOTCalculator.calculate_vdot(target_distance, implied_seconds)
            if vdot:
                vdot_zones = VDOTCalculator.get_pace_zones(vdot)

        goal_seconds = int(goal_pace * target_distance * 60)
        goal_vdot = goal_vdot_from_time(target_distance, goal_seconds)
        goal_ctx = GoalPaceContext(
            current_vdot=vdot,
            goal_vdot=goal_vdot,
            goal_pace_min_km=goal_pace,
            target_distance_km=target_distance,
        )

        def _zones_for_week(week_num: int):
            """Blended VDOT zones (and 5-band table) for a given plan week."""
            week_vdot_zones = (
                progressive_pace_zones(goal_ctx, week_num, weeks) or vdot_zones
            )
            week_zones = self.calculate_training_zones(
                goal_pace, max_heart_rate, vdot_zones=week_vdot_zones
            )
            return week_zones, week_vdot_zones

        # Shared mileage progression (10% rule, recovery weeks, VDOT-adjusted peak)
        km_progression = mileage_progression.calculate_weekly_progression(
            current_weekly_km,
            target_distance,
            weeks,
            runs_per_week,
            vdot=vdot,
        )

        experience_level = derive_experience_level(current_weekly_km)

        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = phase_calculator.get_phase(week_num, phase_durations)
            is_recovery = phase_calculator.is_recovery_week(
                week_num, phase, phase_durations
            )

            week_in_phase = calculate_week_in_phase(week_num, phase, phase_durations)

            week_zones, week_vdot_zones = _zones_for_week(week_num)
            weekly_plan = self._generate_weekly_plan(
                week_num,
                phase,
                phases_rich,
                week_zones,
                km_progression[week_num - 1],
                target_distance,
                runs_per_week,
                is_recovery,
                vdot_zones=week_vdot_zones,
                week_in_phase=week_in_phase,
                experience_level=experience_level,
            )
            weekly_plans.append(weekly_plan)

        # Representative zone table for the generate-response / summary: the
        # final week's zones, i.e. paces at full goal fitness.
        zones, _ = _zones_for_week(weeks)

        total_km = sum(week["total_km"] for week in weekly_plans)
        total_quality_workouts = sum(week["quality_workouts"] for week in weekly_plans)

        return {
            "target_distance": target_distance,
            "current_pace": current_pace,
            "goal_pace": goal_pace,
            "weeks": weeks,
            "runs_per_week": runs_per_week,
            "training_zones": zones,
            "phases": phases_rich,
            "vdot": vdot,
            "weekly_plans": weekly_plans,
            "summary": {
                "total_weeks": weeks,
                "total_km": round(total_km, 1),
                "avg_weekly_km": round(total_km / weeks, 1),
                "total_quality_workouts": total_quality_workouts,
                "improvement_target": f"{improvement * 100:.1f}%",
            },
        }
