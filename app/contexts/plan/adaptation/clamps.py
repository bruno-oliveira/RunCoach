"""Pure math helpers used during plan-adjustment signal aggregation.

Both functions are stateless and DB-free; they're factored out of
``signal_computer`` so they can be exercised by unit tests and reused
without pulling in the heavier orchestrator.
"""

from typing import Any, Dict, Optional, Tuple

from app.contexts.plan.adaptation.tuning import (
    HR_OVERREACH_ADHERENCE,
    HR_OVERREACH_CLAMP,
    HR_OVERREACH_DEVIATION,
    OVERREACH_EFFORT_SOLO_CLAMP,
    OVERREACH_EFFORT_SOLO_THRESHOLD,
    OVERREACH_EFFORT_THRESHOLD,
    OVERREACH_VOLUME_EFFORT_CLAMP,
    OVERREACH_VOLUME_RATIO,
    RACE_EFFORT_CLAMP,
    RACE_EFFORT_COUNT_THRESHOLD,
    TSB_FRESH,
    TSB_LOADED,
    TSB_OVERREACHED,
    TSB_OVERREACHED_CLAMP,
    TSB_PRIMED,
    VDOT_DECLINE_CLAMP,
)


def redistribute_weight(weights: Dict[str, float], dropped: str) -> None:
    """Zero ``dropped``'s weight and pro-rata redistribute it onto the rest.

    Mutates ``weights`` in place. Matches the legacy sequential ordering: if
    called twice for two missing signals, the second redistribution sees the
    already-inflated weights from the first.
    """
    original = weights[dropped]
    weights[dropped] = 0.0
    total_other = sum(v for k, v in weights.items() if k != dropped)
    if total_other > 0 and original > 0:
        scale = 1.0 + original / total_other
        for k in weights:
            if k != dropped:
                weights[k] *= scale


def apply_clamps(
    raw_multiplier: float,
    *,
    volume_ratio: float,
    avg_effort: Optional[float],
    hr_extras: Dict[str, Any],
    recent_race_effort_count: int,
    vdot_trend: str,
    training_load: Optional[Dict[str, Any]],
    current_phase: str,
) -> Tuple[float, bool, Dict[str, Any]]:
    """Apply overreach, vdot-trend, and TSB-form clamps.

    Returns ``(clamped_multiplier, overreach_detected, tsb_info)``.
    ``tsb_info`` carries ``tsb``, ``ctl``, ``atl``, ``tsb_form``, and
    ``peak_primed`` for downstream use.
    """
    overreach_detected = False

    if (
        volume_ratio > OVERREACH_VOLUME_RATIO
        and avg_effort is not None
        and avg_effort > OVERREACH_EFFORT_THRESHOLD
    ):
        raw_multiplier = min(raw_multiplier, OVERREACH_VOLUME_EFFORT_CLAMP)
        overreach_detected = True

    # Sustained very-high perceived effort on its own → hold, never increase.
    # Independent of volume, so it tempers an over-effort block several weeks
    # before volume crosses the overreach line. Holds (does not force a cut or
    # raise the overreach banner) — the firmer volume+effort branch above owns
    # the genuine "too much, too hard" reduction.
    if avg_effort is not None and avg_effort >= OVERREACH_EFFORT_SOLO_THRESHOLD:
        raw_multiplier = min(raw_multiplier, OVERREACH_EFFORT_SOLO_CLAMP)

    if (
        hr_extras.get("hr_zone_adherence", 1.0) < HR_OVERREACH_ADHERENCE
        and hr_extras.get("avg_abs_deviation", 0) > HR_OVERREACH_DEVIATION
    ):
        raw_multiplier = min(raw_multiplier, HR_OVERREACH_CLAMP)
        overreach_detected = True

    if recent_race_effort_count >= RACE_EFFORT_COUNT_THRESHOLD:
        raw_multiplier = min(raw_multiplier, RACE_EFFORT_CLAMP)
        overreach_detected = True

    if vdot_trend == "declining":
        raw_multiplier = min(raw_multiplier, VDOT_DECLINE_CLAMP)

    tsb = ctl = atl = None
    tsb_form: Optional[str] = None
    peak_primed = False
    if training_load and training_load.get("available"):
        current_load = training_load.get("current") or {}
        tsb = current_load.get("tsb")
        ctl = current_load.get("ctl")
        atl = current_load.get("atl")

    if tsb is not None:
        if tsb <= TSB_OVERREACHED:
            raw_multiplier = min(raw_multiplier, TSB_OVERREACHED_CLAMP)
            tsb_form = "overreached"
        elif tsb >= TSB_PRIMED and current_phase == "peak":
            tsb_form = "primed"
            peak_primed = True
        elif tsb >= TSB_FRESH:
            tsb_form = "fresh"
        elif tsb <= TSB_LOADED:
            tsb_form = "loaded"
        else:
            tsb_form = "neutral"

    return (
        raw_multiplier,
        overreach_detected,
        {
            "tsb": tsb,
            "ctl": ctl,
            "atl": atl,
            "tsb_form": tsb_form,
            "peak_primed": peak_primed,
        },
    )
