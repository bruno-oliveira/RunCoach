"""Self-contained helpers for plan customization (intensity, distance, swap, AI).

Type/distance changes route through the same builders plan generation uses
(``build_workout`` / key-workout rebuild), so a customised workout's distance,
description and steps stay in lockstep instead of drifting apart — the older
implementation string-replaced prose and hand-wrote notes/distances, which left
the structured ``steps`` (and, for generated plans that use ``description`` not
``notes``, the prose itself) stale.
"""

from typing import Any, Optional

from app.core.training import key_workout_library as _kwlib
from app.core.training.workout_registry import WORKOUT_REGISTRY, build_workout
from app.core.training.workout_steps import _compute_distance_from_steps

_KNOWN_TYPES = set(WORKOUT_REGISTRY)

# Race day is not editable through the plan-adjustment surface. Its distance is
# the event's, and it is the one session the whole plan was built to reach —
# a mis-drop or an idle type change on the final day would delete the goal race
# and nothing downstream would put it back (the race is installed once, during
# generation). "race" is also absent from WORKOUT_REGISTRY, so it can never be
# a swap *target* either.
_IMMUTABLE_TYPES = frozenset({"race"})


def _is_immutable(workout: Optional[dict]) -> bool:
    return bool(workout) and workout.get("type") in _IMMUTABLE_TYPES


_OVERLAY_KEYS = (
    "key_workout_id",
    "key_workout_name",
    "structure",
    "key_workout_rationale",
)


def _merge_built(wo: dict, built: dict) -> None:
    """Copy a freshly built workout's fields onto a plan_data workout dict."""
    wo["type"] = built.get("type", wo.get("type"))
    wo["distance"] = round(built.get("distance", wo.get("distance", 0)) or 0, 1)
    wo["intensity"] = built.get("intensity", wo.get("intensity", "low"))
    description = built.get("description", "")
    wo["description"] = description
    wo["notes"] = description  # keep any legacy 'notes' consumers in sync
    steps = built.get("steps")
    if steps is not None:
        wo["steps"] = steps
        # Adopt the steps total as the authoritative distance (some builders,
        # e.g. tempo, report the requested distance rather than what the steps
        # actually deliver) so distance == steps stays true.
        steps_total = _compute_distance_from_steps(steps)
        if steps_total > 0:
            wo["distance"] = round(steps_total, 1)
    else:
        wo.pop("steps", None)


def _regenerate(
    wo: dict,
    *,
    new_type: Optional[str],
    new_distance: float,
    phase: str,
    total_km: float,
    pace_zones: Optional[dict],
) -> None:
    """Regenerate a plan_data workout in place at a new type/distance.

    Produces a consistent ``{type, distance, intensity, description, steps}``
    via the same builders generation uses. Key-workout overlays are preserved
    by re-running their library rebuild; a genuine type change drops the
    (now-irrelevant) overlay and stale coaching note.
    """
    target_type = (new_type or wo.get("type") or "easy").strip()
    type_changed = new_type is not None and new_type != wo.get("type")
    if type_changed:
        for key in (*_OVERLAY_KEYS, "coaching_rationale"):
            wo.pop(key, None)

    wo["type"] = target_type
    wo["distance"] = round(new_distance, 1)

    # Preserve a curated key workout (e.g. a marathon-pace long run) by
    # rebuilding it from the new distance rather than replacing it with a
    # generic build.
    if not type_changed and wo.get("key_workout_id"):
        if _kwlib.rebuild_key_workout(wo, pace_zones):
            return

    built = build_workout(
        target_type,
        day=wo.get("day", 1),
        distance=new_distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
    )
    _merge_built(wo, built)


def _recompute_total(week: dict) -> None:
    week["total_km"] = round(
        sum((w.get("distance") or 0) for w in week.get("daily_workouts", [])), 1
    )


def _default_run_distance(week: dict) -> float:
    """A sensible distance for a brand-new run (mean of the week's runs)."""
    dists = [
        w.get("distance") or 0
        for w in week.get("daily_workouts", [])
        if (w.get("distance") or 0) > 0 and w.get("type") not in ("rest", "recovery")
    ]
    return round(sum(dists) / len(dists), 1) if dists else 5.0


def adjust_intensity(
    plan_data: list[dict],
    week_number: int,
    intensity_level: str,
    pace_zones: Optional[dict[str, Any]] = None,
) -> list[dict]:
    """Dial a week's intensity by converting workout types, structurally.

    ``low`` demotes quality (tempo/interval/hill) to easy; ``high`` promotes
    easy runs to tempo. Each converted workout is regenerated so its distance,
    description and steps stay consistent.
    """
    for week in plan_data:
        if week.get("week") != week_number:
            continue
        phase = week.get("phase", "build")
        total_km = week.get("total_km") or 0.0
        for wo in week.get("daily_workouts", []):
            wtype = wo.get("type")
            if intensity_level == "low" and wtype in ("tempo", "interval", "hill"):
                _regenerate(
                    wo,
                    new_type="easy",
                    new_distance=wo.get("distance") or 0.0,
                    phase=phase,
                    total_km=total_km,
                    pace_zones=pace_zones,
                )
            elif intensity_level == "high" and wtype == "easy":
                _regenerate(
                    wo,
                    new_type="tempo",
                    new_distance=wo.get("distance") or 0.0,
                    phase=phase,
                    total_km=total_km,
                    pace_zones=pace_zones,
                )
        _recompute_total(week)
    return plan_data


