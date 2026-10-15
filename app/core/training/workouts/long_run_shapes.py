"""Long-run shapes: a chosen long run laid over whatever distance the day has.

A key workout is a prescription: its steps fix the distance, so a pinned long
run cannot absorb the week's volume and the volume guard in
``generate_daily_workouts`` refuses most of them (measured: well under half the
build and peak long runs at 3 and 5 runs a week). Every long run in the Flat to
Mountain library is a *shape* instead — thirds, a final fifth, surges sprinkled
through, blocks folded in — so it can be laid over any distance.

A shaped long run therefore stays **flexible**. It carries ``long_shape_id`` (not
``key_workout_id``), every budget pass may resize it, and each resize
re-lays the same shape through :func:`build_shaped_long_run`, so the card, the
steps and the distance never disagree. The prose names no pace (the steps
carry it) and only the kilometres it is re-rendered with.

Pure: no I/O, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.formatting import format_km
from app.core.training.workouts.workout_steps.primitives import _pace_str, _step

# Hard ceilings on how much of a shaped long run may be quality. A long run is
# still an aerobic day; the shape adds a rehearsal, never a second quality day.
MAX_SHAPE_THRESHOLD_SHARE = 0.25  # T or faster
MAX_SHAPE_QUALITY_SHARE = 0.40  # M or faster


@dataclass(frozen=True)
class LongRunShape:
    """One long-run session the runner can choose."""

    id: str
    name: str
    structure: str
    rationale: str
    phases: Tuple[str, ...]
    build: Callable[[int, Optional[Dict]], Tuple[List[Dict[str, Any]], str]]


def _m(km: float) -> int:
    return int(round(km * 1000))


def _km(metres: int) -> str:
    return format_km(metres / 1000)


def _easy(label: str, metres: int, pace_zones, effort: str = "conversational"):
    return _step(
        "run",
        label,
        distance_m=metres,
        pace_zone="E",
        pace_str=_pace_str("E", pace_zones),
        effort=effort,
    )


def _steady_long(total_m: int, pace_zones) -> Tuple[List[Dict[str, Any]], str]:
    steps = [_easy("Easy aerobic", total_m, pace_zones)]
    return (
        steps,
        f"Steady long run: {_km(total_m)} km at an easy, conversational effort.",
    )


def _negative_split(total_m: int, pace_zones) -> Tuple[List[Dict[str, Any]], str]:
    third = total_m // 3
    last = total_m - 2 * third
    steps = [
        _easy("Easy start", third, pace_zones),
        _easy("Steady middle", third, pace_zones, effort="moderate"),
        _step(
            "run",
            "Marathon-pace finish",
            distance_m=last,
            pace_zone="M",
            pace_str=_pace_str("M", pace_zones),
            effort="strong finish",
        ),
    ]
    prose = (
        f"Negative split: {_km(third)} km easy, {_km(third)} km steady, then the "
        f"final {_km(last)} km at marathon effort. If you cannot speed up in the "
        "final third, you started too fast."
    )
    return steps, prose


def _fast_finish(total_m: int, pace_zones) -> Tuple[List[Dict[str, Any]], str]:
    finish = min(5000, max(2000, int(total_m * 0.2) // 100 * 100))
    finish = min(finish, int(total_m * MAX_SHAPE_THRESHOLD_SHARE) // 100 * 100)
    easy = total_m - finish
    steps = [
        _easy("Easy aerobic base", easy, pace_zones),
        _step(
            "run",
            "Fast finish",
            distance_m=finish,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="comfortably hard",
            note="Build effort through the last km",
        ),
    ]
    prose = (
        f"Fast-finish long run: {_km(easy)} km easy, then the final "
        f"{_km(finish)} km at threshold effort, committed."
    )
    return steps, prose


def _sandwich(total_m: int, pace_zones) -> Tuple[List[Dict[str, Any]], str]:
    blocks = 3 if total_m >= 15000 else 2
    block_m = int(total_m * 0.30 / blocks) // 100 * 100
    float_m = 1000
    work_m = blocks * block_m + (blocks - 1) * float_m
    opening = int((total_m - work_m) * 0.6) // 100 * 100
    closing = total_m - work_m - opening
    steps: List[Dict[str, Any]] = [_easy("Easy start", opening, pace_zones)]
    for i in range(blocks):
        steps.append(
            _step(
                "run",
                "Steady block",
                distance_m=block_m,
                pace_zone="M",
                pace_str=_pace_str("M", pace_zones),
                effort="comfortably hard",
            )
        )
        if i < blocks - 1:
            steps.append(_easy("Float", float_m, pace_zones, effort="easy"))
    steps.append(_easy("Easy finish", closing, pace_zones))
    prose = (
        f"Sandwich long run: {_km(opening)} km easy, then {blocks} × "
        f"{_km(block_m)} km at marathon effort with {_km(float_m)} km easy "
        f"between, and {_km(closing)} km easy to finish."
    )
    return steps, prose


def _surges(total_m: int, pace_zones) -> Tuple[List[Dict[str, Any]], str]:
    surges = max(6, min(12, round(total_m / 2000)))
    surge_m = 200
    opening = int(total_m * 0.2) // 100 * 100
    closing = int(total_m * 0.2) // 100 * 100
    middle = total_m - opening - closing
    float_m = max(300, (middle - surges * surge_m) // surges)
    middle_used = surges * (surge_m + float_m)
    closing += middle - middle_used
    steps = [
        _easy("Easy start", opening, pace_zones),
        _step(
            "run",
            "Surge",
            distance_m=surge_m,
            repeat=surges,
            pace_zone="T",
            pace_str=_pace_str("T", pace_zones),
            effort="hard",
            note="About a minute — then straight back to easy",
        ),
        _easy("Easy between surges", float_m, pace_zones),
        _easy("Easy finish", closing, pace_zones),
    ]
    # Work steps sharing a repeat count alternate (``group_steps``), so the
    # surge and its easy float run as one block of ``surges`` reps.
    steps[2]["repeat"] = surges
    prose = (
        f"Surge long run: an easy {_km(total_m)} km with {surges} one-minute "
        "surges at threshold effort sprinkled through the middle — return to easy "
        "between them."
    )
    return steps, prose


SHAPES: Dict[str, LongRunShape] = {
    s.id: s
    for s in (
        LongRunShape(
            id="steady_long",
            name="Steady Long Run",
            structure="the whole run at an easy, conversational effort",
            rationale=(
                "Time on your feet at easy effort builds the aerobic engine and "
                "the durability every other session leans on."
            ),
            phases=("base", "build", "peak"),
            build=_steady_long,
        ),
        LongRunShape(
            id="negative_split_long",
            name="Negative Split",
            structure="thirds: easy → steady → marathon effort",
            rationale=(
                "A long race is decided in its final hour, on tired legs. Finishing "
                "faster than you started teaches pacing patience and strength late."
            ),
            phases=("base", "build", "peak"),
            build=_negative_split,
        ),
        LongRunShape(
            id="fast_finish_long",
            name="Fast-Finish Long Run",
            structure="easy, then the final fifth at threshold effort",
            rationale=(
                "Rehearses the mental gearshift at 'everything hurts, 5 km to go' "
                "without the cost of a full race effort."
            ),
            phases=("build", "peak"),
            build=_fast_finish,
        ),
        LongRunShape(
            id="sandwich_long",
            name="Sandwich Long Run",
            structure="easy, then marathon-effort blocks folded in, easy to finish",
            rationale=(
                "Hard efforts arrive mid-race, not fresh. Steady blocks deep in a "
                "long run rehearse that with the fatigue included."
            ),
            phases=("build", "peak"),
            build=_sandwich,
        ),
        LongRunShape(
            id="surge_long",
            name="Surge Long Run",
            structure="easy, with one-minute surges sprinkled through the middle",
            rationale=(
                "The course decides when you surge, not you. Random surges teach "
                "the gear change and the return to easy effort."
            ),
            phases=("base", "build", "peak"),
            build=_surges,
        ),
    )
}


def get_shape(shape_id: Optional[str]) -> Optional[LongRunShape]:
    """The shape with this id, or ``None``."""
    return SHAPES.get(shape_id or "")


def shapes_for_phase(phase: str) -> List[LongRunShape]:
    """Every shape a runner may choose for a phase, in catalogue order."""
    return [s for s in SHAPES.values() if phase in s.phases]


def build_shaped_long_run(
    shape_id: str,
    day: int,
    distance: float,
    pace_zones: Optional[Dict] = None,
) -> Optional[Dict[str, Any]]:
    """A long-run card laying ``shape_id`` over ``distance``.

    Returns ``None`` for an unknown shape or a non-positive distance, so a
    caller falls back to the plain long run rather than inventing a session.
    """
    shape = get_shape(shape_id)
    if shape is None or distance <= 0:
        return None
    total_m = _m(round(distance, 1))
    steps, prose = shape.build(total_m, pace_zones)
    return {
        "day": day,
        "type": "long",
        "distance": round(distance, 1),
        "intensity": "medium",
        "description": prose,
        "steps": steps,
        "long_shape_id": shape.id,
        "key_workout_name": shape.name,
        "structure": shape.structure,
        "coaching_rationale": shape.rationale,
    }


# Fields a shaped long run owns. A rebuild copies all of them; a day that stops
# being this session (a type change, a rest day) must drop all of them.
SHAPE_CARD_KEYS = (
    "description",
    "steps",
    "intensity",
    "type",
    "distance",
    "long_shape_id",
    "key_workout_name",
    "structure",
    "coaching_rationale",
)


def reshape_long_card(
    card: Dict[str, Any], distance: float, pace_zones: Optional[Dict]
) -> bool:
    """Re-lay a shaped long run's own shape at ``distance``, in place.

    Returns False (and leaves the card alone) when the card carries no shape,
    so callers keep their plain-long-run path for everything else.
    """
    shape_id = card.get("long_shape_id")
    if not shape_id or card.get("type") != "long":
        return False
    rebuilt = build_shaped_long_run(shape_id, card.get("day", 0), distance, pace_zones)
    if rebuilt is None:
        return False
    for key in SHAPE_CARD_KEYS:
        card[key] = rebuilt[key]
    return True


def shape_zone_shares(steps: List[Dict[str, Any]]) -> Tuple[float, float]:
    """(share at T or faster, share at M or faster) of a shape's distance."""
    total = 0
    threshold = 0
    quality = 0
    for step in steps:
        metres = (step.get("distance_m") or 0) * (step.get("repeat") or 1)
        total += metres
        zone = step.get("pace_zone")
        if zone in ("T", "I", "R"):
            threshold += metres
        if zone in ("M", "T", "I", "R"):
            quality += metres
    if total <= 0:
        return 0.0, 0.0
    return threshold / total, quality / total
