"""DB ID enrichment, nutrition format conversion, and logged-run mapping."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.training.baseline_recovery import recover_baseline, strip_annotations
from app.core.training.key_workout_library import (
    _KEY_WORKOUT_MIN_DISTANCE_KM,
    KeyWorkoutLibrary,
    build_key_workout_steps,
    reconcile_key_workout_text,
)
from app.core.training.workout_steps import (
    _compute_distance_from_steps,
    _parse_pace_str_to_min_per_km,
)
from app.models import DailyWorkout, RunLog, WeeklyPlan

logger = logging.getLogger(__name__)

# Display inversion guard: an easy run must render strictly under the week's
# long run. This is a render-time safety net for legacy/corrupted weeks the
# adjuster never re-capped — distinct from (and looser than) the generation
# easy-run cap in quality_caps, so it never retroactively shrinks a correctly
# stored easy run, only fixes an actual easy>long inversion.
_EASY_DISPLAY_MAX_VS_LONG = 0.95

_DURATION_HINT_THRESHOLD_KM = 3.0
_DEFAULT_PACE_MIN_PER_KM_BY_ZONE = {
    "E": 8.0,
    "T": 6.5,
    "I": 5.5,
    "M": 6.0,
    "R": 5.0,
    "10K": 6.0,
}
_DEFAULT_PACE_MIN_PER_KM_BY_TYPE = {
    "easy": 7.0,
    "long": 7.0,
    "tempo": 5.5,
    "interval": 4.8,
    "hill": 5.0,
}


def _has_volume_steps(steps: list[dict]) -> bool:
    for step in steps:
        if step.get("kind") in {"warmup", "cooldown", "rest"}:
            continue
        if step.get("distance_m") or step.get("duration_s"):
            return True
    return False


def _repair_key_workout_steps(workout: dict[str, Any]) -> None:
    key_id = workout.get("key_workout_id")
    if not key_id:
        return

    distance_km = workout.get("distance", 0) or 0
    min_km = _KEY_WORKOUT_MIN_DISTANCE_KM.get(key_id, 0)
    if min_km > 0 and distance_km < min_km:
        distance_km = min_km
        workout["distance"] = distance_km

    reconcile_key_workout_text(workout)

    steps = workout.get("steps")
    if isinstance(steps, list) and _has_volume_steps(steps):
        return

    structure = workout.get("structure")
    key_wk = KeyWorkoutLibrary.get_by_id(key_id)
    if key_wk is None or not structure:
        return

    # Single entry point shared with generation: structured builder →
    # single-block for prose runs → hardened parser fallback.
    workout_type = workout.get("type", "interval")
    workout["steps"] = build_key_workout_steps(
        key_wk, structure, distance_km, workout_type, None
    )


def _estimate_duration_min_from_steps(
    steps: list[dict],
    workout_type: str,
) -> int | None:
    total_seconds = 0.0
    for step in steps:
        try:
            repeat = int(step.get("repeat", 1) or 1)
        except (TypeError, ValueError):
            repeat = 1
        repeat = max(1, repeat)

        duration_s = step.get("duration_s")
        if duration_s:
            total_seconds += float(duration_s) * repeat
            continue

        distance_m = step.get("distance_m")
        if not distance_m:
            continue

        pace_min_per_km = _parse_pace_str_to_min_per_km(
            step.get("pace_str"),
            step.get("pace_zone"),
        )
        if not pace_min_per_km:
            pace_min_per_km = _DEFAULT_PACE_MIN_PER_KM_BY_ZONE.get(
                step.get("pace_zone")
            ) or _DEFAULT_PACE_MIN_PER_KM_BY_TYPE.get(workout_type, 7.0)

        total_seconds += (float(distance_m) / 1000.0) * pace_min_per_km * 60.0 * repeat

    if total_seconds <= 0:
        return None
    return max(1, int(round(total_seconds / 60.0)))


def enrich_plan_data_with_ids(
    plan_data: list[dict],
    training_plan_id: str,
    db: Session,
) -> list[dict]:
    rows = (
        db.query(
            WeeklyPlan.week_number,
            DailyWorkout.day_of_week,
            DailyWorkout.id,
            DailyWorkout.baseline_distance_km,
        )
        .join(DailyWorkout, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
        .filter(WeeklyPlan.training_plan_id == training_plan_id)
        .all()
    )
    id_map = {(wn, dow): wid for wn, dow, wid, _ in rows}
    baseline_map = {(wn, dow): bl for wn, dow, _, bl in rows}

    for week in plan_data:
        week_num = week.get("week")
        for workout in week.get("daily_workouts", []):
            key = (week_num, workout.get("day"))
            workout["id"] = id_map.get(key)
            bl = baseline_map.get(key)
            # Snapshot the persisted distance before enrichment can rewrite
            # it. Adaptation diverges `distance_km` from `baseline_distance_km`
            # in the DB; view-time enrichment only mutates this in-memory
            # dict. Comparing against the snapshot keeps the chip tied to
            # real adaptations.
            original_distance = workout.get("distance")

            # Self-heal corrupted baselines for display. A lingering
            # "(Adjusted: xN)" note with baseline == distance means the stored
            # baseline was frozen to an already-adjusted distance (legacy
            # backfill). Recover the true original from the note's multiplier
            # so the card shows the right distance, drops the stale note, and
            # raises no false "adjusted" chip. In-memory only — no DB write.
            note_text = workout.get("notes") or workout.get("description")
            rec_baseline, rec_distance, recovered = recover_baseline(
                original_distance, bl, note_text
            )
            if recovered:
                workout["distance"] = rec_distance
                original_distance = rec_distance
                bl = rec_baseline
                if workout.get("notes"):
                    workout["notes"] = strip_annotations(workout["notes"])
                if workout.get("description"):
                    workout["description"] = strip_annotations(workout["description"])

            # `description` is the canonical card prose. Older/beginner plans
            # stored their summary under `notes`; backfill so every workout
            # renders a readable line (the card reads `description or notes`).
            if not workout.get("description") and workout.get("notes"):
                workout["description"] = strip_annotations(workout["notes"]) or ""

            _repair_key_workout_steps(workout)

            steps = workout.get("steps")
            if isinstance(steps, list) and steps:
                steps_distance_km = _compute_distance_from_steps(steps)
                if steps_distance_km > 0:
                    rounded_steps_km = round(steps_distance_km, 1)
                    current_distance = workout.get("distance", 0) or 0
                    if (
                        current_distance <= 0
                        or abs(current_distance - rounded_steps_km) > 0.2
                    ):
                        workout["distance"] = rounded_steps_km

                distance = workout.get("distance", 0) or 0
                if 0 < distance < _DURATION_HINT_THRESHOLD_KM:
                    est_min = _estimate_duration_min_from_steps(
                        steps,
                        workout.get("type", "easy"),
                    )
                    if est_min is not None:
                        workout["duration_min"] = est_min

            # Surface the baseline so workout_item.html renders the
            # "adjusted from X km" chip. Compare against the pre-enrichment
            # snapshot — not the (possibly rewritten) current distance — so
            # the chip only fires when real adaptation diverged the persisted
            # distance from its baseline. View-time mutations (key-workout
            # floor bump, steps-derived recompute) must not trigger it.
            if bl is not None and bl != original_distance:
                workout["baseline_distance"] = bl

    # Reconcile each week's chip with the daily distances we will actually
    # render. The per-workout `distance` can be rewritten above (steps-
    # derived recompute, key-workout minimum bump), and the stored
    # `total_km` was last written by the adjustment flow against the
    # pre-rewrite values. Recompute here so the chip is always the sum of
    # the daily cards beside it.
    for week in plan_data:
        daily = week.get("daily_workouts", [])
        # Structural invariant: an easy run can never display longer than the
        # week's long run. Adaptation enforces this only on weeks it touches,
        # so corrupted/legacy past weeks could otherwise show an inversion.
        long_run_km = next(
            (
                (wo.get("distance") or 0)
                for wo in daily
                if (wo.get("type") or wo.get("workout_type")) == "long"
            ),
            0,
        )
        if long_run_km > 0:
            for wo in daily:
                if (wo.get("type") or wo.get("workout_type")) != "easy":
                    continue
                dist = wo.get("distance") or 0
                if dist > 0:
                    wo["distance"] = min(
                        dist, round(long_run_km * _EASY_DISPLAY_MAX_VS_LONG, 1)
                    )
        week["total_km"] = round(
            sum((wo.get("distance") or 0) for wo in daily),
            1,
        )
        week["total_minutes"] = sum(
            (wo.get("duration_min") or 0)
            for wo in week.get("daily_workouts", [])
            if wo.get("type") not in ("rest", "recovery")
        )

    return plan_data


def _macro_summary(targets: dict) -> dict[str, Any]:
    """Map raw nutrition targets to the template's macro keys."""
    return {
        "daily_calories": targets.get("calories", 0),
        "protein_g": targets.get("protein", 0),
        "carbs_g": targets.get("carbs", 0),
        "fats_g": targets.get("fat", 0),
    }


