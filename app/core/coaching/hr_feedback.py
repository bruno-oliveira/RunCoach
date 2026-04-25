"""Heart-rate zone feedback — compare actual HR zone vs target zone."""

from typing import Optional

from app.core.training.hr_zone_calculator import HRZoneCalculator


def hr_zone_feedback(run_log, planned_workout, hr_zones) -> Optional[str]:
    """Compare actual HR zone vs target zone."""
    if not hr_zones or not run_log.avg_heart_rate:
        return None

    actual_zone = HRZoneCalculator.classify_hr(
        run_log.avg_heart_rate, hr_zones
    )

    target_zone = None
    if planned_workout and hasattr(planned_workout, "hr_zone_target"):
        target_zone = planned_workout.hr_zone_target
    if not target_zone:
        wtype = (
            run_log.workout_type or "easy"
        ).lower()
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
    elif diff == -1:
        return (
            f"Heart rate was a bit low ({actual_label} vs target "
            f"{target_label}). You could push a little harder next time."
        )
    else:
        return (
            f"Heart rate averaged {actual_label} — well below target "
            f"({target_label}). Increase intensity to get more benefit."
        )
