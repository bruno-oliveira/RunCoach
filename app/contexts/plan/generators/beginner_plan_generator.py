"""Couch to 5K style beginner plan generator for true beginners."""

from typing import Any, Dict, List

BEGINNER_WEEKS = {
    1: {
        "run": 1,
        "walk": 1.5,
        "repeats": 8,
        "total_min": 20,
        "notes": "Week 1: Run 1 minute, Walk 1.5 minutes. Repeat 8 times (20 min total).",
    },
    2: {
        "run": 1.5,
        "walk": 2,
        "repeats": 6,
        "total_min": 21,
        "notes": "Week 2: Run 1.5 minutes, Walk 2 minutes. Repeat 6 times (21 min total).",
    },
    3: {
        "run": 3,
        "walk": 3,
        "repeats": 4,
        "total_min": 24,
        "notes": "Week 3: Run 3 minutes, Walk 3 minutes. Repeat 4 times (24 min total).",
    },
    4: {
        "run": 5,
        "walk": 3,
        "repeats": 4,
        "total_min": 32,
        "notes": "Week 4: Run 5 minutes, Walk 3 minutes. Repeat 4 times (32 min total).",
    },
    5: {
        "run": 8,
        "walk": 5,
        "repeats": 3,
        "total_min": 39,
        "notes": "Week 5: Run 8 minutes, Walk 5 minutes. Repeat 3 times (39 min total).",
    },
    6: {
        "run": 10,
        "walk": 3,
        "repeats": 3,
        "total_min": 39,
        "notes": "Week 6: Run 10 minutes, Walk 3 minutes. Repeat 3 times (39 min total).",
    },
    7: {
        "run": 15,
        "walk": 3,
        "repeats": 2,
        "total_min": 36,
        "notes": "Week 7: Run 15 minutes, Walk 3 minutes. Repeat 2 times (36 min total).",
    },
    8: {
        "run": 20,
        "walk": 2,
        "repeats": 1,
        "total_min": 30,
        "notes": "Week 8: Run 20 minutes, Walk 2 minutes, Run 8 minutes (30 min total). Almost there!",
    },
    9: {
        "run": 25,
        "walk": 0,
        "repeats": 1,
        "total_min": 25,
        "notes": "Week 9: Run 25 minutes continuously. You can do this!",
    },
    10: {
        "run": 30,
        "walk": 0,
        "repeats": 1,
        "total_min": 30,
        "notes": "Week 10: Run 30 minutes continuously - you did it!",
    },
}

# Compressed progression for shorter C25K portions.
# Merges early weeks to preserve the critical run/walk-to-continuous transition.
_COMPRESSED_WEEKS = {
    4: [1, 4, 7, 10],
    5: [1, 3, 5, 8, 10],
    6: [1, 3, 5, 7, 8, 10],
    7: [1, 3, 4, 5, 7, 8, 10],
    8: [1, 3, 4, 5, 6, 7, 8, 10],
    9: [1, 3, 4, 5, 6, 7, 8, 9, 10],
}

BEGINNER_TIPS = {
    "general": [
        "Listen to your body - rest if you feel pain (not just discomfort)",
        "Good shoes matter - visit a running store for a fitting",
        "Focus on time, not distance or pace",
        "Breathe rhythmically - try 3 steps in, 3 steps out",
    ],
    "early": [
        "It's okay to repeat a week if needed - there's no rush",
        "Walk briskly during walk segments - don't stop completely",
    ],
    "mid": [
        "You're building a habit - consistency matters more than speed",
        "Stay hydrated and eat well to support your training",
    ],
    "late_5k": [
        "You're almost there! Trust the process",
        "Start thinking about your 5K race day or celebration run",
    ],
    "late_10k": [
        "You're almost there! Trust the process",
        "Start thinking about your 10K race day or celebration run",
    ],
}


