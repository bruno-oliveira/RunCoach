"""Per-slot distance budgeting, workout construction, and display helpers.

Leaf helpers for the weekly pipeline: cap quality slots, floor/demote
under-dose quality, allocate easy distances, build a workout by type, and
attach duration hints. No back-reference to the orchestrator.
"""

from typing import Any, Dict, List, Optional

from app.core.training.quality_caps import (
    BASE_QUALITY_MIN_DOSE_KM,
    MAX_EASY_RUN_KM,
    MAX_EASY_VS_LONG_RUN,
    MAX_QUALITY_VS_LONG_RUN,
    MIN_EASY_PER_RUN_KM,
    QUALITY_MIN_DOSE_KM,
    cap_easy_distance,
)
from app.core.training.quality_caps import (
    get_quality_caps as _get_quality_caps,
)
from app.core.training.tuning import MAX_QUALITY_DAY_SHARE, MIN_QUALITY_DAY_KM
from app.core.training.workout_steps import _parse_pace_str_to_min_per_km

# Quality slots with capped distance below this floor are demoted to easy
# rather than scheduled as a thin-stimulus workout. Set just below the
# smallest budget that still leaves room for a meaningful main set after
# warm-up and cool-down.
_QUALITY_DEMOTE_THRESHOLD_KM = 1.5

# Workouts shorter than this get an "≈ X min" UX hint alongside the km value.
_DURATION_HINT_THRESHOLD_KM = 3.0

_PACE_ZONE_FOR_TYPE = {
    "easy": "E",
    "long": "E",
    "tempo": "T",
    "interval": "I",
    "hill": "I",
}
_DEFAULT_PACE_MIN_PER_KM = {
    "easy": 7.0,
    "long": 7.0,
    "tempo": 5.5,
    "interval": 4.8,
    "hill": 5.0,
}


def resolve_low_budget_quality(
    distribution: Dict[str, int],
    quality_distances: Dict[str, float],
    *,
    remaining_km: float,
    long_run_distance: float,
    target_distance: float,
    phase: str,
) -> None:
    """Make an under-dose quality slot meaningful — or demote it to easy.

    A quality slot whose budget is below its meaningful dose
    (``QUALITY_MIN_DOSE_KM``) leaves a main set too thin to be worth a quality
    day. Fit the plan around the session rather than squishing the session into
    the leftover km:

    * **Floor** the slot up to that dose when the week can afford it — i.e. the
      shortfall, borrowed from the easy budget, still leaves each easy run at
      least ``MIN_EASY_PER_RUN_KM`` and the dose fits the physiological /
      long-run caps.
    * If it can't be floored but is still a real session (>= the hard token
      threshold), **keep it at its budget** — a modest quality day beats none,
      especially on low-run plans with no easy budget to borrow from.
    * Only a true token sliver (below the hard threshold) that can't be floored
      is **demoted** to an easy run (its km flow back to the easy budget).

    Mutates both inputs in place. The weekly total is preserved either way.

    Build/peak quality is meant to be substantial, so it is floored up to a
    meaningful dose when affordable — never below ``MIN_QUALITY_DAY_KM``, the
    smallest day worth spending a quality slot on. Base interval/hill slots
    keep their intentionally light *work* (strides / short hill sprints) but
    their day total is floored to ``MIN_QUALITY_DAY_KM`` as well: the easy
    bulk around the strides absorbs the growth. Base *tempo* slots are
    floored too, but to a lighter dose
    (``BASE_QUALITY_MIN_DOSE_KM``): a threshold stimulus needs a minimum
    continuous block, and the percentage budgeting was emitting 1.3-1.6 km T
    blocks in half/marathon base weeks — a session that costs a quality day yet
    delivers no threshold adaptation. Flooring to the lighter base dose keeps
    the slot worth running while staying introductory, rather than the
    build-grade ~20-min effort the full dose would produce. The taper sharpener
    is kept short — never floored up — but a token sliver that the week is too
    small to support is demoted to easy so tiny / low-volume taper weeks don't
    carry a malformed sub-floor session (audit G2).
    """
    if phase not in ("base", "build", "peak", "taper"):
        return
    doses = BASE_QUALITY_MIN_DOSE_KM if phase == "base" else QUALITY_MIN_DOSE_KM
    phys_caps = _get_quality_caps(target_distance, phase)
    ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
    # The quality-day floor only applies when the week can actually support a
    # day that size (≤ the day-share cap): on very low-volume plans a 4 km
    # floor would steal its km from the long run instead of the easy budget.
    week_km = remaining_km + long_run_distance
    day_floor = (
        MIN_QUALITY_DAY_KM
        if MIN_QUALITY_DAY_KM <= week_km * MAX_QUALITY_DAY_SHARE
        else 0.0
    )
    for qtype in ("tempo", "interval", "hill"):
        if phase == "base" and qtype != "tempo" and day_floor <= 0:
            continue  # base strides / hill sprints stay intentionally light
        if distribution.get(qtype, 0) <= 0:
            continue
        budget = quality_distances.get(qtype, 0)
        if budget <= 0:
            continue
        if phase == "base" and qtype != "tempo":
            # Base strides / hill sprints stay intentionally light in
            # intensity, but the *day* still has to be worth lacing up for —
            # the easy bulk around the strides absorbs the floored km, so a
            # 30 km/week runner never sees a 1.9 km "session".
            dose = day_floor
        else:
            dose = doses.get(qtype, 0)
            if phase != "taper":
                dose = max(dose, day_floor)
        if budget >= dose:
            continue  # already a meaningful dose

        if phase == "taper":
            # Keep the short sharpener as-is, but demote a token sliver the
            # week can't support back to easy (no flooring — sharpeners stay
            # short).
            if budget < _QUALITY_DEMOTE_THRESHOLD_KM:
                distribution[qtype] -= 1
                distribution["easy"] = distribution.get("easy", 0) + 1
                quality_distances.pop(qtype, None)
            continue

        capped_floor = round(min(dose, phys_caps.get(qtype, ceiling), ceiling), 1)
        easy_count = distribution.get("easy", 0)
        # Recomputed each iteration so a prior floor/demote is accounted for.
        quality_total = sum(quality_distances.values())
        projected_easy_budget = remaining_km - (quality_total - budget + capped_floor)

        can_afford = (
            capped_floor >= dose
            and easy_count > 0
            and projected_easy_budget / easy_count >= MIN_EASY_PER_RUN_KM
        )
        if can_afford:
            quality_distances[qtype] = capped_floor
        elif budget < _QUALITY_DEMOTE_THRESHOLD_KM:
            # True token sliver that can't be grown — demote to easy.
            distribution[qtype] -= 1
            distribution["easy"] = distribution.get("easy", 0) + 1
            quality_distances.pop(qtype, None)
        # else: keep the modest-but-real session at its budget.