def swap_workout(
    plan_data: list[dict],
    week_number: int,
    swap_info: str,
    pace_zones: Optional[dict[str, Any]] = None,
) -> list[dict]:
    """Swap a single day's workout to a new type, regenerated structurally.

    ``swap_info`` is ``"<day>,<new_type>"``. A rest→run swap seeds a sensible
    distance from the week's other runs instead of a hard-coded 5 km.
    """
    try:
        day_str, raw_type = swap_info.split(",")
        day = int(day_str)
    except (ValueError, TypeError):
        return plan_data
    new_type = raw_type.strip()
    if new_type not in _KNOWN_TYPES:
        return plan_data

    for week in plan_data:
        if week.get("week") != week_number:
            continue
        phase = week.get("phase", "build")
        total_km = week.get("total_km") or 0.0
        wo = next(
            (w for w in week.get("daily_workouts", []) if w.get("day") == day), None
        )
        if wo is None or _is_immutable(wo):
            continue
        if new_type in ("rest", "recovery"):
            distance = 0.0
        else:
            distance = wo.get("distance") or 0.0
            if distance <= 0:  # swapping a rest day into a run
                distance = _default_run_distance(week)
        _regenerate(
            wo,
            new_type=new_type,
            new_distance=distance,
            phase=phase,
            total_km=total_km,
            pace_zones=pace_zones,
        )
        _recompute_total(week)
    return plan_data


def swap_days(
    plan_data: list[dict], week_number: int, source_day: int, target_day: int
) -> list[dict]:
    """Swap two workouts within a week by exchanging their day assignments."""
    for week in plan_data:
        if week["week"] == week_number:
            workouts = week.get("daily_workouts", [])
            src = next((w for w in workouts if w.get("day") == source_day), None)
            tgt = next((w for w in workouts if w.get("day") == target_day), None)
            if _is_immutable(src) or _is_immutable(tgt):
                break
            if src and tgt:
                src["day"], tgt["day"] = tgt["day"], src["day"]
                week["daily_workouts"] = sorted(workouts, key=lambda w: w.get("day", 0))
            break
    return plan_data


def adjust_distance(
    plan_data: list[dict], week_number: int, distance_change: float
) -> list[dict]:
    """Adjust distances for all workouts in a week."""
    for week in plan_data:
        if week["week"] == week_number:
            current_total = sum(
                w.get("distance", 0) for w in week.get("daily_workouts", [])
            )

            if current_total > 0:
                ratio = max(0.0, (current_total + distance_change) / current_total)

                for workout in week.get("daily_workouts", []):
                    if workout["distance"] > 0 and not _is_immutable(workout):
                        workout["distance"] = round(workout["distance"] * ratio, 1)

                week["total_km"] = round(
                    sum(w.get("distance", 0) for w in week.get("daily_workouts", [])), 1
                )

    return plan_data


def apply_ai_suggestions(
    plan_data: list[dict],
    week_number: int,
    preference: str,
    pace_zones: Optional[dict[str, Any]] = None,
) -> list[dict]:
    """Apply a preference to one week, regenerating the affected workout.

    ``more_speed`` converts an easy run to a real interval session (with steps),
    ``more_endurance`` extends the long run, ``more_rest`` turns an easy run
    into a rest day — all via the shared builders instead of hand-written prose.
    """
    for week in plan_data:
        if week.get("week") != week_number:
            continue
        phase = week.get("phase", "build")
        total_km = week.get("total_km") or 0.0
        workouts = week.get("daily_workouts", [])

        if preference == "more_rest":
            wo = next((w for w in workouts if w.get("type") == "easy"), None)
            if wo is not None:
                _regenerate(
                    wo,
                    new_type="rest",
                    new_distance=0.0,
                    phase=phase,
                    total_km=total_km,
                    pace_zones=pace_zones,
                )
        elif preference == "more_speed":
            wo = next((w for w in workouts if w.get("type") == "easy"), None)
            if wo is not None:
                _regenerate(
                    wo,
                    new_type="interval",
                    new_distance=wo.get("distance") or _default_run_distance(week),
                    phase=phase,
                    total_km=total_km,
                    pace_zones=pace_zones,
                )
        elif preference == "more_endurance":
            wo = next((w for w in workouts if w.get("type") == "long"), None)
            if wo is not None:
                _regenerate(
                    wo,
                    new_type=None,  # keep type (preserves a key long run)
                    new_distance=round((wo.get("distance") or 0) * 1.2, 1),
                    phase=phase,
                    total_km=total_km,
                    pace_zones=pace_zones,
                )

        _recompute_total(week)
    return plan_data
