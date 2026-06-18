"""Shared ORM → JSON steps/distance reconciliation for adaptation flows.

Every adaptation path that mutates ORM ``distance_km`` (the weekly adjuster,
missed-week recalibration, and the time-off/ahead recalibrator) must leave the
denormalized ``plan_data`` JSON a deterministic projection of the ORM —
otherwise a safety guard (``enforce_future_growth_cap`` / ``enforce_week_caps``)
can move a distance without rescaling the structured steps, and the view-time
enricher then recomputes the rendered distance back from those stale steps
(>0.2 km drift), so the per-workout cards no longer sum to the weekly chip.

This module is the single source of truth for that reconciliation so all three
flows stay in lockstep. It depends only on the plan builders and step maths, so
it carries no back-reference to the adjusters that import it.
"""

from typing import Any, Dict, Optional

from app.core.training import workout_steps as _steps_mod
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_registry import WORKOUT_REGISTRY, build_workout

_PLAIN_QUALITY_TYPES = ("tempo", "interval", "hill")


def pace_zones_for(training_plan) -> Optional[Dict[str, Any]]:
    """Derive VDOT pace zones for a plan, or ``None`` when no VDOT is set."""
    if getattr(training_plan, "vdot", None):
        return VDOTCalculator.get_pace_zones(training_plan.vdot)
    return None


def rebuild_plain_quality(
    pd_wo: Dict[str, Any],
    *,
    distance: float,
    day: int,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict[str, Any]],
) -> float:
    """Regenerate a non-key tempo/interval/hill workout at ``distance`` in place.

    Re-runs the same plan builder generation used (keyed on the workout's
    ``day`` so the rotation variant is preserved), then copies the fresh
    description, steps and intensity onto ``pd_wo``. Returns the builder's
    authoritative distance (its steps total) so callers can adopt it — keeping
    the card distance, weekly mileage and structured steps in lockstep, the
    same contract ``rebuild_key_workout`` provides for curated key workouts.

    Duration-defined sessions (hill) settle back to their fixed time total, so
    the returned distance simply won't move.
    """
    rebuilt = build_workout(
        pd_wo.get("type") or "easy",
        day=day,
        distance=distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
    )
    pd_wo["description"] = rebuilt.get("description", pd_wo.get("description"))
    pd_wo["steps"] = rebuilt.get("steps", [])
    if rebuilt.get("intensity"):
        pd_wo["intensity"] = rebuilt["intensity"]
    authoritative = round(rebuilt.get("distance", distance) or distance, 1)
    pd_wo["distance"] = authoritative
    return authoritative


def reconcile_plan_data_to_orm(
    weeks,
    workouts_by_week: Dict,
    pd_workout: Dict,
    pd_week: Dict,
    pace_zones: Optional[Dict[str, Any]],
) -> None:
    """Make ``plan_data`` a deterministic projection of the ORM distances.

    Belt-and-suspenders pass that makes the JSON plan_data a deterministic
    projection of the ORM, no matter which mutator (main adjust loop,
    ``enforce_week_structure``, growth-cap, missed-week shift) last touched the
    workouts. Guarantees that the per-workout distances the template renders
    sum to the weekly chip.

    Args:
        weeks: iterable of ``WeeklyPlan`` ORM rows to reconcile.
        workouts_by_week: ``week.id`` -> list of ``DailyWorkout`` ORM rows.
        pd_workout: ``(week_number, day_of_week)`` -> plan_data workout dict.
        pd_week: ``week_number`` -> plan_data week dict.
        pace_zones: VDOT pace zones for rebuilding (or ``None``).
    """
    for week in weeks:
        workouts = workouts_by_week.get(week.id, [])
        for workout in workouts:
            day = int(workout.day_of_week)
            pd_wo = pd_workout.get((week.week_number, day))
            if pd_wo is None:
                continue
            target = float(workout.distance_km or 0)
            wtype = str(workout.workout_type or "easy")
            is_key = bool(workout.key_workout_id)
            steps = pd_wo.get("steps") or []
            steps_km = _steps_mod._compute_distance_from_steps(steps) if steps else 0.0
            distance_synced = pd_wo.get("distance") == target
            # The steps total drives the *rendered* distance: view-time
            # enrichment recomputes distance from steps when they diverge by
            # >0.2 km. Reconcile whenever the steps no longer total the
            # authoritative ORM distance, even if pd_wo["distance"] already
            # matches — otherwise a guard-moved easy/long run renders its stale
            # steps total. The 0.05 km threshold sits below the enricher's
            # tolerance so we always reconcile before it would notice.
            steps_drift = steps_km > 0 and abs(steps_km - target) > 0.05
            if distance_synced and not steps_drift:
                continue
            wk = pd_week.get(week.week_number) or {}
            # A structural cap (enforce_week_caps) moved a non-key quality
            # distance after its steps were rebuilt — regenerate the session at
            # the capped distance and adopt the builder's steps total so the
            # card's distance, steps and description stay in lockstep.
            if wtype in _PLAIN_QUALITY_TYPES and not is_key and target > 0:
                workout.distance_km = rebuild_plain_quality(
                    pd_wo,
                    distance=target,
                    day=day,
                    total_km=wk.get("total_km") or 0.0,
                    phase=wk.get("phase", "build"),
                    pace_zones=pace_zones,
                )
            # Easy/long (and any other non-key) sessions carrying volume steps:
            # a safety guard moved the ORM distance without rescaling steps, so
            # the render-time recompute would revert the card to that stale
            # total. Scale the steps proportionally onto the authoritative
            # distance — from the *live* steps total, so it converges even after
            # several guards/adaptations compounded the drift — and refresh the
            # card prose (mirrors the main loop). Key workouts are excluded:
            # their steps are re-derived from `distance` at enrich time.
            elif not is_key and steps_drift and target > 0:
                pd_wo["steps"] = _steps_mod.scale_steps(steps, target / steps_km)
                # Performance log-only types (vo2max / race_pace / fartlek) have
                # no day-level builder; their scaled steps stay authoritative and
                # the existing prose is kept rather than rebuilt.
                if wtype in WORKOUT_REGISTRY:
                    rebuilt = build_workout(
                        wtype,
                        day=day,
                        distance=target,
                        total_km=wk.get("total_km") or 0.0,
                        phase=wk.get("phase", "build"),
                        pace_zones=pace_zones,
                    )
                    if rebuilt.get("description"):
                        pd_wo["description"] = rebuilt["description"]
            pd_wo["distance"] = workout.distance_km
        if week.week_number in pd_week:
            pd_week[week.week_number]["total_km"] = round(
                sum((w.distance_km or 0) for w in workouts), 1
            )
