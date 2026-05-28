"""Compose the user-facing headline reason for an adjustment.

The headline string surfaces in the change-plan modal and the persisted
adaptation event. It's assembled from the signals dict plus the
before/after snapshots so every contextual factor that drove the decision
is visible. Pure — no DB, no datetime, no logging.
"""

from typing import Any, Dict, Optional

_VERB_DELTA_THRESHOLD = 0.05


def compute_net_delta_km(
    before: Dict[str, Dict[str, Any]],
    after: Dict[str, Dict[str, Any]],
) -> float:
    """Sum the rounded distance deltas across all workouts in before ∪ after.

    Rounded to one decimal — matches the precision the UI displays and the
    threshold used to pick the headline verb.
    """
    return round(
        sum(
            (
                after.get(wid, {}).get("distance_km", 0.0)
                - before.get(wid, {}).get("distance_km", 0.0)
            )
            for wid in set(before) | set(after)
        ),
        1,
    )


def _verb_for(net_delta_km: float) -> str:
    if net_delta_km > _VERB_DELTA_THRESHOLD:
        return "increased"
    if net_delta_km < -_VERB_DELTA_THRESHOLD:
        return "reduced"
    return "kept"


def build_headline_reason(
    *,
    signals: Dict[str, Any],
    vdot_result: Optional[Dict[str, Any]],
    net_delta_km: float,
    multiplier: float,
    in_progress: bool,
    current_week: int,
    has_adjustable_weeks: bool,
) -> str:
    """Compose the user-facing reason string from the signals dict.

    Missing keys naturally suppress optional phrases (read via
    ``signals.get(...)``), so the same function serves both the rich-data
    path and the minimal-signals path.

    The user-facing verb has to track the actual net change. A baseline-
    relative multiplier below 1.0 can still produce a net increase when a
    previous, more aggressive adjustment had pulled distances further down
    — so the modal showed "Reduced ... +26 km" until this was decoupled.
    """
    volume_ratio = signals["volume_ratio"]
    completion_rate = signals["completion_rate"]
    avg_effort = signals["avg_effort"]
    effort_trend = signals.get("effort_trend", "stable")
    overreach_detected = signals.get("overreach_detected", False)
    current_phase = signals.get("current_phase", "build")
    phase_weights = signals.get("phase_weights", {})

    verb = _verb_for(net_delta_km)

    parts = [f"Remaining workouts {verb} (x{multiplier})."]
    parts.append(
        f"Volume ratio: {round(volume_ratio, 2)}, "
        f"completion: {round(completion_rate * 100)}%."
    )
    if avg_effort is not None:
        parts.append(f"Avg effort: {round(avg_effort, 1)}/10 (trend: {effort_trend}).")
    if overreach_detected:
        parts.append("Overreach detected — forced reduction to protect recovery.")
    if signals.get("vdot_trend") == "declining":
        parts.append("VDOT declining — capping volume to prevent overtraining.")
    tsb_form = signals.get("tsb_form")
    if tsb_form:
        parts.append(f"Form: {tsb_form} (TSB {signals.get('tsb')}).")
    if vdot_result:
        parts.append(
            f"VDOT recalibrated: {vdot_result['old_vdot']} → {vdot_result['new_vdot']} "
            f"({vdot_result['direction']})."
        )
    parts.append(
        f"Phase: {current_phase} (weights: "
        f"V={phase_weights.get('volume', 0):.0%} "
        f"E={phase_weights.get('effort', 0):.0%} "
        f"C={phase_weights.get('completion', 0):.0%})."
    )

    hr_zone_adherence = signals.get("hr_zone_adherence")
    if hr_zone_adherence is not None:
        parts.append(
            f"HR zone adherence: {round(hr_zone_adherence * 100)}% "
            f"(trend: {signals.get('hr_zone_trend', 'unknown')})."
        )

    warning_ratio = signals.get("warning_ratio")
    if warning_ratio is not None and warning_ratio > 0:
        parts.append(f"Feedback warnings: {round(warning_ratio * 100)}% of runs.")

    mountain_score = signals.get("mountain_simulation_score")
    if mountain_score is not None:
        parts.append(
            "Mountain simulation score: "
            f"{mountain_score}/100 (factor "
            f"x{signals.get('mountain_simulation_factor', 1.0)})."
        )

    if in_progress and has_adjustable_weeks:
        parts.insert(
            0,
            f"Current week {current_week} left in place — adjustments apply "
            f"from week {current_week + 1}.",
        )

    return " ".join(parts)