class BeginnerPlanGenerator:
    """Generate Couch to 5K style plans for true beginners."""

    def generate_plan(
        self,
        target_distance: float,
        weeks: int,
        max_runs_per_week: int = 3,
        estimated_pace_min_km: float = 8.0,
    ) -> List[Dict[str, Any]]:
        """
        Generate a beginner-friendly training plan.

        Args:
            target_distance: Race distance in km (5.0 or 10.0)
            weeks: Training duration in weeks (minimum 8)
            max_runs_per_week: Maximum runs per week (capped at 3 for beginners)
            estimated_pace_min_km: Estimated pace in min/km for distance calculations

        Returns:
            List of weekly plan dictionaries
        """
        max_runs = min(max_runs_per_week, 3)
        self._pace_min_km = max(4.0, min(15.0, estimated_pace_min_km))
        plan = []

        c25k_total = len(BEGINNER_WEEKS)  # 10 weeks

        if target_distance > 5.0:
            # 10K: compress C25K to reserve weeks for distance building
            max_c25k = min(8, c25k_total)
            extension_count = max(2, weeks - max_c25k)
            c25k_weeks_needed = weeks - extension_count
        else:
            # 5K: use all weeks for C25K
            c25k_weeks_needed = min(weeks, c25k_total)
            extension_count = 0

        # Build the C25K week sequence — compress if fewer than 10 weeks
        if c25k_weeks_needed < c25k_total and c25k_weeks_needed in _COMPRESSED_WEEKS:
            c25k_sequence = _COMPRESSED_WEEKS[c25k_weeks_needed]
        elif c25k_weeks_needed < c25k_total:
            c25k_sequence = list(
                range(c25k_total - c25k_weeks_needed + 1, c25k_total + 1)
            )
        else:
            c25k_sequence = list(range(1, c25k_total + 1))

        for i in range(c25k_weeks_needed):
            source_week = c25k_sequence[i]
            week_plan = self._generate_couch_to_5k_week(
                source_week,
                max_runs,
                display_week=i + 1,
                target_distance=target_distance,
            )
            plan.append(week_plan)

        # Extension weeks beyond C25K (10K distance building)
        for week in range(c25k_weeks_needed + 1, weeks + 1):
            week_plan = self._generate_10k_extension_week(
                week, target_distance, max_runs, weeks, c25k_weeks_needed
            )
            plan.append(week_plan)

        return plan

    def _generate_couch_to_5k_week(
        self,
        week_number: int,
        max_runs: int,
        display_week: int = 0,
        target_distance: float = 5.0,
    ) -> Dict[str, Any]:
        """Generate a single week for Couch to 5K plan."""
        week_config = BEGINNER_WEEKS.get(week_number, BEGINNER_WEEKS[10])
        display = display_week or week_number

        workouts = []
        days = self._get_workout_days(max_runs)

        for i, day in enumerate(days):
            workout = {
                "day": day,
                "type": "easy" if week_config["walk"] == 0 else "run_walk",
                "distance": 0,
                "intensity": "low",
                "notes": week_config["notes"],
                "duration_min": week_config["total_min"],
                "run_min": week_config["run"],
                "walk_min": week_config["walk"],
                "repeats": week_config["repeats"],
            }
            workouts.append(workout)

        assumed_pace_km_per_min = 1 / self._pace_min_km
        estimated_km = (
            round(
                week_config["total_min"]
                * assumed_pace_km_per_min
                * (week_config["run"] / (week_config["run"] + week_config["walk"]))
                * max_runs,
                1,
            )
            if week_config["run"] > 0
            else 0
        )

        return {
            "week": display,
            "total_km": estimated_km,
            "phase": "beginner",
            "daily_workouts": workouts,
            "training_tips": self._get_beginner_tips(week_number, target_distance),
            "is_beginner_plan": True,
            "workout_distribution": {"easy": max_runs, "rest": 7 - max_runs},
        }

    def _generate_10k_extension_week(
        self,
        week_number: int,
        target_distance: float,
        max_runs: int,
        total_weeks: int,
        c25k_length: int = 10,
    ) -> Dict[str, Any]:
        """Generate weeks beyond C25K for 10K beginner extension."""
        extension_week = week_number - c25k_length
        is_taper = week_number == total_weeks

        base_duration = min(60, 25 + (extension_week - 1) * 5)
        if is_taper:
            base_duration = int(base_duration * 0.6)

        workouts = []
        days = self._get_workout_days(max_runs)

        pace_km_per_min = 1 / self._pace_min_km
        for i, day in enumerate(days):
            if i == 0:
                workout = {
                    "day": day,
                    "type": "long",
                    "distance": round(base_duration * pace_km_per_min, 1),
                    "intensity": "low",
                    "notes": f"Week {week_number}: Long easy run - {base_duration} minutes continuous.",
                    "duration_min": base_duration,
                }
            elif i == 1:
                easy_duration = int(base_duration * 0.6)
                workout = {
                    "day": day,
                    "type": "easy",
                    "distance": round(easy_duration * pace_km_per_min, 1),
                    "intensity": "low",
                    "notes": f"Week {week_number}: Easy recovery run - {easy_duration} minutes.",
                    "duration_min": easy_duration,
                }
            else:
                tempo_duration = int(base_duration * 0.7)
                workout = {
                    "day": day,
                    "type": "tempo" if not is_taper else "easy",
                    "distance": round(tempo_duration * pace_km_per_min, 1),
                    "intensity": "medium" if not is_taper else "low",
                    "notes": f"Week {week_number}: {'Easy shakeout run' if is_taper else 'Run with 5-10 min slightly faster segment'}.",
                    "duration_min": tempo_duration,
                }
            workouts.append(workout)

        phase = "build" if extension_week <= 4 else "peak"
        if is_taper:
            phase = "taper"

        return {
            "week": week_number,
            "total_km": round(sum(w.get("distance", 0) for w in workouts), 1),
            "phase": phase,
            "daily_workouts": workouts,
            "training_tips": self._get_beginner_tips(week_number, target_distance),
            "is_beginner_plan": True,
            "workout_distribution": {
                "easy": max_runs - 1,
                "long": 1,
                "rest": 7 - max_runs,
            },
        }

    def _get_workout_days(self, max_runs: int) -> List[int]:
        """Get optimal workout days for beginners (spread throughout week)."""
        if max_runs == 3:
            return [1, 3, 5]
        elif max_runs == 2:
            return [1, 4]
        return [1, 3, 5, 7][:max_runs]

    def _get_beginner_tips(
        self, week_number: int, target_distance: float = 5.0
    ) -> List[str]:
        """Get beginner-appropriate training tips."""
        tips = BEGINNER_TIPS["general"].copy()

        if week_number <= 3:
            tips.extend(BEGINNER_TIPS["early"])
        elif week_number <= 6:
            tips.extend(BEGINNER_TIPS["mid"])
        else:
            late_key = "late_10k" if target_distance > 5.0 else "late_5k"
            tips.extend(BEGINNER_TIPS[late_key])

        return tips