def attach_duration_hints(
    workouts: List[Dict[str, Any]], pace_zones: Optional[Dict] = None
) -> None:
    """Attach a duration_min UX hint to short workouts.

    Pure display annotation: does not modify ``distance`` or ``steps``.
    Only fires for workouts shorter than the hint threshold so cards
    aren't cluttered with redundant minute estimates.
    """
    for w in workouts:
        wtype = w.get("type")
        if wtype not in _PACE_ZONE_FOR_TYPE:
            continue
        dist = w.get("distance", 0) or 0
        if dist <= 0 or dist >= _DURATION_HINT_THRESHOLD_KM:
            continue
        pace_min_km = _pace_for_type(wtype, pace_zones)
        w["duration_min"] = max(1, int(round(dist * pace_min_km)))


def _pace_for_type(wtype: str, pace_zones: Optional[Dict]) -> float:
    """Pace (min/km) for a workout type, preferring VDOT zones when present."""
    if pace_zones:
        zone = _PACE_ZONE_FOR_TYPE.get(wtype)
        if zone and zone in pace_zones:
            parsed = _parse_pace_str_to_min_per_km(
                pace_zones[zone].get("pace_str"),
                zone,
            )
            if parsed:
                return parsed
    return _DEFAULT_PACE_MIN_PER_KM.get(wtype, 7.0)


def apply_quality_caps(
    quality_distances: Dict[str, float],
    long_run_distance: float,
    target_distance: float,
    phase: str,
) -> Dict[str, float]:
    """Cap each quality workout by the smaller of:
    MAX_QUALITY_VS_LONG_RUN * long_run or the distance-scaled
    physiological cap for that workout type.
    """
    ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
    phys_caps = _get_quality_caps(target_distance, phase)
    capped = dict(quality_distances)
    for key in capped:
        cap = min(ceiling, phys_caps.get(key, ceiling))
        if capped[key] > cap:
            capped[key] = round(cap, 1)
    return capped


def allocate_easy_distances(
    remaining_km: float,
    quality_total: float,
    long_run_distance: float,
    easy_runs: int,
    max_easy_abs_km: float = MAX_EASY_RUN_KM,
    easy_vs_long_ratio: float = MAX_EASY_VS_LONG_RUN,
) -> List[float]:
    """Distribute the easy-run budget evenly across easy days.

    Each easy run is capped by both a fraction of the long run and an absolute
    ceiling (``cap_easy_distance``), so on low-run-count plans the week falls
    short of target rather than ballooning easy days into second long runs.
    Trail callers pass ``max_easy_abs_km=inf`` since back-to-back long days are
    intentional there. Low-frequency road callers pass a tighter
    ``easy_vs_long_ratio`` so the single easy slot stays clearly below the long
    run instead of becoming a second long effort.
    """
    if easy_runs <= 0:
        return []
    easy_budget = remaining_km - quality_total
    per_run = easy_budget / easy_runs
    return [
        cap_easy_distance(
            per_run, long_run_distance, max_easy_abs_km, easy_vs_long_ratio
        )
        for _ in range(easy_runs)
    ]


def build_workout_for_type(
    workout_type: str,
    day_number: int,
    distance: float,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict],
) -> Dict[str, Any]:
    """Dispatch workout creation to the registered builder."""
    from app.core.training.workout_registry import build_workout

    return build_workout(
        workout_type,
        day=day_number,
        distance=distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
    )
