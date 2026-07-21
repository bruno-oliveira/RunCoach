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
  * Running pace targets are expressed against the athlete's threshold pace,
    as a zone (``Z4 Pace``) or a percentage band (``78-82% pace``). Absolute
    paces (``4:30/km``) are not part of the formal step syntax, so we target
    zones and surface the RunCoach pace only in the workout name.
  * A repeated block is a ``Nx`` header followed by its indented ``- `` steps.

Spike before relying on this: post a sample workout to a real Intervals.icu
account and confirm the pace targets survive the push to Garmin. If zone-based
targets read poorly on the watch, switch ``_ZONE_TO_PACE_ZONE`` mapping to the
percentage form (both are valid Intervals.icu syntax).
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.training.workout_steps.metrics import _parse_pace_str_to_min_per_km

# RunCoach pace zone -> Intervals.icu pace zone (relative to threshold pace).
# Daniels E/M/T/I/R map onto Intervals' Z2..Z6; warm-up/recovery sit at Z1.
_ZONE_TO_PACE_ZONE = {
    "E": "Z2",
    "M": "Z3",
    "T": "Z4",
    "I": "Z5",
    "R": "Z6",
    "5K": "Z5",
    "10K": "Z4",
}

# Easy-effort kinds always target the recovery zone regardless of pace_zone.
_EASY_KINDS = {"warmup", "cooldown", "recovery", "walk"}

# Fallback for legacy plans whose workouts carry no ``steps`` list: map the
# day's coarse type to a pace zone so a single continuous step still targets
# a sensible effort on the watch.
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

# Short trailing step names Intervals.icu accepts (single token, no spaces).
_KIND_LABELS = {
    "warmup": "Warmup",
    "cooldown": "Cooldown",
    "recovery": "Recovery",
    "strides": "Strides",
    "walk": "Walk",
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


def _pace_target(step: dict[str, Any]) -> str:
    """Intervals.icu pace target for a step ('Z4 Pace'), by kind then zone."""
    if step.get("kind") in _EASY_KINDS:
        return "Z1 Pace"
    zone = _ZONE_TO_PACE_ZONE.get(step.get("pace_zone") or "")
    return f"{zone} Pace" if zone else "Z2 Pace"


def _step_line(step: dict[str, Any]) -> Optional[str]:
    """Render one step as a ``- <amount> <target> [Name]`` line.

    Returns None for open steps (no distance and no duration), which have no
    Intervals.icu duration token and are skipped.
    """
    if step.get("distance_m"):
        amount = _format_distance_km(step["distance_m"])
    elif step.get("duration_s"):
        amount = _format_duration(int(step["duration_s"]))
    else:
        return None
    line = f"- {amount} {_pace_target(step)}"
    label = _KIND_LABELS.get(step.get("kind") or "")
    if label:
        line += f" {label}"
    return line


def _blocks(steps: list[dict[str, Any]]) -> list[str]:
    """Group steps into Intervals.icu text blocks, keeping repeats as ``Nx``.

    A ``run`` step with ``repeat > 1`` immediately followed by a matching
    ``recovery``/``walk`` step is emitted as one ``Nx`` block wrapping both,
    mirroring how the session actually alternates work and rest.
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
            and nxt.get("kind") in ("recovery", "walk")
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