def _default_hydration_guide() -> dict[str, Any]:
    """Fresh fallback hydration guide for per-day nutrition lists."""
    return {
        "daily_target": "2000ml",
        "pre_run": "300-500ml, 2 hours before",
        "during_run": "200-400ml per hour",
        "post_run": "150% of fluid lost",
        "tips": ["Stay hydrated throughout the day"],
    }


def _nutrition_from_daily_list(daily_plans: list) -> dict[str, Any]:
    """Build the template view-model from a per-day nutrition list."""
    first_day = daily_plans[0]
    if not isinstance(first_day, dict):
        return {}
    targets = first_day.get("nutrition_targets", {})
    if not isinstance(targets, dict):
        targets = {}

    meal_suggestions: dict[str, Any] = {}
    blueprint: dict[str, Any] = {
        **_macro_summary(targets),
        "meal_suggestions": meal_suggestions,
        "general_tips": first_day.get("nutrition_tips", []),
        "hydration_guide": _default_hydration_guide(),
    }
    for daily_plan in daily_plans:
        if not isinstance(daily_plan, dict):
            continue
        meals = daily_plan.get("meals", {})
        if not isinstance(meals, dict):
            continue
        for meal_type, meal_data in meals.items():
            meal_suggestions.setdefault(meal_type, []).append(meal_data)
    return blueprint


