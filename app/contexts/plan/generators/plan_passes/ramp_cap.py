"""The week-over-week ramp cap, applied to each week as it is built.

These two passes run inside the generation loop rather than after it, because
the ceiling for week *n+1* is the total week *n* actually delivered: a week
has to be capped before its total can become the next week's high-water mark.
"""

import logging
from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_passes.cards import (
    FLEXIBLE_TRIM_FLOOR_RATIO,
    week_total_km,
)
from app.contexts.plan.generators.workout_scaler import is_prescriptive, set_distance
from app.core.training.periodization import mileage_progression
from app.core.training.periodization.long_run_calculator import (
    get_weekly_long_run_ratio_cap,
)
from app.core.training.periodization.quality_caps import trail_easy_cap

logger = logging.getLogger(__name__)


def enforce_weekly_ramp_cap(
    weekly_plan: Dict[str, Any],
    high_water_km: float,
    max_runs_per_week: int,
    pace_zones: Optional[Dict],
) -> None:
    """Hold a loading week to the 10 % ramp over the delivered high-water mark.

    Only flexible workouts (easy, long) absorb the cap. Prescriptive workouts
    (key overlays + tempo / interval / hill) keep their authored distance —
    silently rescaling them would leave the description and step list
    describing a different session than the runner's distance number says. If
    flexible headroom is exhausted, the small overage rides into the next
    week's budget rather than corrupting a prescription.

    Recovery weeks are exempt, and so is a plan with no high-water mark yet.
    """
    if weekly_plan.get("is_recovery", False) or high_water_km <= 0:
        return
    assembled_km = weekly_plan["total_km"]
    ceiling = high_water_km * mileage_progression.WEEK_OVER_WEEK_CAP
    if assembled_km <= ceiling or assembled_km <= 0:
        return

    workouts = weekly_plan["daily_workouts"]
    flexible = [
        w
        for w in workouts
        if w.get("type") in ("easy", "long", "medium_long")
        and not is_prescriptive(w)
        and w.get("distance", 0) > 0
    ]
    _drain_flexible(workouts, flexible, ceiling, max_runs_per_week, pace_zones)
    _trim_rounding_overage(workouts, flexible, ceiling, pace_zones)
    _resolve_long_run_share(workouts, max_runs_per_week, pace_zones)
    weekly_plan["total_km"] = week_total_km(workouts)

    # This pass is the 10% invariant being *enforced*, not dead code: it fires
    # whenever the assembled week overshoots the delivered high-water mark
    # (measured on the plan matrix — the reachability gate is the model-level
    # fix). Most clips are sub-km rounding recoveries, so they log at DEBUG
    # like the weekly builder's own verdict; the material signal is the
    # per-week shortfall warning, which compares delivered volume against the
    # reachable target.
    logger.debug(
        "10%% weekly cap enforced: week %s trimmed to %.1f km "
        "against a %.1f km ceiling (%.1f km assembled)",
        weekly_plan.get("week"),
        weekly_plan["total_km"],
        ceiling,
        assembled_km,
    )


def _drain_flexible(
    workouts: List[Dict[str, Any]],
    flexible: List[Dict[str, Any]],
    ceiling: float,
    max_runs_per_week: int,
    pace_zones: Optional[Dict],
) -> None:
    """Shrink the flexible sessions onto what the ceiling leaves them."""
    fixed_km = sum(
        w.get("distance", 0)
        for w in workouts
        if w not in flexible and w.get("distance", 0) > 0
    )
    flexible_km = sum(w["distance"] for w in flexible)
    target_flexible = max(0.0, ceiling - fixed_km)
    if not flexible or flexible_km <= 0 or target_flexible >= flexible_km:
        return

    # At ≤ 3 runs drain the easy runs first, holding the long run: it is the
    # week's anchor, the weekly builder just enforced its cross-week
    # progression floor, and scaling both proportionally pushed the long run
    # back below that floor (measured: 10.6 → 8.9 across a build week — the
    # progression fault the floor exists to prevent). Only when the easy
    # budget alone cannot absorb the overage do both flexible sessions scale
    # together, exactly as ``workout_scaler.scale_down``'s ``protect_long``
    # branch behaves. At 4+ runs the original proportional scaling stands:
    # protecting the long run there let loading-week longs compound past the
    # contract cap and the envelope's published band (a 19 km "long run" for a
    # 10K).
    easy_ws = [w for w in flexible if w.get("type") == "easy"]
    easy_km = sum(w["distance"] for w in easy_ws)
    easy_floor_km = sum(w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO for w in easy_ws)
    overage = flexible_km - target_flexible
    if max_runs_per_week <= 3 and easy_ws and overage <= (easy_km - easy_floor_km):
        scale_easy = (easy_km - overage) / easy_km
        for w in easy_ws:
            scaled = w["distance"] * scale_easy
            floor = w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO
            set_distance(w, max(floor, scaled), pace_zones)
        return

    scale = target_flexible / flexible_km
    for w in flexible:
        scaled = w["distance"] * scale
        # The cap may shrink a session; it may not delete one. When the week's
        # *prescriptive* content already exceeds the ceiling this target lands
        # at zero, and scaling to it left the runner a 0.0 km "easy" card on
        # the calendar while the week still jumped 23 % — the worst of both.
        #
        # A ratio, not an absolute floor. An absolute ``MIN_VIABLE_RUN_KM``
        # floor also stopped the cap trimming *ordinary* weeks, because a
        # low-base high-frequency plan already sits at 2.5 km a run: it let a
        # trail plan sit at 12.04 %/week against the 10 % the cap allows. A
        # ratio can never reach zero, so it fixes the deletion without
        # disabling the cap.
        floor = w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO
        set_distance(w, max(floor, scaled), pace_zones)


