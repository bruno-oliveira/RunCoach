"""Couch to 5K style beginner plan generator for true beginners."""

import logging
from typing import Any, Dict, List

from app.core.training.periodization.training_constants import workouts_training_km
from app.core.training.workouts import workout_builders
from app.core.training.workouts.workout_builders import attach_strength_sessions

logger = logging.getLogger(__name__)

# Strength is introduced once the running habit is established, not in the
# first couple of weeks when an absolute beginner is barely running.
_STRENGTH_START_DISPLAY_WEEK = 3

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
        self.last_requested_runs_per_week = max_runs_per_week
        self.last_resolved_runs_per_week = max_runs
        if max_runs < max_runs_per_week:
            logger.warning(
                "Beginner plan frequency resolved from %d to %d runs/week: "
                "run/walk progression is capped at three sessions",
                max_runs_per_week,
                max_runs,
            )
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
        elif c25k_weeks_needed > c25k_total:
            # Longer 5K beginner blocks repeat selected progression stages
            # instead of silently returning only the ten template weeks while
            # persistence records the requested 12-16 week duration.
            c25k_sequence = [
                min(c25k_total, 1 + i * c25k_total // c25k_weeks_needed)
                for i in range(c25k_weeks_needed)
            ]
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

        self._enforce_monotonic_volume(plan, target_distance)
        self._install_beginner_race_day(plan, target_distance, max_runs)
        for week in plan:
            week["requested_runs_per_week"] = max_runs_per_week
            week["resolved_runs_per_week"] = max_runs
        self._attach_beginner_strength(plan, target_distance)

        return plan

    @staticmethod
    def _install_beginner_race_day(
        plan: List[Dict[str, Any]], target_distance: float, max_runs: int
    ) -> None:
        """Close a beginner block on the event, consuming one running slot."""
        if not plan:
            return
        final_week = plan[-1]
        workouts = sorted(final_week.get("daily_workouts", []), key=lambda w: w["day"])
        running = [w for w in workouts if (w.get("distance") or 0) > 0]
        # Keep the earliest easy/shakeout work and let the race consume the last
        # scheduled running slot.  This avoids silently turning a requested
        # three-run beginner week into four runs when race day is added.
        keep_ids = {id(w) for w in running[: max(0, max_runs - 1)]}
        kept = [w for w in workouts if not (w in running and id(w) not in keep_ids)]
        kept = [w for w in kept if w.get("day") != 7]
        race = workout_builders.generate_race_day(7, target_distance, None)
        race["coaching_rationale"] = (
            "Start gently, use walk breaks whenever you need them, and celebrate "
            "finishing the distance your plan has prepared you for."
        )
        kept.append(race)
        final_week["daily_workouts"] = sorted(kept, key=lambda w: w["day"])
        final_week["is_race_week"] = True
        final_week["total_km"] = round(sum(w.get("distance", 0) or 0 for w in kept), 1)
        final_week["training_km"] = workouts_training_km(kept)
        final_week["workout_distribution"] = {
            "race": 1,
            "easy": max(0, len(keep_ids)),
            "rest": 7 - max_runs,
        }

    def _enforce_monotonic_volume(
        self, plan: List[Dict[str, Any]], target_distance: float
    ) -> None:
        """Keep weekly volume non-decreasing across the build (taper may dip).

        A beginner seeing weekly km regress week-over-week is confusing; the
        run/walk → continuous transition naturally produces dips. We top up a
        short week proportionally across its running days — not by dumping the
        whole deficit on one session — and cap any single session at a
        beginner-safe ceiling so we never invent an unrealistic long run
        (audit G10). When the cap binds, the week settles on a plateau.
        """
        session_cap = round(target_distance * 1.5, 1)
        prev_total = 0.0
        for week in plan:
            if week.get("phase") == "taper":
                prev_total = week.get("total_km", 0.0)
                continue
            total = week.get("total_km", 0.0)
            runs = [w for w in week["daily_workouts"] if w.get("distance", 0) > 0]
            if total < prev_total - 0.05 and runs and total > 0:
                scale = prev_total / total
                for w in runs:
                    w["distance"] = round(min(session_cap, w["distance"] * scale), 1)
                week["total_km"] = round(
                    sum(w.get("distance", 0) for w in week["daily_workouts"]), 1
                )
            prev_total = week.get("total_km", 0.0)

    def _attach_beginner_strength(
        self, plan: List[Dict[str, Any]], target_distance: float
    ) -> None:
        """Hang one light strength session per week once habit is established."""
        for week in plan:
            display_week = week.get("week", 0)
            if display_week < _STRENGTH_START_DISPLAY_WEEK:
                week.setdefault("strength_training", [])
                continue
            sessions = attach_strength_sessions(
                week["daily_workouts"],
                display_week,
                week.get("phase", "base"),
                experience_level="beginner",
                target_distance=target_distance,
                attach_types=("easy", "run_walk", "long"),
                max_sessions=1,
            )
            week["strength_training"] = sessions

    def _session_distance_km(
        self,
        run_min: float,
        walk_min: float,
        repeats: int,
        extra_run_min: float = 0.0,
    ) -> float:
        """Estimate one session's distance from its *running* minutes.

        Walking recovery doesn't count as training distance, so per-workout
        km are honest (not 0) and track running capability — which grows far
        more smoothly than total run+walk time (audit G10).
        """
        run_total = run_min * repeats + extra_run_min
        run_km = run_total / self._pace_min_km if self._pace_min_km else 0.0
        return round(run_km, 1)

    def _generate_couch_to_5k_week(
        self,
        week_number: int,
        max_runs: int,
        display_week: int = 0,
        target_distance: float = 5.0,
    ) -> Dict[str, Any]:
        """Generate a single week for Couch to 5K plan.

        The three weekly sessions are differentiated rather than cloned: the
        early days run the canonical week structure, while the final day is a
        slightly longer "endurance" session, and every session carries a real
        distance derived from its run/walk minutes (audit G10).
        """
        cfg = BEGINNER_WEEKS.get(week_number, BEGINNER_WEEKS[10])
        display = display_week or week_number
        continuous = cfg["walk"] == 0

        days = self._get_workout_days(max_runs)
        std_km = self._session_distance_km(cfg["run"], cfg["walk"], cfg["repeats"])

        # The endurance day adds running: one extra interval on run/walk
        # weeks, or ~25% more running on continuous weeks.
        if continuous:
            extra_run_min = round(cfg["run"] * 0.25, 1)
            endurance_repeats = cfg["repeats"]
        else:
            extra_run_min = 0.0
            endurance_repeats = cfg["repeats"] + 1
        endurance_km = self._session_distance_km(
            cfg["run"], cfg["walk"], endurance_repeats, extra_run_min=extra_run_min
        )

        workouts: List[Dict[str, Any]] = []
        last_idx = len(days) - 1
        for i, day in enumerate(days):
            is_endurance = i == last_idx and max_runs >= 2
            if is_endurance:
                if continuous:
                    longer_min = int(round(cfg["run"] + extra_run_min))
                    notes = (
                        f"Endurance day — run {longer_min} minutes continuously, "
                        "a touch longer than your other runs. Keep it easy."
                    )
                    duration_min = longer_min
                else:
                    notes = (
                        f"Endurance day — run {cfg['run']:g} min / walk "
                        f"{cfg['walk']:g} min, {endurance_repeats} times "
                        "(one extra round). Build the habit of going a little longer."
                    )
                    duration_min = int(
                        round((cfg["run"] + cfg["walk"]) * endurance_repeats)
                    )
                workouts.append(
                    {
                        "day": day,
                        "type": "long" if continuous else "run_walk",
                        "distance": endurance_km,
                        "intensity": "low",
                        "notes": notes,
                        "duration_min": duration_min,
                        "run_min": cfg["run"],
                        "walk_min": cfg["walk"],
                        "repeats": endurance_repeats,
                    }
                )
            else:
                notes = cfg["notes"]
                if i == 1:
                    notes = (
                        cfg["notes"] + " (Session 2 — same structure; stay relaxed.)"
                    )
                workouts.append(
                    {
                        "day": day,
                        "type": "easy" if continuous else "run_walk",
                        "distance": std_km,
                        "intensity": "low",
                        "notes": notes,
                        "duration_min": cfg["total_min"],
                        "run_min": cfg["run"],
                        "walk_min": cfg["walk"],
                        "repeats": cfg["repeats"],
                    }
                )

        total_km = round(sum(w["distance"] for w in workouts), 1)
        long_count = 1 if (max_runs >= 2 and continuous) else 0

        return {
            "week": display,
            "total_km": total_km,
            "training_km": workouts_training_km(workouts),
            "phase": "beginner",
            "daily_workouts": workouts,
            "training_tips": self._get_beginner_tips(week_number, target_distance),
            "is_beginner_plan": True,
            "workout_distribution": {
                "long": long_count,
                "easy": max_runs - long_count,
                "rest": 7 - max_runs,
            },
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

        # The compressed C25K portion ends with a ~5 km endurance run.  Build
        # from that actual hand-off toward an 80%-of-race peak instead of
        # restarting at 25 minutes (which the monotonic repair pass merely
        # flattened back to 5.8 km for every extension week).
        loading_extensions = max(1, total_weeks - c25k_length - 1)
        progress = min(1.0, extension_week / loading_extensions)
        peak_long_km = target_distance * 0.8
        long_km = 5.0 + (peak_long_km - 5.0) * progress
        base_duration = int(round(long_km * self._pace_min_km))
        base_duration = min(75, base_duration)
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
            "training_km": workouts_training_km(workouts),
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
