"""Step metrics: distance computation, pace parsing, and scaling for adaptation."""

from __future__ import annotations

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
    duration-based step (other than a deliberate ``rest``) had no resolvable
    pace and therefore contributed zero distance. Callers that reconcile a
    workout's displayed distance against its steps must treat an incomplete
    total as a lower bound - never as license to shrink the session below
    its budgeted distance.
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
            elif s.get("kind") != "rest":
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
