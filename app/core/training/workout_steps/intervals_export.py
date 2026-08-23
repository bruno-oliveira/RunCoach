"""Convert structured workout steps into an Intervals.icu workout description.

Intervals.icu accepts a plain-text workout ``description`` on calendar events
(``POST /athlete/{id}/events``). Once the athlete has linked Garmin Connect and
ticked "Upload planned workouts" in Intervals.icu, those events push to Garmin
automatically and land on the watch as structured workouts.

This module turns RunCoach's canonical ``steps`` model (see
``app.core.training.workout_steps``) into that text form. It is pure (no I/O),
so it is unit-testable and reused by the push endpoint.

Syntax notes (Intervals.icu workout builder):
  * ``m`` means MINUTES, not meters. Distance must use ``km``/``mi``
    (``0.4km`` for 400 m); seconds use ``s`` (``90s``).
  * Pace targets are written as an ABSOLUTE pace with the ``Pace`` keyword:
    ``- 10m 5:15/km Pace`` (single) or ``- 10m 5:00/km-5:15/km Pace`` (range,
    fast-slow). Absolute pace is independent of the athlete's threshold, so the
    watch shows the exact target RunCoach prescribed (the same approach Runna
    uses). We take the pace straight from each step's ``pace_str``; when a plan
    was generated without VDOT and a step has only a ``pace_zone``, we fall back
    to a default pace for that zone so a concrete target is always emitted.
  * A repeated block is a ``Nx`` header followed by its indented ``- `` steps.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.training.workout_steps.metrics import (
    _DEFAULT_PACES,
    _parse_pace_str_to_min_per_km,
)

# Fallback for legacy plans whose workouts carry no ``steps`` list: map the
# day's coarse type to a pace zone so a single continuous step still targets
# a sensible pace on the watch.
_TYPE_TO_ZONE = {
    "easy": "E",
    "recovery": "E",
    "long": "E",
    "marathon_pace": "M",
    "tempo": "T",
    "threshold": "T",
    "interval": "I",
    "vo2max": "I",
    "hill": "I",
    "speed": "R",
}


def _format_distance_km(distance_m: float) -> str:
    """Meters -> Intervals.icu distance token in km (400 -> '0.4km')."""
    km = distance_m / 1000.0
    text = f"{km:.3f}".rstrip("0").rstrip(".")
    return f"{text}km"


def _format_duration(duration_s: int) -> str:
    """Seconds -> Intervals.icu duration token ('10m' minutes, else '90s')."""
    if duration_s % 60 == 0:
        return f"{duration_s // 60}m"
    return f"{duration_s}s"


def _fmt_pace(min_per_km: float) -> str:
    """min/km float -> Intervals.icu absolute pace token ('5:15/km')."""
    total_s = int(round(min_per_km * 60))
    return f"{total_s // 60}:{total_s % 60:02d}/km"


def _parse_pace_bounds(pace_str: Optional[str]) -> list[float]:
    """Parse a pace_str into 1 or 2 min/km values ('7:05-7:55/km' -> [7.08, 7.92])."""
    if not pace_str:
        return []
    cleaned = pace_str.replace("/km", "").replace("–", "-").strip()
    bounds: list[float] = []
    for part in cleaned.split("-"):
        mm_ss = part.strip().split(":")
        if len(mm_ss) == 2:
            try:
                bounds.append(int(mm_ss[0]) + int(mm_ss[1]) / 60.0)
            except ValueError:
                pass
    return bounds


def _fallback_pace(step: dict[str, Any]) -> Optional[float]:
    """Default min/km for a step with no pace_str (pre-VDOT plans)."""
    zone = step.get("pace_zone")
    if zone and zone in _DEFAULT_PACES:
        return _DEFAULT_PACES[zone]
    kind = step.get("kind")
    if kind == "walk":
        return _DEFAULT_PACES["WALK"]
    if kind in ("warmup", "cooldown", "recovery"):
        return _DEFAULT_PACES["E"]
    return None


def _pace_target(step: dict[str, Any]) -> Optional[str]:
    """Absolute Intervals.icu pace target for a step, or None for an open step."""
    bounds = _parse_pace_bounds(step.get("pace_str"))
    if not bounds:
        fallback = _fallback_pace(step)
        if fallback is None:
            return None
        bounds = [fallback]
    if len(bounds) == 1:
        return f"{_fmt_pace(bounds[0])} Pace"
    return f"{_fmt_pace(min(bounds))}-{_fmt_pace(max(bounds))} Pace"


def _step_line(step: dict[str, Any]) -> Optional[str]:
    """Render one step as a ``- <amount> [<pace> Pace]`` line.

    Returns None for open steps (no distance and no duration), which have no
    Intervals.icu duration token and are skipped.
    """
    if step.get("distance_m"):
        amount = _format_distance_km(step["distance_m"])
    elif step.get("duration_s"):
        amount = _format_duration(int(step["duration_s"]))
    else:
        return None
    target = _pace_target(step)
    return f"- {amount} {target}" if target else f"- {amount}"


def _blocks(steps: list[dict[str, Any]]) -> list[str]:
    """Group steps into Intervals.icu text blocks, keeping repeats as ``Nx``.

    A ``run`` step with ``repeat > 1`` immediately followed by a matching
    ``recovery``/``walk``/``rest`` step is emitted as one ``Nx`` block wrapping
    both, mirroring how the session actually alternates work and rest. ``rest``
    belongs in that set for the same reason the other two do: a standing rest
    between cruise reps, or a backyard turnaround between loops, is part of the
    repeated unit, and splitting it into a second ``Nx`` block reads as though
    the runner does every rep and *then* every recovery.
    """
    out: list[str] = []
    i = 0
    n = len(steps)
    while i < n:
        step = steps[i]
        repeat = step.get("repeat", 1) or 1
        nxt = steps[i + 1] if i + 1 < n else None
        if (
            repeat > 1
            and nxt is not None
            and (nxt.get("repeat", 1) or 1) > 1
            and nxt.get("kind") in ("recovery", "walk", "rest")
        ):
            lines = [f"{repeat}x"]
            lines.extend(ln for ln in (_step_line(step), _step_line(nxt)) if ln)
            out.append("\n".join(lines))
            i += 2
        elif repeat > 1:
            line = _step_line(step)
            if line:
                out.append(f"{repeat}x\n{line}")
            i += 1
        else:
            line = _step_line(step)
            if line:
                out.append(line)
            i += 1
    return out


def _estimate_moving_time_s(steps: list[dict[str, Any]]) -> int:
    """Estimate total moving time in seconds across all step reps."""
    total = 0.0
    for step in steps:
        reps = step.get("repeat", 1) or 1
        if step.get("duration_s"):
            total += step["duration_s"] * reps
        elif step.get("distance_m"):
            pace = _parse_pace_str_to_min_per_km(
                step.get("pace_str"), step.get("pace_zone")
            )
            if pace and pace > 0:
                total += (step["distance_m"] / 1000.0) * pace * 60.0 * reps
    return int(round(total))


def _workout_name(day: dict[str, Any]) -> str:
    """Human workout name from the day's key-workout name or type."""
    raw = day.get("key_workout_name") or day.get("type") or "Workout"
    name = str(raw).replace("_", " ").strip().title()
    return name[:60] or "Workout"


