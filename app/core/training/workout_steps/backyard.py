"""Backyard step builders: loop simulations, turnarounds, and loop repeats.

Training sessions are emitted as one explicit step per loop rather than a
compressed ``N ×`` block. That is deliberate: the runner's job in a
simulation is to treat every loop as its own event, and a step list that says
"Loop 1 … Loop 6" reads the way the race is actually experienced — whereas
``6 × 6.7 km`` reads like an interval session and hides the thing that makes
it hard, which is the eleven minutes of sitting down in between. Race day is
the one exception (:func:`build_backyard_race_steps`): forty loops spelled
out is a step list nobody reads and no watch wants.

The turnaround is modelled as a ``rest`` step with no pace zone, so it costs
the session no distance (see ``compute_distance_from_steps_checked``) while
still occupying the clock on the watch and in the PDF.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.training.workout_steps.primitives import _pace_str, _step
from app.utils import format_km, format_pace

# Loop-pace repeats stand still between reps rather than jogging: the whole
# point is rehearsing a cold restart, and a jog recovery quietly removes it.
_LOOP_REPEAT_STANDING_REST_MIN = 6.0


def _loop_pace_str(
    loop_pace_min_km: Optional[float], pace_zones: Optional[Dict]
) -> Optional[str]:
    """Prefer the goal's own loop pace; fall back to the easy zone."""
    if loop_pace_min_km and loop_pace_min_km > 0:
        return format_pace(loop_pace_min_km)
    return _pace_str("E", pace_zones)


def _turnaround_step(minutes: float, note: Optional[str] = None) -> Dict[str, Any]:
    return _step(
        "rest",
        f"Turnaround — {round(minutes)} min",
        duration_s=int(round(minutes * 60)),
        effort="off the feet",
        note=note,
    )


def build_loop_simulation_steps(
    loops: int,
    loop_km: float,
    loop_budget_min: float,
    turnaround_min: float,
    pace_zones: Optional[Dict] = None,
    loop_pace_min_km: Optional[float] = None,
    overnight: bool = False,
) -> List[Dict[str, Any]]:
    """A simulation as it is run: loop, turnaround, loop, turnaround…

    The final loop carries no turnaround after it — the session ends when the
    runner stops, which in a real backyard is the only way it ever ends.
    """
    if loops <= 0 or loop_km <= 0:
        return []

    pace_str = _loop_pace_str(loop_pace_min_km, pace_zones)
    loop_m = int(round(loop_km * 1000))

    steps: List[Dict[str, Any]] = []
    for loop in range(1, loops + 1):
        note: Optional[str] = None
        if loop == 1:
            note = (
                "Start on the hour. Go out slower than feels right — the first "
                "loop sets the pace you'll still be holding hours from now."
            )
        elif overnight and loop == 2:
            note = "Headlamp on before you need it, not after."
        elif loop == loops:
            note = "Last one. Finish it at the same pace as the first."
        steps.append(
            _step(
                "run",
                f"Loop {loop} — {format_km(loop_km)} km in ~{round(loop_budget_min)} min",
                distance_m=loop_m,
                pace_zone="E",
                pace_str=pace_str,
                effort="controlled",
                note=note,
            )
        )
        if loop < loops:
            steps.append(
                _turnaround_step(
                    turnaround_min,
                    note=(
                        "Eat and drink something every single turnaround, "
                        "whether you want it or not."
                        if loop == 1
                        else None
                    ),
                )
            )
    return steps


