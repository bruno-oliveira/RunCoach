"""Step metrics: distance computation, pace parsing, and scaling for adaptation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Default pace estimates (min/km) for time-based workouts when no VDOT data.
# Must cover every pace_zone label step builders emit (E/T/I/M/R plus the
# race-pace labels "5K"/"10K"): a label missing here priced its reps at zero
# distance, which collapsed whole sessions to warm-up + cool-down (a 10K
# fartlek's 3 x 3-min main set vanished and the card showed 1.5 km).
_DEFAULT_PACES = {
    "E": 8.0,  # Easy pace
    "T": 6.5,  # Tempo/threshold pace
    "I": 5.5,  # Interval/VO2max pace
    "M": 6.0,  # Marathon pace
    "R": 5.0,  # Repetition/speed pace
    "10K": 6.2,  # 10K race pace (between T and M for an unknown runner)
    "5K": 5.8,  # 5K race pace (slightly slower than I on this scale)
    "WALK": 12.0,  # brisk walk / walk-down recovery - real covered ground
}


def _parse_pace_str_to_min_per_km(
    pace_str: Optional[str], pace_zone: Optional[str] = None
) -> Optional[float]:
    """Parse pace string like '6:22/km' or '7:05-7:55/km' to min/km float.

    For ranges like '5:54-5:16/km' (slow-fast format), uses the slower pace
    (first value) for conservative distance estimates.
    """
    if pace_str:
        pace_str = pace_str.replace("/km", "").strip()
        # Handle both en-dash (–) and regular hyphen (-)
        if "–" in pace_str:
            pace_str = pace_str.split("–")[0].strip()
        elif "-" in pace_str:
            pace_str = pace_str.split("-")[0].strip()
        parts = pace_str.split(":")
        if len(parts) == 2:
            try:
                return int(parts[0]) + int(parts[1]) / 60.0
            except ValueError:
                pass
    if pace_zone and pace_zone in _DEFAULT_PACES:
        return _DEFAULT_PACES[pace_zone]
    return None


def compute_distance_from_steps_checked(
    steps: List[Dict[str, Any]],
) -> tuple[float, bool]:
    """Compute total km from steps, reporting whether every step was priced.

    Returns ``(km, complete)``. ``complete`` is False when any
    duration-based *work* step had no resolvable pace and therefore
    contributed zero distance. A duration-based ``rest`` or ``recovery``
    step that carries no pace zone is a deliberate zero: the builders omit
    the zone exactly when the pause is standing/near-standing ground that
    must not count toward the session (e.g. the 60-90 s between cruise
    reps), so it doesn't make the total incomplete. Callers that reconcile
    a workout's displayed distance against its steps must treat an
    incomplete total as a lower bound - never as license to shrink the
    session below its budgeted distance.
    """
    total_m = 0.0
    complete = True
    for s in steps:
        if s.get("distance_m"):
            total_m += s["distance_m"] * s.get("repeat", 1)
        elif s.get("duration_s"):
            pace_min_km = _parse_pace_str_to_min_per_km(
                s.get("pace_str"), s.get("pace_zone")
            )
            if pace_min_km and pace_min_km > 0:
                duration_min = s["duration_s"] / 60.0
                distance_km = duration_min / pace_min_km
                total_m += distance_km * 1000 * s.get("repeat", 1)
            elif s.get("kind") not in ("rest", "recovery"):
                complete = False
    return total_m / 1000.0, complete


def _compute_distance_from_steps(steps: List[Dict[str, Any]]) -> float:
    """Compute total distance in km from workout steps.

    For distance-based steps, uses distance_m directly.
    For duration-based steps, calculates distance from duration and pace.
    Prefer :func:`compute_distance_from_steps_checked` when the result is
    used to overwrite a budgeted workout distance.
    """
    return compute_distance_from_steps_checked(steps)[0]


_REP_LABEL_RE = re.compile(r"^\s*(\d+)(\s*[×x]\s*)(.+)$")


def _relabel_rep_count(label: Optional[str], new_count: int) -> Optional[str]:
    """Rewrite the leading ``N ×`` count in a step label (e.g. '8 × 500 m')."""
    if not label:
        return label
    m = _REP_LABEL_RE.match(label)
    if not m:
        return label
    return f"{new_count}{m.group(2)}{m.group(3)}"


def fit_steps_to_distance(
    steps: List[Dict[str, Any]], max_km: float
) -> List[Dict[str, Any]]:
    """Trim an over-long key-workout step list so its priced total fits ``max_km``.

    A key workout's fixed prescription (e.g. ``8 × 500 m``, or a 60-minute
    hike-run) can run longer than the runner's physiological ceiling — for a
    low-mileage plan an interval session must not exceed the long run. Rather
    than rewrite every rep shorter (which would contradict the rep distance
    cited in the label), reps are *dropped* until the total fits, so the
    session stays a recognizable shorter version of itself (``7 × 500 m``
    instead of ``8 × 270 m``). Reps are only trimmed as far as needed; a
    session already within ``max_km`` is returned unchanged, so workouts keep
    their full prescribed length whenever the ceiling allows.

    As a last resort — a single rep plus warm-up/cool-down still overruns — the
    variable blocks are scaled by magnitude so the total never exceeds the
    ceiling.
    """
    if max_km <= 0 or not steps:
        return steps
    total, _ = compute_distance_from_steps_checked(steps)
    if total <= max_km:
        return steps

    work_kinds = ("run", "walk", "strides")
    work_counts = [
        s.get("repeat", 1)
        for s in steps
        if s.get("kind") in work_kinds and s.get("repeat", 1) > 1
    ]
    if work_counts:
        n = max(work_counts)
        for m in range(n - 1, 0, -1):
            factor = m / n
            candidate = []
            for s in steps:
                cs = dict(s)
                if s.get("repeat", 1) > 1:
                    nr = max(1, round(s["repeat"] * factor))
                    cs["repeat"] = nr
                    cs["label"] = _relabel_rep_count(s.get("label"), nr)
                candidate.append(cs)
            if compute_distance_from_steps_checked(candidate)[0] <= max_km:
                return candidate

    # One rep each still overruns (warm-up + cool-down + a single rep): collapse
    # repeats to one and scale the variable blocks by magnitude onto the ceiling.
    singles = []
    for s in steps:
        cs = dict(s)
        if s.get("repeat", 1) > 1:
            cs["repeat"] = 1
            cs["label"] = _relabel_rep_count(s.get("label"), 1)
        singles.append(cs)
    fixed_m = sum(
        (s.get("distance_m") or 0) * s.get("repeat", 1)
        for s in singles
        if s.get("kind") in ("warmup", "cooldown")
    )
    single_total_m = compute_distance_from_steps_checked(singles)[0] * 1000
    variable_m = single_total_m - fixed_m
    target_variable_m = max_km * 1000 - fixed_m
    if variable_m <= 0 or target_variable_m <= 0:
        return singles
    mult = target_variable_m / variable_m
    out = []
    for s in singles:
        cs = dict(s)
        if s.get("kind") not in ("warmup", "cooldown"):
            if s.get("distance_m"):
                cs["distance_m"] = int(round(s["distance_m"] * mult))
            if s.get("duration_s"):
                cs["duration_s"] = int(round(s["duration_s"] * mult))
        out.append(cs)
    return out


def _priced_step_km(s: Dict[str, Any]) -> float:
    """Priced km for one step (distance, or duration × zone pace), all reps."""
    reps = s.get("repeat", 1)
    if s.get("distance_m"):
        return s["distance_m"] * reps / 1000.0
    if s.get("duration_s"):
        pace = _parse_pace_str_to_min_per_km(s.get("pace_str"), s.get("pace_zone"))
        if pace and pace > 0:
            return (s["duration_s"] / 60.0) / pace * reps
    return 0.0


def work_km_by_group(steps: List[Dict[str, Any]]) -> Dict[str, float]:
    """Priced *work-set* km per capped intensity group (I / R / T).

    Only run/strides steps count as work; warm-up, cool-down, recoveries and
    walks are bookkeeping. Zones map onto groups via
    :data:`app.core.training.tuning.WORK_ZONE_GROUP`; zones with no group
    entry (M, E) are exempt from intensity caps and excluded here.
    """
    from app.core.training.tuning import WORK_ZONE_GROUP

    out: Dict[str, float] = {}
    for s in steps:
        if s.get("kind") not in ("run", "strides"):
            continue
        group = WORK_ZONE_GROUP.get(s.get("pace_zone") or "")
        if not group:
            continue
        km = _priced_step_km(s)
        if km > 0:
            out[group] = out.get(group, 0.0) + km
    return out


def exempt_work_km(steps: List[Dict[str, Any]]) -> float:
    """Priced work km at cap-exempt intensities (M-pace and easy)."""
    from app.core.training.tuning import WORK_ZONE_GROUP

    total = 0.0
    for s in steps:
        if s.get("kind") not in ("run", "strides"):
            continue
        zone = s.get("pace_zone") or ""
        if zone in WORK_ZONE_GROUP:
            continue
        total += _priced_step_km(s)
    return total


def fit_steps_to_intensity_caps(
    steps: List[Dict[str, Any]], weekly_km: float
) -> List[Dict[str, Any]]:
    """Drop reps until each intensity group's work fits its weekly-share cap.

    Enforces Daniels' intensity-volume guidelines (I ≤ 8%, R ≤ 5%, T ≤ 10% of
    weekly volume per session, with absolute ceilings) by reusing
    :func:`fit_steps_to_distance`'s drop-reps strategy: the total is walked
    down by the current overshoot until every group fits, so reps stay their
    prescribed length and the session remains recognizable. A floor
    (``MIN_CAPPED_WORK_KM``) guarantees a minimal complete stimulus on very
    low-volume weeks.
    """
    from app.core.training.tuning import (
        MAX_WORK_ABS_KM_BY_ZONE,
        MAX_WORK_SHARE_BY_ZONE,
        MIN_CAPPED_WORK_KM,
    )

    if weekly_km <= 0 or not steps:
        return steps
    for _ in range(6):
        excess = 0.0
        for group, km in work_km_by_group(steps).items():
            allowed = max(
                MIN_CAPPED_WORK_KM,
                min(
                    weekly_km * MAX_WORK_SHARE_BY_ZONE[group],
                    MAX_WORK_ABS_KM_BY_ZONE[group],
                ),
            )
            excess = max(excess, km - allowed)
        if excess <= 0.05:
            break
        total, _ = compute_distance_from_steps_checked(steps)
        trimmed = fit_steps_to_distance(steps, max(0.1, total - excess))
        if trimmed is steps:
            break
        steps = trimmed
    return steps


def scale_steps(steps: List[Dict[str, Any]], multiplier: float) -> List[Dict[str, Any]]:
    """Scale distance/duration of each step by a multiplier.

    Used by adaptation when a week's total distance is adjusted — keeps
    step proportions intact rather than blanket-scaling the whole workout.
    Warm-up and cool-down are NOT scaled (they're absolute).
    """
    if not steps or multiplier == 1.0:
        return steps
    scaled = []
    for s in steps:
        if s["kind"] in ("warmup", "cooldown", "rest"):
            scaled.append(dict(s))
            continue
        new = dict(s)
        if s.get("distance_m"):
            new["distance_m"] = int(round(s["distance_m"] * multiplier))
        if s.get("duration_s"):
            new["duration_s"] = int(round(s["duration_s"] * multiplier))
        scaled.append(new)
    return scaled


def total_distance_m(steps: List[Dict[str, Any]]) -> int:
    """Sum total meters across all step reps (for validation)."""
    total = 0
    for s in steps:
        if s.get("distance_m"):
            total += s["distance_m"] * s.get("repeat", 1)
    return total
