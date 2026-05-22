"""Treadmill incline prescriptions and per-week vertical-load actuals.

Two related concerns for flat-only training on a mountain race:

* ``attach_treadmill_prescriptions`` distributes the weekly simulated uphill
  budget across each week's eligible workouts (tempo/interval/hill) so the
  workout card can offer a concrete treadmill option ("20 min @ 6%").
* ``compute_weekly_vertical_actuals`` aggregates logged runs into per-week
  uphill/downhill/transition estimates, mirroring the factor model in
  :mod:`app.contexts.runner.fitness.readiness_scoring.score_mountain_simulation`
  so the weekly card can render planned-vs-actual gauges.

Pure functions — no DB or HTTP. The caller passes in the data it needs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from app.core.training.trail_profile import TrailProfile

_ELIGIBLE_TYPES = ("interval", "hill", "tempo", "long")

# Relative share of the weekly uphill budget assigned to each workout type
# when present. Quality sessions absorb more vertical than long runs because
# uphill running on treadmills is hard to sustain for long durations.
_TYPE_WEIGHTS = {
    "interval": 1.5,
    "hill": 1.5,
    "tempo": 1.2,
    "long": 1.0,
}

# Grade (%) prescribed for each workout type, indexed by race elevation class.
# Mountainous races push grade higher so eccentric and metabolic load match
# what the runner will face on race day.
_GRADE_BY_TYPE: Dict[str, Dict[str, int]] = {
    "rolling": {"tempo": 3, "interval": 5, "hill": 6, "long": 2},
    "hilly": {"tempo": 5, "interval": 7, "hill": 8, "long": 3},
    "mountainous": {"tempo": 6, "interval": 9, "hill": 10, "long": 4},
}

# Treadmill incline minutes can't exceed this fraction of the session's total
# duration -- otherwise the prescription crowds out warm-up, cool-down, and
# any rest intervals. 60% is a sensible upper bound for quality work.
_MAX_INCLINE_FRACTION = 0.60
_MIN_INCLINE_MIN = 6  # below this the prescription isn't worth surfacing

# Vertical ascent rate (m/min) on a treadmill at a given grade. Roughly
# 1.5 m/min per percent of incline at typical aerobic running speeds; this is
# the same scale used elsewhere in the codebase (12 m/min at ~8%).
_VERTICAL_RATE_PER_GRADE = 1.5


def attach_treadmill_prescriptions(
    workouts: List[Dict[str, Any]],
    vertical_simulation: Optional[Dict[str, Any]],
    trail_profile: Optional[TrailProfile],
    training_terrain: Optional[str],
) -> None:
    """Mutate ``workouts`` to add a ``treadmill_prescription`` field where useful.

    Only fires when the runner has flat-only access and a non-flat race
    profile -- the same gate as ``_vertical_simulation_targets`` in
    :mod:`app.contexts.plan.generators.weekly_plan_builder`.
    """
    if (
        trail_profile is None
        or training_terrain != "flat"
        or not vertical_simulation
        or not vertical_simulation.get("enabled")
    ):
        return

    elevation_class = trail_profile.elevation_class
    if elevation_class == "flat":
        return

    grade_table = _GRADE_BY_TYPE.get(elevation_class)
    if not grade_table:
        return

    budget_min = int(vertical_simulation.get("uphill_effort_min", 0) or 0)
    if budget_min <= 0:
        return

    eligible: List[Dict[str, Any]] = []
    for w in workouts:
        wtype = w.get("type")
        if wtype not in _ELIGIBLE_TYPES:
            continue
        duration = int(w.get("duration_min") or 0)
        if duration <= 0:
            # Fall back to a rough estimate from distance so workouts without
            # an attached duration hint still receive a prescription.
            dist = float(w.get("distance") or 0)
            if dist <= 0:
                continue
            duration = int(round(dist * 7.0))  # ~easy pace as a coarse floor
        eligible.append({"workout": w, "duration_min": duration})

    if not eligible:
        return

    total_weight = sum(_TYPE_WEIGHTS[e["workout"]["type"]] for e in eligible)
    if total_weight <= 0:
        return

    for entry in eligible:
        w = entry["workout"]
        wtype = w["type"]
        weight = _TYPE_WEIGHTS[wtype]
        raw_share = budget_min * (weight / total_weight)
        cap = entry["duration_min"] * _MAX_INCLINE_FRACTION
        incline_minutes = int(round(min(raw_share, cap)))
        if incline_minutes < _MIN_INCLINE_MIN:
            continue
        grade = grade_table[wtype]
        simulated_m = int(round(incline_minutes * _VERTICAL_RATE_PER_GRADE * grade))
        w["treadmill_prescription"] = {
            "incline_pct": grade,
            "incline_minutes": incline_minutes,
            "simulated_m": simulated_m,
            "note": _prescription_note(wtype, grade, incline_minutes),
        }


def _prescription_note(wtype: str, grade: int, minutes: int) -> str:
    if wtype == "long":
        return (
            f"Flat-access option: finish with {minutes} min on the treadmill "
            f"at {grade}% to bank race-specific vertical."
        )
    if wtype == "interval":
        return (
            f"Treadmill alternative: run the work intervals at {grade}% incline "
            f"({minutes} min total uphill effort)."
        )
    if wtype == "hill":
        return (
            f"Treadmill substitute: {minutes} min at {grade}% in 3-5 min reps "
            f"with easy walks between."
        )
    return (
        f"Treadmill alternative: hold {grade}% incline for the tempo block "
        f"({minutes} min)."
    )


# ---------------------------------------------------------------------------
# Per-week actuals from logged runs
# ---------------------------------------------------------------------------

# Matches score_mountain_simulation's factor model so dashboard adherence
# and the per-week card stay consistent.
_RUN_FACTORS = {
    "interval": (0.60, 0.45, 2),
    "tempo": (0.60, 0.45, 2),
    "hill": (0.60, 0.45, 2),
    "long": (0.30, 0.40, 1),
}
_DEFAULT_FACTORS = (0.12, 0.15, 0)


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def compute_weekly_vertical_actuals(
    plan_data: List[Dict[str, Any]],
    runs: Iterable[Any],
    start_date: Optional[date],
    training_plan_id: Optional[str] = None,
) -> Dict[int, Dict[str, int]]:
    """Aggregate executed vertical proxies per week from logged runs.

    Args:
        plan_data: The plan's weekly structure -- used to enumerate week
            numbers (so weeks with no runs still get a zeroed entry where the
            simulation is enabled).
        runs: Iterable of RunLog rows for the plan.
        start_date: Plan start date -- used to bucket runs into weeks.
        training_plan_id: Optional plan id; when provided, runs whose
            ``training_plan_id`` doesn't match are skipped.

    Returns:
        A mapping ``{week_number: {uphill_min, downhill_min, transitions}}``.
        Only weeks whose plan entry carries an enabled ``vertical_simulation``
        block are included -- this is purely a display companion to that
        block.
    """
    enabled_weeks = {
        wk.get("week"): {"uphill_min": 0, "downhill_min": 0, "transitions": 0}
        for wk in plan_data or []
        if isinstance(wk, dict) and (wk.get("vertical_simulation") or {}).get("enabled")
    }
    if not enabled_weeks or start_date is None:
        return {}

    uphill_acc: Dict[int, float] = {wk: 0.0 for wk in enabled_weeks}
    downhill_acc: Dict[int, float] = {wk: 0.0 for wk in enabled_weeks}
    transitions_acc: Dict[int, int] = {wk: 0 for wk in enabled_weeks}

    for run in runs:
        if (
            training_plan_id is not None
            and getattr(run, "training_plan_id", None) != training_plan_id
        ):
            continue
        run_date = _to_date(getattr(run, "date", None))
        if run_date is None:
            continue
        delta = (run_date - start_date).days
        if delta < 0:
            continue
        week_idx = delta // 7 + 1
        if week_idx not in enabled_weeks:
            continue

        duration = float(getattr(run, "duration_minutes", 0) or 0)
        if duration <= 0:
            continue

        wtype = (getattr(run, "workout_type", "") or "easy").lower()
        effort = int(getattr(run, "perceived_effort", 0) or 0)
        distance = float(getattr(run, "distance_km", 0) or 0)
        elevation = float(getattr(run, "elevation_gain_m", 0) or 0)
        m_per_km = (elevation / distance) if distance > 0 else 0.0

        uphill_factor, downhill_factor, transitions = _RUN_FACTORS.get(
            wtype,
            _DEFAULT_FACTORS,
        )
        if effort >= 7:
            uphill_factor += 0.08
            downhill_factor += 0.05
            transitions += 1
        if m_per_km >= 20:
            uphill_factor += 0.10
            downhill_factor += 0.10

        uphill_acc[week_idx] += duration * uphill_factor
        downhill_acc[week_idx] += duration * downhill_factor
        transitions_acc[week_idx] += transitions

    return {
        wk: {
            "uphill_min": int(round(uphill_acc[wk])),
            "downhill_min": int(round(downhill_acc[wk])),
            "transitions": transitions_acc[wk],
        }
        for wk in enabled_weeks
    }
