"""Whole-plan smoothing: re-anchor the weeks the model sized against a peak the
runner never ran.

The periodisation model sizes deloads and the taper from its own high-water
mark. On capped plans the loading weeks land below that mark, so anything
scaled from it lands too high. These passes re-anchor to the *delivered* load,
then sweep away the token cards the drawdown leaves behind.
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_passes.cards import (
    MIN_COHERENT_RUN_KM,
    MIN_VIABLE_QUALITY_KM,
    QUALITY_CARD_TYPES,
    RUNNING_CARD_TYPES,
    clear_duration_hints,
    refresh_duration_hints,
    week_total_km,
)
from app.contexts.plan.generators.workout_scaler import (
    reclamp_quality_to_long_run,
    scale_down,
)
from app.core.training.periodization import mileage_progression
from app.core.training.periodization.mileage_progression import _get_taper_curve
from app.core.training.periodization.phase_calculator import calculate_phases
from app.core.training.profiles.trail_profile import TrailProfile
from app.core.training.workouts import workout_builders


def smooth_recovery_dips(
    training_plan: List[Dict[str, Any]],
    pace_zones: Optional[Dict],
) -> None:
    """Keep deload weeks a genuine dip below the surrounding load (in place).

    A recovery week's target is ``RECOVERY_WEEK_RATIO`` of the progression's
    high-water mark. On low-frequency plans for a high base the loading weeks
    fall short of that high-water mark (a 2-3 run week can't physically hold the
    volume), so a deload anchored to the unrealized high-water can land *above*
    the loading weeks around it — a recovery week harder than the work weeks,
    which reads as a broken curve. This pass shrinks any recovery week back to
    ``RECOVERY_WEEK_RATIO`` of the loading week that precedes it, draining the
    excess from its flexible (easy/long) runs. Loading weeks are never touched.
    """
    prev_load_total: Optional[float] = None
    for weekly_plan in training_plan:
        if not weekly_plan.get("is_recovery"):
            prev_load_total = weekly_plan["total_km"]
            continue
        if prev_load_total is None:
            continue
        target = round(prev_load_total * mileage_progression.RECOVERY_WEEK_RATIO, 1)
        if weekly_plan["total_km"] > target + 0.05:
            workouts = weekly_plan["daily_workouts"]
            clear_duration_hints(workouts)
            scale_down(workouts, target, pace_zones=pace_zones)
            weekly_plan["total_km"] = week_total_km(workouts)
            refresh_duration_hints(workouts, pace_zones)


def smooth_taper(
    training_plan: List[Dict[str, Any]],
    target_distance: float,
    weeks: int,
    pace_zones: Optional[Dict],
    trail_profile: Optional[TrailProfile] = None,
) -> None:
    """Re-anchor the taper to the *realized* peak so it always descends (in place).

    The taper curve is computed inside ``calculate_weekly_progression`` from the
    progression's high-water mark. But on capped plans (low base / low frequency)
    the week-level 10% pass scales the loading weeks *down* below that high-water
    target, so a taper scaled from the unrealized peak lands too high relative to
    the weeks the runner actually ran — race week sitting at ~70% of the displayed
    peak instead of the intended ~50-55%. This pass rescales each taper week to
    ``taper_curve_fraction × realized_peak`` (the max loading-week total actually
    delivered), draining the excess from the flexible (easy/long) runs. Weeks
    already at or below target are untouched, so well-resourced plans are
    unaffected.
    """
    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    taper_weeks = phases.get("taper", 0)
    if taper_weeks <= 0 or taper_weeks >= len(training_plan):
        return

    loading = training_plan[: len(training_plan) - taper_weeks]
    realized_peak = max(
        (w["total_km"] for w in loading if not w.get("is_recovery")),
        default=0.0,
    )
    if realized_peak <= 0:
        return

    curve = _get_taper_curve(taper_weeks, target_distance, trail_profile=trail_profile)
    taper_plans = training_plan[len(training_plan) - taper_weeks :]
    for i, weekly_plan in enumerate(taper_plans):
        fraction = curve[min(i, len(curve) - 1)]
        target = round(realized_peak * fraction, 1)
        if weekly_plan["total_km"] > target + 0.05:
            workouts = weekly_plan["daily_workouts"]
            clear_duration_hints(workouts)
            scale_down(workouts, target, pace_zones=pace_zones, protect_long=False)
            reclamp_quality_to_long_run(workouts)
            weekly_plan["total_km"] = week_total_km(workouts)
            refresh_duration_hints(workouts, pace_zones)


def sweep_trivial_sessions(
    training_plan: List[Dict[str, Any]],
    pace_zones: Optional[Dict],
) -> None:
    """Render sub-viable running cards as the sessions they effectively are.

    Three ways a week can end up carrying a card no runner should execute:

    - a **zero**-distance running card — scaling passes can drain a flexible
      session to 0.0 km while the card stays typed ``easy``, so the calendar
      shows an easy run with no distance on it (observed on 5K/10K race weeks
      and, off the schema's guarded path, on a build week). Rendered as rest:
      it was never a run.
    - a **token quality** session — the taper and deload smoothing draws weeks
      down proportionally, and a 2.2 km "tempo" cannot hold warm-up, work, and
      cool-down. Rebuilt as an *easy* run at the same distance: the session
      was already jogging duration, and relabelling keeps the runner's
      frequency intact.
    - a **token easy** run — worst case observed: a 0.3 km easy card in a 10K
      peak week. Rendered as rest, but only when it is not even coherent
      (under a kilometre) *and* the week's median running dose shows the week
      can sustain real sessions — the crushed card is a scaling artifact, not
      the plan's honest shape. A 1.5 km jog in a small week is small-but-real
      and stays: converting it erodes frequency and deflates the ramp
      baseline for no coaching gain.

    The race week itself is skipped: its pre-race days are sized by
    ``race_week.install_race_day``, which applies the same rules to its own
    cards. Long runs are never converted — the week's long anchor is
    load-bearing for the plan's invariants, and a sub-viable long run does not
    occur on the grid (the long-run rebuild path resizes it rather than
    shrinking it to a token).

    A week is never left without a runnable session: converting the last one
    would trade a trivial card for a fatal structure-guard failure.
    """
    for weekly_plan in training_plan[:-1]:
        workouts = weekly_plan.get("daily_workouts") or []
        running = [
            w
            for w in workouts
            if w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) > 0
        ]
        doses = sorted((w.get("distance") or 0) for w in running)
        median_dose = doses[len(doses) // 2] if doses else 0.0
        shedding_week = weekly_plan.get("phase") == "taper" or weekly_plan.get(
            "is_recovery"
        )
        changed = False
        for i, w in enumerate(workouts):
            wtype = w.get("type")
            if wtype not in RUNNING_CARD_TYPES:
                continue
            distance = w.get("distance") or 0
            if wtype in QUALITY_CARD_TYPES:
                if distance < 0:
                    continue
                if distance == 0:
                    # A drained quality card is not a stimulus and not a run.
                    workouts[i] = workout_builders.generate_rest_day(w.get("day"))
                    changed = True
                    continue
                if distance >= MIN_VIABLE_QUALITY_KM:
                    continue
                if not shedding_week:
                    # A loading week keeps its intensity stimulus, however
                    # small: on a micro plan the token session is the plan's
                    # *only* quality work, and relabelling it as easy strips
                    # the plan of intensity entirely.
                    continue
                # A token quality session in a taper/deload week was already
                # jogging duration: relabel it as the easy run it effectively
                # was. Intensity is being shed by design.
                workouts[i] = workout_builders.generate_easy_run(
                    w.get("day"), distance, distance, pace_zones
                )
                changed = True
                continue
            if distance > 0 and distance >= MIN_COHERENT_RUN_KM:
                continue
            if distance > 0 and (
                median_dose < MIN_VIABLE_QUALITY_KM or len(running) <= 1
            ):
                # Not junk: either a borderline-but-real jog in a week that
                # cannot sustain bigger doses, or the week's only run. Both
                # stay — converting them trades a small card for frequency
                # erosion and a deflated ramp baseline.
                continue
            workouts[i] = workout_builders.generate_rest_day(w.get("day"))
            running = [r for r in running if r is not w]
            changed = True
        if changed:
            # The rebuild swaps in fresh cards, so the week's display hints
            # must be refreshed from the final distances — a downgraded
            # token tempo is now an easy run under the 3 km hint threshold.
            refresh_duration_hints(workouts, pace_zones)
            weekly_plan["daily_workouts"] = workouts
            weekly_plan["total_km"] = week_total_km(workouts)
