"""
Fitness Training Plan Generator

Generates physiology-focused training plans (VO2Max, threshold, balanced)
that prioritize fitness development over race preparation. Uses VDOT as the
primary metric and includes built-in time trials for progress tracking.
"""

from typing import Any, Dict, List, Optional

from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training import phase_calculator
from app.core.training.mileage_progression import runs_per_week_volume_factor
from app.core.training.strength_plan import derive_experience_level
from app.core.training.training_constants import calculate_week_in_phase
from app.core.training.tuning import (
    BASE_PHASE_END_FRACTION,
    FITNESS_PEAK_CAP_KM,
    FITNESS_PEAK_FLOOR_MULTIPLIER,
    FITNESS_PEAK_MULTIPLIER,
    FITNESS_TAPER_CURVE,
    FITNESS_TAPER_SINGLE,
    MIN_NON_RECOVERY_BUMP,
    PEAK_OSCILLATION_BASE,
    PEAK_OSCILLATION_STEP,
    RECOVERY_WEEK_RATIO,
    WEEK_OVER_WEEK_CAP,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_builders import attach_strength_sessions

from .base_plan_generator import BasePlanGenerator
from .fitness_workout_builders import (
    generate_cruise_interval_workout,
    generate_fartlek_workout,
    generate_long_run,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_time_trial_workout,
    generate_vo2max_ladder,
    generate_vo2max_workout,
)
from .phase_scaffold import build_phases_rich

_PHASE_METADATA = {
    "base": {
        "quality_percent": 25,
        "description": "Build aerobic foundation and introduce intensity",
    },
    "build": {
        "quality_percent": 45,
        "description": "Develop VO2max and lactate threshold",
    },
    "peak": {"quality_percent": 55, "description": "Peak physiological development"},
    "taper": {"quality_percent": 30, "description": "Consolidate gains and recover"},
}

_TIME_TRIAL_INTERVAL = 3

_FITNESS_QUALITY_PRIORITY = {
    "vo2max": {
        "base": ["tempo", "vo2max"],
        "build": ["vo2max", "vo2max_ladder"],
        "peak": ["vo2max", "vo2max_ladder"],
        "taper": ["tempo"],
    },
    "threshold": {
        "base": ["tempo", "cruise_interval"],
        "build": ["cruise_interval", "tempo"],
        "peak": ["cruise_interval", "tempo"],
        "taper": ["tempo"],
    },
    "balanced": {
        "base": ["tempo", "vo2max"],
        "build": ["vo2max", "cruise_interval"],
        "peak": ["vo2max", "tempo"],
        "taper": ["tempo"],
    },
}

_LIBRARY_TYPE_MAP = {
    "vo2max": "interval",
    "vo2max_ladder": "interval",
    "tempo": "tempo",
    "cruise_interval": "tempo",
    "fartlek": "interval",
    "time_trial": "interval",
}

_COACHING_TYPE_MAP = {
    "vo2max": "interval",
    "vo2max_ladder": "interval",
    "cruise_interval": "tempo",
    "race_pace": "tempo",
    "time_trial": "interval",
}


def _fitness_long_run_km(
    weekly_km: float,
    runs_per_week: int,
    focus_distance: Optional[float],
) -> float:
    """Long-run distance for a fitness week, responsive to focus and frequency.

    The previous flat ``min(weekly_km * 0.25, 18)`` made the endurance dose
    blind to both the focus distance and how often the runner trains: a 5K
    focus and a marathon focus produced nearly identical long runs, and a
    low-frequency plan leaned no harder on its single long session than a
    high-frequency one (audit recommendation #3). Here the long-run *share*
    grows with the focus distance (a marathon focus earns a bigger endurance
    session than a 5K focus) and with low training frequency (fewer runs each
    carry more of the week), while an absolute cap that also tracks the focus
    distance keeps it sane. Fitness plans are not race prep, so the cap stays
    well below a full marathon-specific long run.
    """
    if focus_distance and focus_distance >= 30:
        ratio = 0.32
    elif focus_distance and focus_distance >= 18:
        ratio = 0.28
    else:
        ratio = 0.25
    # Fewer runs → the long run is a larger slice of the week.
    if runs_per_week <= 3:
        ratio += 0.04

    # The ceiling tracks the focus distance but stays generous enough that the
    # ratio-driven endurance dose isn't throttled to a token run at higher
    # weekly volume. The old ``focus * 0.7`` collapsed a 10 km-focus long run to
    # an 8 km ceiling — so a 50 km/week plan's "long run" was 13% of the week
    # (no real endurance session). Scaling at ``focus * 1.3`` lets the long run
    # breathe (a 10 km focus reaches ~13 km, ~24% of a 55 km week) while still
    # staying well below a race-specific long run, which a fitness plan is not.
    if focus_distance and focus_distance > 0:
        cap = max(10.0, min(focus_distance * 1.3, 26.0))
    else:
        cap = 18.0

    return round(max(5.0, min(weekly_km * ratio, cap)), 1)


class FitnessPlanGenerator(BasePlanGenerator):
    """Generates fitness-focused training plans with VDOT-driven zones.

    Supports three focus areas:
    - vo2max: Emphasizes Zone 4 intervals for aerobic power
    - threshold: Emphasizes Zone 3 tempo/cruise work for lactate threshold
    - balanced: Mix of VO2max and threshold work

    Includes time trials every 3 weeks for progress tracking.

    Shared weekly-assembly machinery (easy-run scheduling, rest padding, key
    workout overlay, and quality structural caps) lives in BasePlanGenerator.
    """

    LIBRARY_TYPE_MAP = _LIBRARY_TYPE_MAP

    def calculate_training_zones(
        self,
        vdot: Optional[float] = None,
        max_hr: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate 5 training zones based on VDOT or fallback pacing.

        Delegates to the shared zone_calculator. Fitness plans have no goal
        pace, so zone 5 is anchored to VDOT-derived marathon pace (or a
        5.5 min/km fallback when VDOT is unavailable).
        """
        from app.core.training.zone_calculator import calculate_zones

        return calculate_zones(vdot=vdot, max_hr=max_hr)

    def _calculate_fitness_phases(self, weeks: int, focus_area: str) -> Dict[str, int]:
        """Calculate phase distribution for fitness plans.

        VO2max focus reduces/removes taper; others keep standard taper.
        """
        if focus_area == "vo2max":
            taper_weeks = 1
        else:
            taper_weeks = 2

        remaining = weeks - taper_weeks
        base = max(2, round(remaining * 0.30))
        build = max(2, round(remaining * 0.40))
        peak = remaining - base - build

        while base + build + peak + taper_weeks > weeks:
            if peak > 1:
                peak -= 1
            elif build > 2:
                build -= 1
            elif base > 2:
                base -= 1
            else:
                break

        while base + build + peak + taper_weeks < weeks:
            build += 1

        if taper_weeks == 0:
            return {"base": base, "build": build, "peak": peak, "taper": 0}
        return {"base": base, "build": build, "peak": peak, "taper": taper_weeks}

    def _is_time_trial_week(self, week_number: int) -> bool:
        """Determine if a week should include a time trial."""
        return week_number % _TIME_TRIAL_INTERVAL == 0

    def _generate_weekly_plan(
        self,
        week_number: int,
        phase: str,
        phases_rich: Dict,
        zones: Dict,
        weekly_km: float,
        runs_per_week: int,
        is_recovery: bool,
        focus_area: str,
        vdot: Optional[float] = None,
        vdot_zones: Optional[Dict] = None,
        week_in_phase: int = 0,
        is_time_trial_week: bool = False,
        focus_distance: Optional[float] = None,
        experience_level: str = "intermediate",
    ) -> Dict[str, Any]:
        quality_percent = phases_rich[phase]["quality_percent"]

        # Race specificity: a real focus distance threads through overlay,
        # coaching, race-pace sessions and the goal-pace long-run finish so
        # a 5K focus and a Half focus produce different plans (audit G9).
        target_distance = (
            focus_distance if focus_distance and focus_distance > 0 else 10.0
        )
        goal_race_pace = None
        if vdot and focus_distance and focus_distance > 0:
            secs = VDOTCalculator.predict_time_for_distance(vdot, focus_distance)
            if secs:
                goal_race_pace = secs / focus_distance / 60.0

        if is_recovery:
            quality_workouts_needed = 0 if is_time_trial_week else 1
        else:
            quality_workouts_needed = max(1, int(runs_per_week * quality_percent / 100))

        daily_workouts = []
        total_assigned_km = 0.0
        workout_schedule = []

        long_run_km = _fitness_long_run_km(weekly_km, runs_per_week, focus_distance)

        workout_schedule.append(
            {
                "day": 6,
                "workout_generator": lambda: generate_long_run(
                    zones, long_run_km, week_number, phase, race_pace=goal_race_pace
                ),
            }
        )

        if is_time_trial_week and not is_recovery:
            tt_distance = min(3.0, weekly_km * 0.15)
            tt_distance = max(tt_distance, 1.5)
            workout_schedule.append(
                {
                    "day": 3,
                    "workout_generator": lambda: generate_time_trial_workout(
                        zones, tt_distance, week_number, vdot
                    ),
                }
            )
            quality_workouts_needed = max(0, quality_workouts_needed - 1)

        if quality_workouts_needed > 0:
            quality_days = [2, 4] if runs_per_week >= 4 else [2]
            priority = _FITNESS_QUALITY_PRIORITY.get(
                focus_area, _FITNESS_QUALITY_PRIORITY["balanced"]
            )
            quality_types = list(priority.get(phase, ["tempo", "vo2max"]))

            # Peak weeks get a race-specific session at goal pace when a focus
            # distance is set, so peak fitness converts into race readiness.
            if phase == "peak" and focus_distance and focus_distance > 0:
                quality_types = ["race_pace"] + [
                    t for t in quality_types if t != "race_pace"
                ]

            generators = {
                "vo2max": lambda: generate_vo2max_workout(
                    zones, weekly_km, week_number, phase
                ),
                "vo2max_ladder": lambda: generate_vo2max_ladder(
                    zones, weekly_km, week_number, phase
                ),
                "cruise_interval": lambda: generate_cruise_interval_workout(
                    zones, weekly_km, week_number, phase
                ),
                "tempo": lambda: generate_tempo_workout(
                    zones, weekly_km, week_number, phase
                ),
                "fartlek": lambda: generate_fartlek_workout(
                    zones, weekly_km, week_number, phase
                ),
                "race_pace": lambda: generate_race_pace_workout(
                    zones, weekly_km, week_number, phase, focus_distance, vdot
                ),
            }

            for i, day in enumerate(quality_days[:quality_workouts_needed]):
                idx = (week_number - 1 + i) % len(quality_types)
                workout_type = quality_types[idx]
                generator = generators.get(workout_type, generators["tempo"])
                workout_schedule.append({"day": day, "workout_generator": generator})

        for item in workout_schedule:
            workout = item["workout_generator"]()
            workout["day"] = item["day"]
            daily_workouts.append(workout)
            total_assigned_km += workout["distance"]

        # Cap formulaic quality against the long run before filling easy volume,
        # so a single tempo/VO2max day can't approach or exceed the long run
        # (parity with the performance and road generators).
        self._enforce_quality_caps(daily_workouts, target_distance, phase)
        total_assigned_km = sum(w["distance"] for w in daily_workouts)

        # Fill remaining days with well-spaced easy runs, then rest
        remaining_km = weekly_km - total_assigned_km
        self._fill_easy_runs(daily_workouts, zones, runs_per_week, remaining_km)
        self._fill_rest_days(daily_workouts)

        # Overlay curated key workouts, bounded to a long-run-relative ceiling
        # so a fixed library prescription never balloons past the long run.
        quality_ceiling = self._key_workout_ceiling(daily_workouts)
        for workout in daily_workouts:
            if workout.get("quality", False):
                self._overlay_key_workout(
                    workout,
                    phase,
                    target_distance,
                    week_in_phase,
                    vdot_zones,
                    max_distance=quality_ceiling,
                )
            coaching_type = _COACHING_TYPE_MAP.get(workout["type"], workout["type"])
            workout["coaching_rationale"] = generate_coaching_note(
                coaching_type,
                phase,
                week_number,
                target_distance,
                is_recovery,
                pace_zones=vdot_zones,
            )
            if is_time_trial_week and workout["type"] == "time_trial":
                workout["coaching_rationale"] = (
                    f"Time Trial Week {week_number}: Give a maximal effort over the prescribed distance. "
                    "Use this result to track your VDOT progress and adjust training paces."
                )

        strength_sessions = attach_strength_sessions(
            daily_workouts,
            week_number,
            phase,
            experience_level=experience_level,
            target_distance=target_distance,
        )

        actual_total_km = sum(w["distance"] for w in daily_workouts)

        return {
            "week": week_number,
            "phase": phase,
            "phase_description": phases_rich[phase]["description"],
            "is_recovery": is_recovery,
            "is_time_trial_week": is_time_trial_week,
            "total_km": round(actual_total_km, 1),
            "quality_workouts": sum(
                1 for w in daily_workouts if w.get("quality", False)
            ),
            "daily_workouts": daily_workouts,
            "strength_training": strength_sessions,
        }

    def generate_plan(
        self,
        current_weekly_km: float,
        weeks: int,
        runs_per_week: int,
        vdot: Optional[float] = None,
        max_heart_rate: Optional[int] = None,
        focus_area: str = "vo2max",
        focus_distance: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate a complete fitness training plan."""
        weeks = max(6, min(12, weeks))
        runs_per_week = max(3, min(6, runs_per_week))

        phase_durations = self._calculate_fitness_phases(weeks, focus_area)
        phases_rich = build_phases_rich(phase_durations, _PHASE_METADATA)

        zones = self.calculate_training_zones(vdot, max_heart_rate)

        vdot_zones = None
        if vdot:
            vdot_zones = VDOTCalculator.get_pace_zones(vdot)

        # Weekly volume tracks training frequency: a runner training 5-6x/week
        # can absorb more aerobic load than one training 3x, so the chosen
        # frequency must move the peak target rather than just re-slicing a
        # fixed volume into more (smaller) runs. Reuse the same frequency→volume
        # relationship as the race/performance plans for one consistent model.
        # The downward nudge never detrains below the established base; the
        # FITNESS_PEAK_CAP_KM ceiling still bounds high-frequency, high-base
        # plans (where the cap, not the knob, is the binding constraint).
        runs_factor = runs_per_week_volume_factor(runs_per_week)
        peak_km = min(
            current_weekly_km * FITNESS_PEAK_MULTIPLIER * runs_factor,
            FITNESS_PEAK_CAP_KM,
        )
        floor_multiplier = FITNESS_PEAK_FLOOR_MULTIPLIER if runs_factor >= 1.0 else 1.0
        peak_km = max(peak_km, current_weekly_km * floor_multiplier)

        experience_level = derive_experience_level(current_weekly_km)

        km_progression = self._calculate_fitness_mileage(
            current_weekly_km, weeks, phase_durations, peak_km
        )

        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = phase_calculator.get_phase(week_num, phase_durations)
            is_recovery = phase_calculator.is_recovery_week(
                week_num, phase, phase_durations
            )
            week_in_phase = calculate_week_in_phase(week_num, phase, phase_durations)
            is_tt = self._is_time_trial_week(week_num) and not is_recovery

            weekly_plan = self._generate_weekly_plan(
                week_num,
                phase,
                phases_rich,
                zones,
                km_progression[week_num - 1],
                runs_per_week,
                is_recovery,
                focus_area,
                vdot,
                vdot_zones,
                week_in_phase,
                is_tt,
                focus_distance=focus_distance,
                experience_level=experience_level,
            )
            weekly_plans.append(weekly_plan)

        total_km = sum(week["total_km"] for week in weekly_plans)
        total_quality = sum(week["quality_workouts"] for week in weekly_plans)
        time_trial_weeks = [
            w["week"] for w in weekly_plans if w.get("is_time_trial_week")
        ]

        return {
            "focus_area": focus_area,
            "focus_distance": focus_distance,
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
                "peak_weekly_km": round(max(km_progression), 1),
                "total_quality_workouts": total_quality,
                "time_trial_weeks": time_trial_weeks,
            },
        }

    def _calculate_fitness_mileage(
        self,
        current_km: float,
        weeks: int,
        phases: Dict[str, int],
        peak_km: float,
    ) -> List[float]:
        """Calculate weekly mileage for fitness plans.

        Simpler than race plans: linear ramp to peak, recovery dips, taper if present.
        """
        weekly_progression: List[float] = []
        high_water = current_km

        for week_num in range(1, weeks + 1):
            phase = phase_calculator.get_phase(week_num, phases)
            is_recovery = phase_calculator.is_recovery_week(week_num, phase, phases)

            if is_recovery:
                week_km = high_water * RECOVERY_WEEK_RATIO
                weekly_progression.append(round(week_km, 1))
                continue

            if phase == "base":
                base_end = peak_km * BASE_PHASE_END_FRACTION
                progress = (week_num - 1) / max(1, phases["base"])
                week_km = current_km + (base_end - current_km) * progress
            elif phase == "build":
                build_start = peak_km * BASE_PHASE_END_FRACTION
                week_in_build = week_num - phases["base"]
                progress = week_in_build / max(1, phases["build"])
                week_km = build_start + (peak_km - build_start) * progress
            elif phase == "peak":
                week_in_peak = week_num - phases["base"] - phases["build"]
                oscillation = (
                    PEAK_OSCILLATION_BASE + (week_in_peak % 3) * PEAK_OSCILLATION_STEP
                )
                week_km = peak_km * oscillation
            else:
                taper_weeks = phases["taper"]
                week_in_taper = (
                    week_num - phases["base"] - phases["build"] - phases["peak"]
                )
                if taper_weeks == 1:
                    week_km = peak_km * FITNESS_TAPER_SINGLE
                else:
                    curve = FITNESS_TAPER_CURVE
                    week_km = peak_km * curve[min(week_in_taper, len(curve) - 1)]

            week_km = min(week_km, high_water * WEEK_OVER_WEEK_CAP)
            # The min-bump floor keeps loading weeks progressing, but it must not
            # apply to the taper: ``max(taper_km, high_water * 1.01)`` would lift
            # the taper week back above the peak it is meant to descend from,
            # inverting the taper (the final week became the plan's biggest). The
            # peak phase is also excluded (it oscillates around the ceiling).
            week_km = (
                max(week_km, high_water * MIN_NON_RECOVERY_BUMP)
                if week_num > 1 and phase not in ("peak", "taper")
                else week_km
            )
            # The taper descends, so it must never raise the high-water mark used
            # to anchor later weeks (there are none after taper, but keep the
            # invariant clean and avoid feeding an inflated value forward).
            if phase != "taper":
                high_water = week_km
            weekly_progression.append(round(week_km, 1))

        return weekly_progression