def _fallback_steps(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Single continuous step for legacy workouts lacking a ``steps`` list."""
    distance_km = day.get("distance") or 0
    if distance_km and distance_km > 0:
        zone = _TYPE_TO_ZONE.get((day.get("type") or "").lower(), "E")
        return [
            {
                "kind": "run",
                "distance_m": int(round(distance_km * 1000)),
                "pace_zone": zone,
                "repeat": 1,
            }
        ]
    return []


def build_intervals_workout(day: dict[str, Any]) -> dict[str, Any]:
    """Build an Intervals.icu workout payload from a plan_data day dict.

    Args:
        day: One entry from ``TrainingPlan.plan_data[week]["daily_workouts"]``,
            expected to carry a ``steps`` list (falls back to the day distance).

    Returns:
        Dict with ``name``, ``description`` (Intervals.icu step text), and
        ``moving_time`` (estimated seconds).

    Raises:
        ValueError: The workout has no structured, sendable steps (e.g. a rest
            day, or a distance-less day with no steps).
    """
    steps = day.get("steps") or _fallback_steps(day)
    if not steps:
        raise ValueError("Workout has no structured steps to send")
    blocks = _blocks(steps)
    if not blocks:
        raise ValueError("Workout has no sendable steps")
    return {
        "name": _workout_name(day),
        "description": "\n\n".join(blocks),
        "moving_time": _estimate_moving_time_s(steps),
    }
