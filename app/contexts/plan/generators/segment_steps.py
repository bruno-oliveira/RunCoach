"""Project formulaic segment-based workouts onto the canonical steps model.

The pace/VDOT generators assemble warm-up / main / cool-down *segments* while a
week's distances and paces are capped, reconciled, and described. Once the week
is settled, this adapter projects any remaining segment-based workout onto the
same structured ``steps`` model the road generator and the key-workout overlay
already emit, so every workout in a stored plan — whatever engine produced it —
renders, enriches, and adapts through a single representation.

Build/peak quality sessions are replaced by curated key workouts upstream
(``overlay_key_workout`` pops their segments and installs steps), so they carry
no segments by the time this runs and are left untouched. Rest days carry no
segments either. The projection preserves the workout's settled ``distance``:
the warm-up, working set, and cool-down distances are copied verbatim, and
interval recovery is emitted as a duration-only step (no priced distance) so the
steps total matches the segment total exactly — recovery jog distance is not
part of the performance builders' distance budget.
"""

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import _step

# Performance zone identifier -> canonical pace-zone badge letter (E/M/T/I/R),
# matching the road generator's structured steps so the same zone colours and
# legend apply. "mixed" (fartlek) deliberately maps to no letter.
_ZONE_LETTER: Dict[str, str] = {
    "zone_1": "E",
    "zone_2": "E",
    "zone_3": "T",
    "zone_4": "I",
    "zone_5": "M",
}

_KIND_BY_SEGMENT_TYPE = {"warmup": "warmup", "cooldown": "cooldown"}


def _letter(seg: Dict[str, Any]) -> Optional[str]:
    return _ZONE_LETTER.get(seg.get("zone") or "")


def _distance_m(seg: Dict[str, Any]) -> Optional[int]:
    km = seg.get("distance_km") or 0
    return int(round(km * 1000)) if km > 0 else None


def _segment_to_steps(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert one segment into one or more canonical step dicts."""
    seg_type = seg.get("type", "main")
    kind = _KIND_BY_SEGMENT_TYPE.get(seg_type, "run")
    letter = _letter(seg)
    pace_str = seg.get("pace_formatted")
    name = seg.get("name") or kind.title()
    intervals = seg.get("intervals")

    # Metre-defined reps (VO2max / interval): one working step carrying the rep
    # distance and count, plus a duration-only recovery step that adds no
    # distance (the performance builders price only the work into the total).
    if intervals and isinstance(intervals.get("interval_m"), int):
        reps = intervals.get("reps") or 1
        interval_m = intervals["interval_m"]
        steps = [
            _step(
                "run",
                f"{reps} × {interval_m} m",
                distance_m=interval_m,
                repeat=reps,
                pace_zone=letter,
                pace_str=pace_str,
                effort="hard",
            )
        ]
        recovery_min = intervals.get("recovery_min")
        if recovery_min:
            steps.append(
                _step(
                    "recovery",
                    f"{recovery_min} min jog recovery",
                    duration_s=int(recovery_min * 60),
                    repeat=max(1, reps - 1),
                    effort="jog",
                )
            )
        return steps

    # Time-defined surges (fartlek): a single working step over the main
    # distance, labelled with the surge count and carrying the pace range.
    if intervals:
        reps = intervals.get("reps") or 0
        descriptor = intervals.get("interval_m") or "surges"
        label = f"{reps} × {descriptor}" if reps else name
        return [
            _step(
                "run",
                label,
                distance_m=_distance_m(seg),
                pace_zone=letter,
                pace_str=pace_str,
                effort="hard",
                note="easy running between surges",
            )
        ]

    # Plain block (warm-up / cool-down / steady main).
    effort = "easy" if kind in ("warmup", "cooldown") or letter == "E" else None
    return [
        _step(
            kind,
            name,
            distance_m=_distance_m(seg),
            pace_zone=letter,
            pace_str=pace_str,
            effort=effort,
        )
    ]


def segments_to_steps(workout: Dict[str, Any]) -> None:
    """Replace a workout's ``segments`` with canonical ``steps`` in place.

    No-op when the workout already carries steps (a key-workout overlay) or has
    no segments (rest days). The settled ``segments`` are removed so a stored
    workout never carries both representations.
    """
    if workout.get("steps"):
        return
    segments = workout.get("segments")
    if not segments:
        return
    steps: List[Dict[str, Any]] = []
    for seg in segments:
        steps.extend(_segment_to_steps(seg))
    workout["steps"] = steps
    workout.pop("segments", None)


def apply_steps_model(daily_workouts: List[Dict[str, Any]]) -> None:
    """Project every segment-based workout in a week onto the steps model."""
    for workout in daily_workouts:
        segments_to_steps(workout)
