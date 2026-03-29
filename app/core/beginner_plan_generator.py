"""Couch to 5K style beginner plan generator for true beginners."""

from typing import Any, Dict, List


BEGINNER_WEEKS = {
    1: {"run": 1, "walk": 1.5, "repeats": 8, "total_min": 20,
        "notes": "Week 1: Run 1 minute, Walk 1.5 minutes. Repeat 8 times (20 min total)."},
    2: {"run": 1.5, "walk": 2, "repeats": 6, "total_min": 21,
        "notes": "Week 2: Run 1.5 minutes, Walk 2 minutes. Repeat 6 times (21 min total)."},
    3: {"run": 3, "walk": 3, "repeats": 4, "total_min": 24,
        "notes": "Week 3: Run 3 minutes, Walk 3 minutes. Repeat 4 times (24 min total)."},
    4: {"run": 5, "walk": 3, "repeats": 4, "total_min": 32,
        "notes": "Week 4: Run 5 minutes, Walk 3 minutes. Repeat 4 times (32 min total)."},
    5: {"run": 8, "walk": 5, "repeats": 3, "total_min": 39,
        "notes": "Week 5: Run 8 minutes, Walk 5 minutes. Repeat 3 times (39 min total)."},
    6: {"run": 10, "walk": 3, "repeats": 3, "total_min": 39,
        "notes": "Week 6: Run 10 minutes, Walk 3 minutes. Repeat 3 times (39 min total)."},
    7: {"run": 15, "walk": 3, "repeats": 2, "total_min": 36,
        "notes": "Week 7: Run 15 minutes, Walk 3 minutes. Repeat 2 times (36 min total)."},
    8: {"run": 20, "walk": 0, "repeats": 1, "total_min": 20,
        "notes": "Week 8: Run 20 minutes continuously - you did it!"},
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
    "late": [
        "You're almost there! Trust the process",
        "Start thinking about your 5K race day or celebration run",
    ],
}


class BeginnerPlanGenerator:
    """Generate Couch to 5K style plans for true beginners."""

    def generate_plan(self, target_distance: float, weeks: int,
                      max_runs_per_week: int = 3) -> List[Dict[str, Any]]:
        """
        Generate a beginner-friendly training plan.
        
        Args:
            target_distance: Race distance in km (5.0 or 10.0)
            weeks: Training duration in weeks (minimum 8)
            max_runs_per_week: Maximum runs per week (capped at 3 for beginners)
        
        Returns:
            List of weekly plan dictionaries
        """
        max_runs = min(max_runs_per_week, 3)
        plan = []

        for week in range(1, weeks + 1):
            if week <= 8:
                week_plan = self._generate_couch_to_5k_week(week, max_runs)
            else:
                week_plan = self._generate_10k_extension_week(
                    week, target_distance, max_runs, weeks
                )
            plan.append(week_plan)

        return plan

    def _generate_couch_to_5k_week(self, week_number: int,
                                    max_runs: int) -> Dict[str, Any]:
        """Generate a single week for Couch to 5K plan."""
        week_config = BEGINNER_WEEKS.get(week_number, BEGINNER_WEEKS[8])

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

        return {
            "week": week_number,
            "total_km": 0,
            "phase": "beginner",
            "daily_workouts": workouts,
            "training_tips": self._get_beginner_tips(week_number),
            "is_beginner_plan": True,
            "workout_distribution": {"easy": max_runs, "rest": 7 - max_runs},
        }

    def _generate_10k_extension_week(self, week_number: int, target_distance: float,
                                      max_runs: int, total_weeks: int) -> Dict[str, Any]:
        """Generate weeks 9+ for 10K beginner extension."""
        extension_week = week_number - 8
        base_duration = 25 + (extension_week - 1) * 5

        workouts = []
        days = self._get_workout_days(max_runs)

        for i, day in enumerate(days):
            if i == 0:
                workout = {
                    "day": day,
                    "type": "long",
                    "distance": round(base_duration * 0.1, 1),
                    "intensity": "low",
                    "notes": f"Week {week_number}: Long easy run - {base_duration} minutes continuous.",
                    "duration_min": base_duration,
                }
            elif i == 1:
                workout = {
                    "day": day,
                    "type": "easy",
                    "distance": round(base_duration * 0.06, 1),
                    "intensity": "low",
                    "notes": f"Week {week_number}: Easy recovery run - {int(base_duration * 0.6)} minutes.",
                    "duration_min": int(base_duration * 0.6),
                }
            else:
                workout = {
                    "day": day,
                    "type": "tempo",
                    "distance": round(base_duration * 0.07, 1),
                    "intensity": "medium",
                    "notes": f"Week {week_number}: Run with 5-10 min slightly faster segment.",
                    "duration_min": int(base_duration * 0.7),
                }
            workouts.append(workout)

        phase = "build" if extension_week <= 4 else "peak"
        if week_number == total_weeks:
            phase = "taper"

        return {
            "week": week_number,
            "total_km": round(sum(w.get("distance", 0) for w in workouts), 1),
            "phase": phase,
            "daily_workouts": workouts,
            "training_tips": self._get_beginner_tips(week_number),
            "is_beginner_plan": True,
            "workout_distribution": {"easy": max_runs - 1, "long": 1, "rest": 7 - max_runs},
        }

    def _get_workout_days(self, max_runs: int) -> List[int]:
        """Get optimal workout days for beginners (spread throughout week)."""
        if max_runs == 3:
            return [1, 3, 5]
        elif max_runs == 2:
            return [1, 4]
        return [1, 3, 5, 7][:max_runs]

    def _get_beginner_tips(self, week_number: int) -> List[str]:
        """Get beginner-appropriate training tips."""
        tips = BEGINNER_TIPS["general"].copy()

        if week_number <= 3:
            tips.extend(BEGINNER_TIPS["early"])
        elif week_number <= 6:
            tips.extend(BEGINNER_TIPS["mid"])
        else:
            tips.extend(BEGINNER_TIPS["late"])

        return tips