def build_turnaround_drill_steps(
    reps: int,
    loop_km: float,
    loop_budget_min: float,
    turnaround_min: float,
    pace_zones: Optional[Dict] = None,
    loop_pace_min_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """A short mid-week rehearsal of the transition, not of the distance.

    Same shape as a simulation but only a few loops long, and the turnaround
    is where the work is: the runner practises the full routine — pack down,
    eat, refill, foot check, corral — against a clock they cannot argue with.
    """
    if reps <= 0 or loop_km <= 0:
        return []

    pace_str = _loop_pace_str(loop_pace_min_km, pace_zones)
    loop_m = int(round(loop_km * 1000))

    steps: List[Dict[str, Any]] = []
    for rep in range(1, reps + 1):
        steps.append(
            _step(
                "run",
                f"Loop {rep} — {format_km(loop_km)} km in ~{round(loop_budget_min)} min",
                distance_m=loop_m,
                pace_zone="E",
                pace_str=pace_str,
                effort="controlled",
                note=(
                    f"Target {round(loop_budget_min)} min. Being early is not a "
                    "bonus — it's pace you didn't need to spend."
                    if rep == 1
                    else None
                ),
            )
        )
        if rep < reps:
            steps.append(
                _turnaround_step(
                    turnaround_min,
                    note=(
                        "Full routine every time: bottle, food, feet, kit, "
                        "corral. Time it."
                    ),
                )
            )
    return steps


def build_loop_repeats_steps(
    reps: int,
    loop_km: float,
    pace_zones: Optional[Dict] = None,
    loop_pace_min_km: Optional[float] = None,
    standing_rest_min: float = _LOOP_REPEAT_STANDING_REST_MIN,
) -> List[Dict[str, Any]]:
    """Loop-distance repeats at goal loop pace off a *standing* rest.

    The pace itself is easy; what this session trains is hitting it from cold
    legs, over and over, without drifting faster. Standing rest rather than a
    jog recovery — the restart is the stimulus.
    """
    if reps <= 0 or loop_km <= 0:
        return []

    pace_str = _loop_pace_str(loop_pace_min_km, pace_zones)
    loop_m = int(round(loop_km * 1000))

    steps: List[Dict[str, Any]] = []
    for rep in range(1, reps + 1):
        steps.append(
            _step(
                "run",
                f"{format_km(loop_km)} km loop rep",
                distance_m=loop_m,
                pace_zone="E",
                pace_str=pace_str,
                effort="controlled",
                note=(
                    "Hold the same split every rep. A fast one is a mistake, not a win."
                    if rep == 1
                    else None
                ),
            )
        )
        if rep < reps:
            steps.append(
                _step(
                    "rest",
                    f"{round(standing_rest_min)} min standing rest",
                    duration_s=int(round(standing_rest_min * 60)),
                    effort="off the feet",
                    note=(
                        "Sit down. Restarting cold is the whole point."
                        if rep == 1
                        else None
                    ),
                )
            )
    return steps


def build_backyard_race_steps(
    target_loops: int,
    loop_km: float,
    loop_budget_min: float,
    turnaround_min: float,
    pace_zones: Optional[Dict] = None,
    loop_pace_min_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Race day, compressed.

    Unlike a simulation, the race can run to forty-plus loops, and a step per
    loop would be a step list nobody reads and no watch wants. The opening
    loop is spelled out because it is the one that decides the race — it is
    where every runner goes too fast — and the remainder is a single repeated
    (loop, turnaround) block, which is honestly what the next thirty hours are.

    That block ends on a turnaround rather than on a loop, because a backyard
    does too: the race is over at the moment somebody doesn't come back out.
    """
    if target_loops <= 0 or loop_km <= 0:
        return []

    pace_str = _loop_pace_str(loop_pace_min_km, pace_zones)
    loop_m = int(round(loop_km * 1000))

    def _loop_step(label: str, note: Optional[str], repeat: int = 1):
        return _step(
            "run",
            label,
            distance_m=loop_m,
            repeat=repeat,
            pace_zone="E",
            pace_str=pace_str,
            effort="controlled",
            note=note,
        )

    steps: List[Dict[str, Any]] = [
        _loop_step(
            f"Loop 1 — {format_km(loop_km)} km",
            f"Target {round(loop_budget_min)} min. Everyone runs the first "
            "loop too fast; the ones still there tomorrow didn't.",
        ),
        _turnaround_step(
            turnaround_min,
            note="Eat, drink, feet, kit, corral. Every hour, without fail.",
        ),
    ]
    remaining = target_loops - 1
    if remaining > 0:
        steps.append(
            _loop_step(
                f"Loops 2–{target_loops} — {format_km(loop_km)} km each",
                "Same loop, same split, one hour at a time.",
                repeat=remaining,
            )
        )
        steps.append(
            _step(
                "rest",
                f"Turnaround — {round(turnaround_min)} min",
                duration_s=int(round(turnaround_min * 60)),
                repeat=remaining,
                effort="off the feet",
                note="Back in the corral before the whistle, every single time.",
            )
        )
    return steps
