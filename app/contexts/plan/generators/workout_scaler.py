"""Workout-scaling primitives extracted from weekly_plan_builder.

Each week's distance budget can disagree with the sum of its generated
workouts. The functions here close that gap by:

- shrinking flexible (easy / long) workouts when the week is over budget
  (`scale_down`),
- expanding flexible workouts when the week is under budget, with a hard
  ceiling on the long run (`fill_shortfall`),
- capping long-run dominance against the rest of the week
  (`enforce_long_run_ratio_cap`).

Prescriptive workouts — key-workout overlays and tempo/interval/hill builds
that embed distance fragments in their description / step list — are
never silently rescaled, because changing `distance` would leave the
description and steps describing a different session than the runner is
asked to do.

The lower-level helpers (`set_distance`, `rebuild_long_run`,
`rescale_steps`, `is_prescriptive`) are exported too so callers in
`plan_generator` can apply the same invariant-preserving rules when
they do their own scaling passes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training import long_run_calculator, workout_builders
from app.core.training.key_workout_library import reconcile_key_workout_text
from app.core.training.training_constants import get_hard_ceiling


def is_prescriptive(workout: Dict[str, Any]) -> bool:
    """Workouts whose ``distance``, ``description`` and ``steps`` are tightly
    coupled and must not be rescaled by week-level budget arithmetic.

    Key workouts (``key_workout_id``) are authored prescriptions. The
    standard quality builders (tempo / interval / hill) likewise embed
    distance fragments in the description (warm-up split, rep count,
    main_km), so silently changing ``workout['distance']`` would leave the
    description lying about what the runner is asked to do. Only easy and
    long runs are flexible enough to absorb week-budget drift.
    """
    if workout.get("key_workout_id"):
        return True
    return workout.get("type") in ("tempo", "interval", "hill")


def rescale_steps(workout: Dict[str, Any], multiplier: float) -> None:
    """Scale every step's distance_m / duration_s by ``multiplier`` so the
    step list stays in sync with the workout's distance.

    Skipped for prescriptive sessions — their structure is authored to a
    specific dose and shouldn't be rubber-banded to fit budget.
    """
    if multiplier == 1.0 or not workout.get("steps"):
        return
    if is_prescriptive(workout):
        return
    new_steps = []
    for s in workout["steps"]:
        ns = dict(s)
        if ns.get("distance_m"):
            ns["distance_m"] = max(1, int(round(ns["distance_m"] * multiplier)))
        if ns.get("duration_s"):
            ns["duration_s"] = max(1, int(round(ns["duration_s"] * multiplier)))
        new_steps.append(ns)
    workout["steps"] = new_steps


def rebuild_long_run(
    workout: Dict[str, Any], new_distance: float, pace_zones: Optional[Dict]
) -> None:
    """Rebuild a long-run workout so its description and steps reflect the
    new distance.

    ``generate_long_run`` is the single source of truth for the description
    template (including the ``mp_finish`` split that references distance
    fragments) and the matching step list. Calling it with the new distance
    keeps description ↔ steps ↔ distance aligned. Caller-attached fields
    (``coaching_rationale``, ``strength_session``, …) are preserved.
    """
    rounded = round(new_distance, 1)
    rebuilt = workout_builders.generate_long_run(
        workout.get("day", 0),
        rounded,
        rounded,
        pace_zones,
    )
    for key in ("distance", "description", "steps", "intensity", "type"):
        if key in rebuilt:
            workout[key] = rebuilt[key]


def set_distance(
    workout: Dict[str, Any], new_distance: float, pace_zones: Optional[Dict] = None
) -> None:
    """Update ``distance`` and keep the workout's text/steps in lockstep.

    For non-prescriptive workouts, steps are rescaled proportionally. Long
    runs additionally have their description re-rendered (the ``mp_finish``
    variant cites distance splits). Key-workout text is reconciled via the
    library's renderers. Prescriptive non-key workouts (tempo / interval /
    hill) are not expected to flow through here; if they do, ``distance``
    is updated alone — the caller is responsible for honouring the
    prescription's invariants.
    """
    old = workout.get("distance", 0) or 0
    rounded = round(new_distance, 1)
    if rounded == old:
        return
    if workout.get("type") == "long" and not workout.get("key_workout_id"):
        rebuild_long_run(workout, rounded, pace_zones)
        return
    workout["distance"] = rounded
    if old > 0 and rounded > 0:
        rescale_steps(workout, rounded / old)
    reconcile_key_workout_text(workout)


def scale_down(
    workouts: List[Dict[str, Any]], total_km: float, pace_zones: Optional[Dict] = None
) -> float:
    """Bring the week's total down to budget by shrinking flexible workouts.

    Prescriptive workouts (key overlays + tempo / interval / hill) stay at
    their prescribed distance — scaling them would silently invalidate the
    description and step list. Easy and (non-key) long runs absorb the
    overage; long runs are rebuilt via the long-run generator so their
    description and steps stay in lockstep with the new distance. If the
    flexible budget is exhausted, the small overage is accepted rather
    than corrupting a prescription.
    """
    actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)
    if actual_total_km <= total_km * 1.01 or actual_total_km <= 0:
        return actual_total_km

    flexible = [
        w
        for w in workouts
        if w.get("type") in ("easy", "long")
        and not is_prescriptive(w)
        and w.get("distance", 0) > 0
        and not w.get("duration_min")
    ]
    if not flexible:
        return actual_total_km

    fixed_km = sum(w.get("distance", 0) for w in workouts if w not in flexible)
    target_flexible = total_km - fixed_km
    flexible_km = sum(w["distance"] for w in flexible)
    if flexible_km <= 0 or target_flexible >= flexible_km:
        return actual_total_km
    target_flexible = max(target_flexible, 0)

    scale = target_flexible / flexible_km
    for w in flexible:
        set_distance(w, w["distance"] * scale, pace_zones)
    return round(sum(w.get("distance", 0) for w in workouts), 1)


def fill_shortfall(
    workouts: List[Dict[str, Any]],
    total_km: float,
    actual_total_km: float,
    target_distance: float,
    pace_zones: Optional[Dict] = None,
    trail_profile=None,
) -> float:
    """Fill shortfall by expanding easy runs; reshape long run when its
    distance must change for safety (hard ceiling) or balance against easy.

    Prescriptive workouts are never expanded — their distance is the
    prescription. Long-run mutations rebuild description + steps via
    ``rebuild_long_run`` so the workout stays internally consistent.
    """
    if actual_total_km >= total_km * 0.97 or actual_total_km <= 0:
        actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)
    else:
        deficit = total_km - actual_total_km
        flexible = [
            w
            for w in workouts
            if w.get("type") in ("easy", "long")
            and not is_prescriptive(w)
            and w.get("distance", 0) > 0
            and not w.get("duration_min")
        ]
        if flexible:
            total_flex = sum(w["distance"] for w in flexible)
            if total_flex > 0:
                for w in flexible:
                    share = deficit * (w["distance"] / total_flex)
                    set_distance(w, w["distance"] + share, pace_zones)

    hard_ceiling = get_hard_ceiling(target_distance, trail_profile=trail_profile)
    long_ws = [
        w for w in workouts if w.get("type") == "long" and w.get("distance", 0) > 0
    ]
    long_w = long_ws[0] if long_ws else None
    long_is_prescriptive = bool(long_w and long_w.get("key_workout_id"))

    if long_w and long_w["distance"] > hard_ceiling and not long_is_prescriptive:
        excess = round(long_w["distance"] - hard_ceiling, 1)
        set_distance(long_w, hard_ceiling, pace_zones)
        easy_ws = [
            w for w in workouts if w.get("type") == "easy" and w.get("distance", 0) > 0
        ]
        if easy_ws:
            per_easy = excess / len(easy_ws)
            for w in easy_ws:
                set_distance(w, w["distance"] + per_easy, pace_zones)

    if long_w:
        long_d = long_w["distance"]
        for w in workouts:
            if w.get("type") == "easy" and w.get("distance", 0) > long_d:
                if not long_is_prescriptive:
                    transferable = w["distance"] - long_d
                    headroom = hard_ceiling - long_d
                    transfer = min(transferable, max(0, headroom))
                    if transfer > 0:
                        set_distance(w, w["distance"] - transfer, pace_zones)
                        set_distance(long_w, long_w["distance"] + transfer, pace_zones)
                        long_d = long_w["distance"]
                if w["distance"] > long_d + 0.05:
                    set_distance(w, long_d, pace_zones)

    return round(sum(w.get("distance", 0) for w in workouts), 1)


def enforce_long_run_ratio_cap(
    workouts: List[Dict[str, Any]],
    phase: str,
    training_terrain: Optional[str] = None,
    trail_profile=None,
    max_ratio: float = 0.55,
    min_runs_for_cap: int = 4,
    pace_zones: Optional[Dict] = None,
) -> float:
    """Cap long-run dominance for practical weekly distribution.

    Applies only on 4+ running-day weeks. Excess long-run distance is
    redistributed to easy runs where possible.
    """
    running = [
        w
        for w in workouts
        if w.get("type") not in ("rest", "recovery") and (w.get("distance", 0) or 0) > 0
    ]
    if len(running) < min_runs_for_cap:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    long_ws = [w for w in running if w.get("type") == "long"]
    if not long_ws:
        return round(sum(w.get("distance", 0) for w in workouts), 1)
    long_w = long_ws[0]

    total = sum(w.get("distance", 0) for w in running)
    if total <= 0:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    effective_max_ratio = max_ratio
    if trail_profile is not None:
        effective_max_ratio = long_run_calculator.get_weekly_long_run_ratio_cap(
            phase,
            trail_profile=trail_profile,
            training_terrain=training_terrain,
        )

    max_long = total * effective_max_ratio
    long_d = long_w.get("distance", 0)
    if long_d <= max_long + 0.05:
        return round(sum(w.get("distance", 0) for w in workouts), 1)

    excess = long_d - max_long
    set_distance(long_w, max_long, pace_zones)

    recipients = [w for w in running if w is not long_w and w.get("type") == "easy"]
    if not recipients:
        recipients = [w for w in running if w is not long_w]
    if recipients:
        per = excess / len(recipients)
        for w in recipients:
            set_distance(w, w.get("distance", 0) + per, pace_zones)

    long_after = long_w.get("distance", 0)
    for w in workouts:
        if w.get("type") == "easy" and w.get("distance", 0) > long_after:
            set_distance(w, long_after, pace_zones)

    return round(sum(w.get("distance", 0) for w in workouts), 1)
