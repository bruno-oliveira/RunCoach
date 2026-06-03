"""Heart-rate zone feedback — compare actual HR zone vs target zone."""

from typing import Optional

from app.core.training.hr_zone_calculator import HRZoneCalculator

# Quality session types where a below-target HR genuinely means "you didn't
# reach the intended hard effort". On easy / long / recovery runs a low HR is
# the goal, so the "push harder" cue would contradict the slow-down pace cue.
_QUALITY_TYPES = frozenset(
    {
        "tempo",
        "threshold",
        "cruise_interval",
        "interval",
        "vo2max",
        "vo2max_ladder",
        "hill",
        "fartlek",
        "race",
        "race_pace",
        "time_trial",
        "speed",
    }
)


def compute_hr_zone_deviation(run_log, planned_workout, hr_zones) -> Optional[int]:
    """Compute numeric HR zone deviation for a run.

    Returns:
        Signed integer: actual_zone - target_zone
        None if HR data or zones unavailable.
    """
    if not hr_zones or not run_log.avg_heart_rate:
        return None

    actual_zone = HRZoneCalculator.classify_hr(run_log.avg_heart_rate, hr_zones)

    target_zone = None
    if planned_workout and hasattr(planned_workout, "hr_zone_target"):
        target_zone = planned_workout.hr_zone_target
    if not target_zone:
        wtype = (run_log.workout_type or "easy").lower()
        target_zone = HRZoneCalculator.get_workout_zone(wtype)

    return actual_zone - target_zone


def hr_zone_feedback(run_log, planned_workout, hr_zones) -> Optional[str]:
    """Compare actual HR zone vs target zone."""
    if not hr_zones or not run_log.avg_heart_rate:
        return None

    actual_zone = HRZoneCalculator.classify_hr(run_log.avg_heart_rate, hr_zones)

    target_zone = None
    if planned_workout and hasattr(planned_workout, "hr_zone_target"):
        target_zone = planned_workout.hr_zone_target
    if not target_zone:
        wtype = (run_log.workout_type or "easy").lower()
        target_zone = HRZoneCalculator.get_workout_zone(wtype)

    target_label = HRZoneCalculator.zone_label(target_zone, hr_zones)
    actual_label = HRZoneCalculator.zone_label(actual_zone, hr_zones)

    diff = actual_zone - target_zone
    if diff == 0:
        return f"Heart rate was in the target zone ({actual_label}). Well paced!"
    elif diff >= 2:
        return (
            f"Heart rate averaged {actual_label} — that's {diff} zones above "
            f"the target ({target_label}). You're working harder than planned, "
            "which impairs recovery."
        )
    elif diff == 1:
        return (
            f"Heart rate was slightly high ({actual_label} vs target "
            f"{target_label}). Try to stay relaxed and ease into the effort."
        )

    # diff < 0: HR below target. Only nudge "push harder" on quality sessions —
    # on easy/long/recovery runs a low HR is exactly right, and telling the
    # runner to push would contradict the pace cue to keep it easy (audit B11).
    wtype = (run_log.effective_workout_type or run_log.workout_type or "easy").lower()
    if wtype not in _QUALITY_TYPES:
        return (
            f"Heart rate stayed comfortably easy ({actual_label}) — right where "
            "an easy aerobic run should be. Nicely controlled."
        )
    if diff == -1:
        return (
            f"Heart rate was a bit low ({actual_label} vs target "
            f"{target_label}). You could push a little harder next time."
        )
    return (
        f"Heart rate averaged {actual_label} — well below target "
        f"({target_label}). Increase intensity to get more benefit."
    )