def _nutrition_from_blueprint_dict(plan: dict) -> dict[str, Any]:
    """Build the template view-model from a single blueprint dict."""

    def as_dict(key: str) -> dict:
        value = plan.get(key, {})
        return value if isinstance(value, dict) else {}

    def as_list(key: str) -> list:
        value = plan.get(key, [])
        return value if isinstance(value, list) else []

    return {
        **_macro_summary(as_dict("nutrition_targets")),
        "meal_suggestions": as_dict("meal_options"),
        "general_tips": as_list("general_tips"),
        "hydration_guide": as_dict("hydration_guide"),
        "pre_run_meal": plan.get("pre_run_meal"),
        "post_run_meal": plan.get("post_run_meal"),
        "in_race_fueling": plan.get("in_race_fueling"),
        "trail_fuel_ideas": as_list("trail_fuel_ideas"),
        "trail_fuel_phases": as_list("trail_fuel_phases"),
        "trail_tips": as_list("trail_tips"),
    }


def nutrition_for_template(nutrition_plan_data) -> dict[str, Any]:
    """Normalize stored nutrition data (list- or dict-shaped) for the template."""
    if not nutrition_plan_data:
        return {}
    if isinstance(nutrition_plan_data, list):
        return _nutrition_from_daily_list(nutrition_plan_data)
    if isinstance(nutrition_plan_data, dict):
        return _nutrition_from_blueprint_dict(nutrition_plan_data)
    return {}


def get_logged_runs_map(
    training_plan_id: str,
    db: Session,
) -> tuple[dict, list]:
    logged_runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == training_plan_id)
        .order_by(RunLog.date.desc())
        .all()
    )
    runs_map = {}
    for run in logged_runs:
        if run.daily_workout_id and run.daily_workout_id not in runs_map:
            runs_map[run.daily_workout_id] = run
    return runs_map, logged_runs


def get_feedback_map(logged_runs: list, db: Session) -> dict[str, Any]:
    from app.models.run_feedback import RunFeedback

    if not logged_runs:
        return {}
    try:
        run_ids = [r.id for r in logged_runs]
        feedbacks = (
            db.query(RunFeedback).filter(RunFeedback.run_log_id.in_(run_ids)).all()
        )
        return {fb.run_log_id: fb for fb in feedbacks}
    except Exception as e:
        logger.warning(f"Could not load feedback: {e}")
        return {}