def _trim_rounding_overage(
    workouts: List[Dict[str, Any]],
    flexible: List[Dict[str, Any]],
    ceiling: float,
    pace_zones: Optional[Dict],
) -> None:
    """Take a rounding-sized overage out of the largest flexible workout.

    Stops at the trim floor rather than shaving a session away.
    """
    total_exact = sum(w.get("distance", 0) for w in workouts)
    if total_exact <= ceiling + 0.01 or not flexible:
        return
    largest = max(flexible, key=lambda w: w.get("distance", 0))
    current = largest.get("distance", 0)
    trim_floor = current * FLEXIBLE_TRIM_FLOOR_RATIO
    set_distance(
        largest, max(trim_floor, current - (total_exact - ceiling)), pace_zones
    )


def _resolve_long_run_share(
    workouts: List[Dict[str, Any]],
    max_runs_per_week: int,
    pace_zones: Optional[Dict],
) -> None:
    """Give back whatever the long run's share of the smaller week requires.

    The easy-first drain preserves the long run — which can push its *share*
    of the now-smaller week past the frequency ceiling (a 5.6 km week with
    long 3.8 = 0.68 against 0.65; a 3-run marathon week drained to 0.56
    against 0.55). Re-solving the share here means no pass leaves the envelope
    breached, bounded by the same trim floor as the drain.
    """
    long_run = next(
        (
            w
            for w in workouts
            if w.get("type") == "long" and (w.get("distance") or 0) > 0
        ),
        None,
    )
    if long_run is None:
        return
    share_ceiling = get_weekly_long_run_ratio_cap(
        phase="base", max_runs=max_runs_per_week
    )
    rest_km = round(
        sum(
            w.get("distance", 0)
            for w in workouts
            if w.get("type") not in ("rest", "recovery", "long")
        ),
        1,
    )
    share_max = (
        int(share_ceiling * rest_km / (1 - share_ceiling) * 10) / 10
        if share_ceiling < 1
        else rest_km
    )
    if (long_run.get("distance") or 0) > share_max + 0.05:
        set_distance(
            long_run,
            max(long_run["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO, share_max),
            pace_zones,
        )


def refill_trail_week(
    weekly_plan: Dict[str, Any],
    week_target_km: float,
    high_water_km: float,
    pace_zones: Optional[Dict],
) -> None:
    """Return volume a clamp released to a trail week's aerobic slots.

    Trail weeks can lose a small amount when the final quality/long
    relationship is clamped. This hands that released volume to the
    non-prescriptive aerobic slots while respecting both the weekly ramp
    ceiling and the long-run anchor. Without the transfer, the same 30 km
    trail target delivered 31.7 km at four runs but only 30.7 km at five —
    offering another day reduced the prescription.

    The caller never refills a deload or a taper: a taper's shortfall is the
    point. Topping it up moved the km the shortened long run gave back into
    the weekday easy runs, which grew into the taper instead of shrinking.
    """
    workouts = weekly_plan["daily_workouts"]
    refill_ceiling = (
        high_water_km * mileage_progression.WEEK_OVER_WEEK_CAP
        if high_water_km > 0
        else week_target_km
    )
    deficit = min(week_target_km, refill_ceiling) - weekly_plan["total_km"]
    long_distance = max(
        (w.get("distance", 0) or 0 for w in workouts if w.get("type") == "long"),
        default=0.0,
    )
    # Easy runs refill only up to the trail easy ceiling. Bounded by the long
    # run alone, this pass turned every weekday easy run of a 100K peak week
    # into a 42 km copy of the long run.
    easy_ceiling = min(long_distance, trail_easy_cap(week_target_km))

    def _card_ceiling(w: Dict[str, Any]) -> float:
        return easy_ceiling if w.get("type") == "easy" else long_distance

    receivers = [
        w
        for w in workouts
        if w.get("type") in ("easy", "medium_long")
        and not is_prescriptive(w)
        and 0 < (w.get("distance") or 0) < _card_ceiling(w)
    ]
    headrooms = [_card_ceiling(w) - w["distance"] for w in receivers]
    total_headroom = sum(headrooms)
    if deficit <= 0.05 or total_headroom <= 0:
        return
    for workout, headroom in zip(receivers, headrooms):
        addition = min(headroom, deficit * headroom / total_headroom)
        set_distance(workout, workout["distance"] + addition, pace_zones)
    weekly_plan["total_km"] = week_total_km(workouts)
