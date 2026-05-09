"""Apply adjustment multiplier to future weeks' workout distances."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import TrainingPlan, WeeklyPlan
from app.core.training import workout_steps as _steps_mod

from ._helpers import ANNOTATION_RE, batch_workouts_by_week, parse_plan_data_lookups
from .safety import enforce_future_growth_cap, enforce_week_structure

logger = logging.getLogger(__name__)


def apply_adjustment_to_future_weeks(
    training_plan: TrainingPlan,
    future_weeks: List,
    multiplier: float,
    db: Session,
    *,
    current_week: int | None = None,
    current_day_of_week: int | None = None,
    per_type_ratios: Optional[Dict[str, float]] = None,
) -> Tuple[int, bool]:
    plan_data, pd_week, pd_workout = parse_plan_data_lookups(training_plan)
    target_distance = training_plan.target_distance_km

    workouts_by_week = batch_workouts_by_week(
        [week.id for week in future_weeks], db
    )

    weeks_changed = 0
    any_distance_changed = False

    future_weeks = sorted(future_weeks, key=lambda w: w.week_number)
    week_by_number = {w.week_number: w for w in future_weeks}

    for week in future_weeks:
        workouts = workouts_by_week.get(week.id, [])
        week_changed = False
        phase = pd_week.get(week.week_number, {}).get("phase", "build")

        for workout in workouts:
            if (
                workout.workout_type == "rest"
                or not workout.distance_km
                or workout.distance_km <= 0
            ):
                continue

            if (
                current_week is not None
                and current_day_of_week is not None
                and week.week_number == current_week
                and workout.day_of_week < current_day_of_week
            ):
                continue

            # Prescriptive workouts (key overlays + standard tempo / interval
            # / hill) embed distance fragments in description and steps
            # (warm-up split, rep count, main_km). Adaptation absorbs ratio
            # adjustments through flexible workouts (easy, long) instead of
            # silently mutating a prescribed distance while its description
            # and step list stay frozen.
            if (
                workout.key_workout_id
                or workout.workout_type in ("tempo", "interval", "hill")
            ):
                continue

            base_distance = workout.baseline_distance_km or workout.distance_km

            wtype = workout.workout_type or "easy"
            type_mult = multiplier
            if per_type_ratios and wtype in per_type_ratios:
                type_ratio = per_type_ratios[wtype]
                type_mult = round(max(0.85, min(1.15, type_ratio)), 2)

            if workout.workout_type == "long" and type_mult < 1.0:
                new_distance = round(base_distance, 1)
            elif workout.workout_type in ("interval", "tempo", "hill", "vo2max", "race_pace", "fartlek"):
                quality_mult = 1.0 + (type_mult - 1.0) * 0.5
                new_distance = max(1.0, round(base_distance * quality_mult, 1))
            else:
                new_distance = max(1.0, round(base_distance * type_mult, 1))
            old_distance = workout.distance_km

            if new_distance == old_distance:
                continue

            workout.distance_km = new_distance
            any_distance_changed = True
            week_changed = True

            is_protected = workout.workout_type == "long" and type_mult < 1.0

            clean_notes = ANNOTATION_RE.sub("", workout.notes or "").strip()
            if type_mult != 1.0 and not is_protected:
                adjust_note = f"(Adjusted: x{type_mult})"
                workout.notes = (
                    f"{clean_notes} {adjust_note}".strip()
                    if clean_notes
                    else adjust_note
                )
            else:
                workout.notes = clean_notes or None

            pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
            if pd_wo is not None:
                pd_wo["distance"] = new_distance
                if pd_wo.get("steps") and old_distance and old_distance > 0:
                    step_scale = new_distance / old_distance
                    pd_wo["steps"] = _steps_mod.scale_steps(pd_wo["steps"], step_scale)
                pd_clean = ANNOTATION_RE.sub(
                    "", pd_wo.get("notes", pd_wo.get("description", ""))
                ).strip()
                if type_mult != 1.0 and not is_protected:
                    adjust_note = f"(Adjusted: x{type_mult})"
                    pd_wo["notes"] = (
                        f"{pd_clean} {adjust_note}".strip()
                        if pd_clean
                        else adjust_note
                    )
                else:
                    pd_wo["notes"] = pd_clean

        if week_changed and target_distance > 0:
            if enforce_week_structure(workouts, target_distance, phase):
                week_changed = True

        if week_changed:
            weeks_changed += 1
            new_total = round(
                sum(w.distance_km for w in workouts if w.distance_km), 1
            )
            week.total_km = new_total
            if week.week_number in pd_week:
                pd_week[week.week_number]["total_km"] = new_total
                for workout in workouts:
                    pd_wo = pd_workout.get((week.week_number, workout.day_of_week))
                    if pd_wo is not None:
                        pd_wo["distance"] = workout.distance_km

    if future_weeks:
        first_future_week = future_weeks[0].week_number
        prev_week = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == training_plan.id,
                WeeklyPlan.week_number < first_future_week,
            )
            .order_by(WeeklyPlan.week_number.desc())
            .first()
        )
        seed = prev_week.total_km if prev_week and prev_week.total_km else training_plan.current_weekly_km or 0.0
        changed_weeks = enforce_future_growth_cap(
            [w.week_number for w in future_weeks],
            week_by_number,
            workouts_by_week,
            pd_week,
            high_water_seed=seed,
        )
        if changed_weeks > 0:
            weeks_changed += changed_weeks
            any_distance_changed = True

    training_plan.plan_data = plan_data
    return weeks_changed, any_distance_changed
