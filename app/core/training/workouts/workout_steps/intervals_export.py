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
    Header text becomes a per-rep counter on the watch (``Rep 3/5``).
  * Text before a step's duration is the cue the watch announces for it
    (``- Recovery 90s``). Walks, rests and hill reps carry a cue but no pace
    target: they are run by feel, and a pace alarm on them only ever beeps.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.training.workouts.workout_steps.metrics import (
    _DEFAULT_PACES,
    _parse_pace_str_to_min_per_km,
)
from app.core.training.workouts.workout_steps.structure import (
    group_steps,
    is_recovery,
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
    """Seconds -> Intervals.icu duration token ('10m', '2m30s', '45s')."""
    minutes, seconds = divmod(duration_s, 60)
    if not minutes:
        return f"{seconds}s"
    return f"{minutes}m{seconds}s" if seconds else f"{minutes}m"


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
    """Default min/km for a work/bookend step with no pace_str (pre-VDOT plans)."""
    zone = step.get("pace_zone")
    if zone and zone in _DEFAULT_PACES:
        return _DEFAULT_PACES[zone]
    if step.get("kind") in ("warmup", "cooldown"):
        return _DEFAULT_PACES["E"]
    return None


def is_hill(step: dict[str, Any]) -> bool:
    text = f"{step.get('label') or ''} {step.get('effort') or ''}".lower()
    return "hill" in text


def is_walk(step: dict[str, Any]) -> bool:
    effort = (step.get("effort") or "").lower()
    return (
        step.get("kind") == "walk"
        or step.get("pace_zone") == "WALK"
        or effort.startswith("walk")
    )


def is_open_effort(step: dict[str, Any]) -> bool:
    """Steps run by feel, where an absolute pace alarm would be wrong.

    Walks and rests have no running pace; a hill rep's pace depends on the
    gradient, so a flat-ground number beeps "too slow" all the way up; and an
    implied stride recovery is a walk/jog back.
    """
    return (
        step.get("kind") == "rest"
        or step.get("implied", False)
        or is_walk(step)
        or is_hill(step)
    )


def resolve_pace_bounds(
    step: dict[str, Any],
    zone_paces: dict[str, str],
    *,
    allow_default: bool = True,
) -> Optional[list[float]]:
    """The min/km bounds a step targets, or None when it is run by feel.

    A recovery with a zone but no pace of its own borrows the runner's pace for
    that zone from a sibling step (the warm-up's easy range). With nothing to
    borrow it stays open: an 8:00/km default is not the runner's number, and a
    recovery jog that beeps "slow down" every rep is worse than no target.
    ``allow_default=False`` also refuses the zone defaults for work steps — the
    screens use that, so they never print a generic pace as if it were yours.
    """
    if is_open_effort(step):
        return None
    bounds = _parse_pace_bounds(step.get("pace_str"))
    zone = step.get("pace_zone")
    if not bounds and zone in zone_paces:
        bounds = _parse_pace_bounds(zone_paces[zone])
    if bounds:
        return bounds
    if step.get("kind") == "recovery" or not allow_default:
        return None
    fallback = _fallback_pace(step)
    return [fallback] if fallback is not None else None


def _pace_target(step: dict[str, Any], zone_paces: dict[str, str]) -> Optional[str]:
    """Absolute Intervals.icu pace target for a step, or None for an open step."""
    bounds = resolve_pace_bounds(step, zone_paces)
    if not bounds:
        return None
    if len(bounds) == 1:
        return f"{_fmt_pace(bounds[0])} Pace"
    return f"{_fmt_pace(min(bounds))}-{_fmt_pace(max(bounds))} Pace"


# Step cue text: everything before the duration becomes the prompt the watch
# shows for the step. Kept free of digits so Intervals.icu can never read part
# of the cue as the duration ("10K pace" would be a gamble).
_ZONE_CUES = {
    "E": "Easy",
    "M": "Marathon pace",
    "T": "Threshold",
    "I": "Interval",
    "R": "Fast",
    "5K": "Five-K pace",
    "10K": "Ten-K pace",
    "race": "Race pace",
}


def step_cue(step: dict[str, Any]) -> str:
    """Short, digit-free name for a step, as the watch should announce it."""
    kind = step.get("kind")
    if step.get("implied"):
        return "Jog back"
    if kind == "warmup":
        return "Warmup"
    if kind == "cooldown":
        return "Cooldown"
    if kind == "rest":
        return "Rest"
    if kind == "walk":
        return "Power hike" if "hike" in (step.get("effort") or "") else "Walk"
    if kind == "recovery":
        return "Walk" if is_walk(step) else "Recovery"
    if kind == "strides":
        return "Stride"
    if is_hill(step):
        return "Hill"
    if (step.get("label") or "").startswith("Loop"):
        return "Loop"
    return _ZONE_CUES.get(step.get("pace_zone") or "", "Run")


def _step_line(step: dict[str, Any], zone_paces: dict[str, str]) -> Optional[str]:
    """Render one step as a ``- <cue> <amount> [<pace> Pace]`` line.

    Returns None for open steps (no distance and no duration), which have no
    Intervals.icu duration token and are skipped.
    """
    if step.get("distance_m"):
        amount = _format_distance_km(step["distance_m"])
    elif step.get("duration_s"):
        amount = _format_duration(int(step["duration_s"]))
    else:
        return None
    parts = [f"- {step_cue(step)} {amount}"]
    target = _pace_target(step, zone_paces)
    if target:
        parts.append(target)
    return " ".join(parts)


def zone_paces_of(steps: list[dict[str, Any]]) -> dict[str, str]:
    """The first concrete pace each zone carries anywhere in the session."""
    paces: dict[str, str] = {}
    for step in steps:
        zone, pace = step.get("pace_zone"), step.get("pace_str")
        if zone and pace and zone not in paces:
            paces[zone] = pace
    return paces


def _blocks(steps: list[dict[str, Any]]) -> list[str]:
    """Render the grouped session as Intervals.icu text blocks.

    Grouping is :func:`group_steps`' job, shared with every screen that shows
    the session, so the watch runs the structure the runner reads. A repeat
    header is written ``Rep Nx`` because Intervals turns header text into a
    per-rep counter on the watch ("Rep 3/5"). A block whose last recovery is
    skipped goes up as ``(N-1)x`` rep+recovery followed by one bare rep —
    Intervals has no "skip the last recovery" syntax, and the expansion is
    exactly what the runner does.
    """
    zone_paces = zone_paces_of(steps)
    out: list[str] = []
    for block in group_steps(steps):
        lines = [ln for ln in (_step_line(s, zone_paces) for s in block["steps"]) if ln]
        if not lines:
            continue
        reps = block["repeat"]
        if reps <= 1:
            out.extend(lines)
            continue
        if not block["skip_last_recovery"]:
            out.append("\n".join([f"Rep {reps}x", *lines]))
            continue
        work = [
            ln
            for ln in (
                _step_line(s, zone_paces) for s in block["steps"] if not is_recovery(s)
            )
            if ln
        ]
        if reps - 1 > 1:
            out.append("\n".join([f"Rep {reps - 1}x", *lines]))
        else:
            out.extend(lines)
        out.extend(work)
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
