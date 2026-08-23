"""Backyard Ultra reshaping for a single training week.

A backyard plan is an ultra plan underneath — the aerobic base, the deloads,
the taper are all the same — but three weeks in four it looks nothing like
the race, and that gap is what this post-pass closes:

* **the weekend** becomes a loop simulation when the ladder in
  :mod:`app.core.training.backyard_simulation` calls for one, and the day
  after it becomes either rest (if the simulation ran into the night) or a
  short second day on tired legs, which is what hours eighteen onward
  actually feel like.
* **the midweek quality slot** stops being a tempo. Backyard has no tempo —
  nothing in the race is ever run at threshold. The slot goes to loop-pace
  repeats or a turnaround drill instead, which train the two things that
  decide the race: hitting the rest budget from cold, and getting out of the
  corral on time.

Runs before ``scale_down`` in :func:`build_weekly_plan`, like the trail
Intensive Training Weekend it is modelled on. Every session it installs
carries ``key_workout_id`` (so the week-budget passes treat it as
prescriptive) and ``fixed_structure`` (so adaptation never rescales a whole
number of hourly loops into a fractional one).
"""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.weekly_plan_builder.budget import (
    build_workout_for_type,
)
from app.core.training import workout_builders
from app.core.training.backyard_profile import BackyardProfile
from app.core.training.backyard_simulation import LoopSimulation
from app.core.training.workout_steps.backyard import (
    build_loop_repeats_steps,
    build_loop_simulation_steps,
    build_turnaround_drill_steps,
)
from app.utils import format_km, format_pace

# The simulation takes the long-run slot, which the scheduler anchors on
# Saturday — leaving Sunday free for the second day the format demands.
_SIMULATION_DAY = 6
_SECOND_DAY = 7

# Loops for the day after a simulation. One is a genuine second start on
# stiff legs; two is worth doing only when the simulation itself was big
# enough that the runner is rehearsing the back half of a race rather than
# just adding volume.
_SECOND_DAY_LOOPS_LARGE_SIM = 2
_LARGE_SIM_LOOPS = 5
# The second day only happens if the week can afford it without collapsing
# every other run to its floor: the headroom left after the simulation must be
# comfortably more than the loops the second day would add.
_SECOND_DAY_HEADROOM_FACTOR = 1.6

# Midweek loop repeats: enough to rehearse the restart, not so many that the
# session turns into a simulation the week hasn't budgeted for.
_MIN_LOOP_REPEATS = 2
_MAX_LOOP_REPEATS = 4
# The turnaround drill is deliberately the smaller of the two — its work is
# done standing still.
_TURNAROUND_DRILL_LOOPS = 3

_SIMULATION_KEY_IDS: Dict[str, str] = {
    "introduction": "backyard_loop_simulation",
    "progression": "backyard_loop_simulation",
    "night": "backyard_night_simulation",
    "dress_rehearsal": "backyard_dress_rehearsal",
}


def _loop_pace_str(profile: BackyardProfile) -> str:
    return format_pace(profile.loop_pace_min_km)


def _simulation_description(
    simulation: LoopSimulation, profile: BackyardProfile
) -> str:
    budget = round(profile.loop_budget_minutes)
    turn = round(profile.turnaround_minutes)
    opening = (
        f"{simulation.loops} loops on the hour — {format_km(simulation.distance_km)} km "
        f"over {simulation.elapsed_hours} hours. Run each "
        f"{format_km(profile.loop_km)} km loop in about {budget} min "
        f"({_loop_pace_str(profile)}), then take the remaining ~{turn} min as a "
        "real turnaround: eat, drink, refill, sort your feet, and be back "
        "before the hour."
    )
    if simulation.role == "dress_rehearsal":
        return (
            f"{opening} This is the dress rehearsal — race kit, race shoes, "
            "race food, drop bag laid out the way it will be on the day. "
            "Change nothing between today and the start line."
        )
    if simulation.role == "night":
        return (
            f"{opening} Start in the evening so the later loops run in full "
            "darkness. Headlamp, spare batteries, night layers, and the food "
            "you can still stomach at 2am — find out tonight, not on race night."
        )
    if simulation.role == "introduction":
        return (
            f"{opening} First one of the plan: the goal is to learn the rhythm, "
            "not to prove anything. Finishing this feeling like you could have "
            "done two more is exactly right."
        )
    return (
        f"{opening} Same pace on the last loop as the first — if the splits "
        "drift, the rest budget goes with them."
    )


def _simulation_rationale(simulation: LoopSimulation) -> str:
    if simulation.role == "dress_rehearsal":
        return (
            "The last session that can still teach you something in time to "
            "act on it. Every problem it exposes is one you get to solve "
            "before it costs you loops."
        )
    if simulation.role == "night":
        return (
            "Darkness slows everyone down and the clock doesn't care. Knowing "
            "what a headlamp costs you per loop is the difference between "
            "pacing the night and being timed out by it."
        )
    return (
        "A long run teaches you to keep going; a backyard asks you to stop and "
        "start again on cold legs, over and over. Only the format itself "
        "trains that."
    )


def _build_simulation_workout(
    day: int,
    simulation: LoopSimulation,
    profile: BackyardProfile,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict],
) -> Dict[str, Any]:
    workout = build_workout_for_type(
        "long", day, simulation.distance_km, total_km, phase, pace_zones
    )
    workout["distance"] = simulation.distance_km
    workout["key_workout_id"] = _SIMULATION_KEY_IDS.get(
        simulation.role, "backyard_loop_simulation"
    )
    workout["key_workout_name"] = simulation.label
    workout["structure"] = (
        f"{simulation.loops} × {format_km(profile.loop_km)} km loop, one on "
        f"each hour, with the full turnaround between"
    )
    workout["description"] = _simulation_description(simulation, profile)
    workout["coaching_rationale"] = _simulation_rationale(simulation)
    workout["steps"] = build_loop_simulation_steps(
        simulation.loops,
        profile.loop_km,
        profile.loop_budget_minutes,
        profile.turnaround_minutes,
        pace_zones,
        loop_pace_min_km=profile.loop_pace_min_km,
        overnight=simulation.is_overnight,
    )
    workout["fixed_structure"] = True
    workout["backyard_simulation"] = {
        "loops": simulation.loops,
        "role": simulation.role,
        "start_time": simulation.start_time,
        "elapsed_hours": simulation.elapsed_hours,
    }
    return workout


def _build_second_day_workout(
    day: int,
    loops: int,
    profile: BackyardProfile,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict],
) -> Dict[str, Any]:
    distance = round(loops * profile.loop_km, 1)
    workout = build_workout_for_type("long", day, distance, total_km, phase, pace_zones)
    workout["distance"] = distance
    workout["key_workout_id"] = "backyard_b2b_day2"
    workout["key_workout_name"] = "Second-Day Loops"
    workout["structure"] = (
        f"{loops} × {format_km(profile.loop_km)} km loop at goal pace on "
        "yesterday's legs"
    )
    workout["description"] = (
        f"{loops} more {format_km(profile.loop_km)} km loop"
        f"{'s' if loops > 1 else ''} at goal loop pace "
        f"({_loop_pace_str(profile)}), on legs that already did yesterday's "
        "work. Fuel on the race schedule and judge the effort by how the pace "
        "feels, not by the watch."
    )
    workout["coaching_rationale"] = (
        "Hour twenty feels like the second day of a training weekend, not "
        "like the end of a long run. Starting already tired is the closest a "
        "training week gets to the back half of the race."
    )
    workout["steps"] = build_loop_simulation_steps(
        loops,
        profile.loop_km,
        profile.loop_budget_minutes,
        profile.turnaround_minutes,
        pace_zones,
        loop_pace_min_km=profile.loop_pace_min_km,
    )
    workout["fixed_structure"] = True
    return workout


def _build_loop_repeats_workout(
    workout: Dict[str, Any],
    reps: int,
    profile: BackyardProfile,
    pace_zones: Optional[Dict],
) -> None:
    """Rewrite a quality slot in place as loop-pace repeats."""
    workout["distance"] = round(reps * profile.loop_km, 1)
    workout["intensity"] = "medium"
    workout["key_workout_id"] = "backyard_loop_repeats"
    workout["key_workout_name"] = "Loop-Pace Repeats"
    workout["structure"] = (
        f"{reps} × {format_km(profile.loop_km)} km at goal loop pace, "
        "standing rest between"
    )
    workout["description"] = (
        f"{reps} × {format_km(profile.loop_km)} km at goal loop pace "
        f"({_loop_pace_str(profile)}), each off a standing rest rather than a "
        "jog. Hold the same split every rep — a fast one is a mistake, not a "
        "win, because the pace you can repeat is the only pace that counts."
    )
    workout["coaching_rationale"] = (
        "Loop pace is a rest budget, and it only becomes automatic if you "
        "rehearse hitting it cold. This is where that gets built."
    )
    workout["steps"] = build_loop_repeats_steps(
        reps,
        profile.loop_km,
        pace_zones,
        loop_pace_min_km=profile.loop_pace_min_km,
    )
    workout["fixed_structure"] = True


def _build_turnaround_drill_workout(
    workout: Dict[str, Any],
    loops: int,
    profile: BackyardProfile,
    pace_zones: Optional[Dict],
) -> None:
    """Rewrite a quality slot in place as a timed turnaround drill."""
    turn = round(profile.turnaround_minutes)
    workout["distance"] = round(loops * profile.loop_km, 1)
    workout["intensity"] = "medium"
    workout["key_workout_id"] = "backyard_turnaround_drill"
    workout["key_workout_name"] = "Turnaround Drill"
    workout["structure"] = (
        f"{loops} loops on the hour, with the transition timed each lap"
    )
    workout["description"] = (
        f"{loops} × {format_km(profile.loop_km)} km on the hour at "
        f"{_loop_pace_str(profile)}. The running is the easy part — the work "
        f"is the ~{turn} min between: bottle, food, feet, kit, corral, every "
        "lap, against a clock. Time each one and find out which step is "
        "costing you."
    )
    workout["coaching_rationale"] = (
        "Backyard runners are eliminated by the corral, not by the course. A "
        "turnaround four minutes longer than planned is four minutes of "
        "recovery you never get — every hour, for as long as you last."
    )
    workout["steps"] = build_turnaround_drill_steps(
        loops,
        profile.loop_km,
        profile.loop_budget_minutes,
        profile.turnaround_minutes,
        pace_zones,
        loop_pace_min_km=profile.loop_pace_min_km,
    )
    workout["fixed_structure"] = True


def _replace_day(
    workouts: List[Dict[str, Any]], day: int, replacement: Dict[str, Any]
) -> None:
    """Swap the entry for ``day`` in place, keeping the week's seven days."""
    for index, workout in enumerate(workouts):
        if workout.get("day") == day:
            workouts[index] = replacement
            return
    workouts.append(replacement)
    workouts.sort(key=lambda w: w.get("day", 0))


def _apply_simulation(
    workouts: List[Dict[str, Any]],
    simulation: LoopSimulation,
    profile: BackyardProfile,
    total_km: float,
    phase: str,
    pace_zones: Optional[Dict],
) -> Dict[str, Any]:
    """Install the simulation and reshape the day after it."""
    long_run = next((w for w in workouts if w.get("type") == "long"), None)
    day = long_run.get("day", _SIMULATION_DAY) if long_run else _SIMULATION_DAY
    # The simulation takes the long run's day, but never the last day of the
    # week: the format needs somewhere for the day *after* to live, and on an
    # overnight rehearsal the session itself spills into it.
    day = min(day, _SIMULATION_DAY)

    _replace_day(
        workouts,
        day,
        _build_simulation_workout(
            day, simulation, profile, total_km, phase, pace_zones
        ),
    )

    second_day_loops = 0
    if simulation.is_overnight:
        # An overnight rehearsal already spans into the next day; the runner
        # is sleeping it off, not adding a session to it.
        _replace_day(
            workouts, _SECOND_DAY, workout_builders.generate_rest_day(_SECOND_DAY)
        )
    else:
        headroom = total_km - simulation.distance_km
        if headroom >= profile.loop_km * _SECOND_DAY_HEADROOM_FACTOR:
            two_loops_affordable = (
                headroom
                >= profile.loop_km
                * _SECOND_DAY_LOOPS_LARGE_SIM
                * _SECOND_DAY_HEADROOM_FACTOR
            )
            second_day_loops = (
                _SECOND_DAY_LOOPS_LARGE_SIM
                if simulation.loops >= _LARGE_SIM_LOOPS and two_loops_affordable
                else 1
            )
            _replace_day(
                workouts,
                _SECOND_DAY,
                _build_second_day_workout(
                    _SECOND_DAY,
                    second_day_loops,
                    profile,
                    total_km,
                    phase,
                    pace_zones,
                ),
            )
        else:
            _replace_day(
                workouts,
                _SECOND_DAY,
                workout_builders.generate_rest_day(_SECOND_DAY),
            )

    return {
        "simulation_loops": simulation.loops,
        "simulation_role": simulation.role,
        "simulation_day": day,
        "second_day_loops": second_day_loops,
    }


def _apply_specific_quality(
    workouts: List[Dict[str, Any]],
    profile: BackyardProfile,
    week_in_phase: int,
    pace_zones: Optional[Dict],
) -> Optional[str]:
    """Turn the week's quality slot into a backyard-specific session.

    Returns the installed session's id, or ``None`` when the week keeps its
    generic quality day — either because no slot was big enough to carry a
    whole loop (an undersized loop session is worse than the tempo it would
    replace) or because this is an interval week the plan is deliberately
    leaving alone.
    """
    if profile.loop_km <= 0:
        return None

    # A threshold day trains an effort the race never asks for — nothing in a
    # backyard is ever run at tempo — so a tempo slot is always fair game.
    # Intervals are a different matter: the aerobic ceiling they build is what
    # keeps loop pace comfortable at hour twenty, so only every other interval
    # week is converted and the rest keep their VO2 work. Hill slots are never
    # touched; on a hilly loop they are the most specific session in the week.
    slot = next(
        (
            w
            for w in workouts
            if w.get("type") == "tempo" and (w.get("distance") or 0) > 0
        ),
        None,
    )
    # Loop repeats are the natural replacement for an interval day — same
    # shape (reps off a rest), different purpose. A tempo day has no such
    # counterpart, so it alternates between the two specific sessions and is
    # where the turnaround drill gets its weeks.
    prefer_repeats = slot is None or week_in_phase % 2 == 0
    if slot is None and week_in_phase % 2 == 1:
        slot = next(
            (
                w
                for w in workouts
                if w.get("type") == "interval" and (w.get("distance") or 0) > 0
            ),
            None,
        )
    if slot is None:
        return None

    # Loops are indivisible, and this session runs at easy pace, so it is
    # sized to the nearest whole loop rather than truncated into the budget —
    # a 12 km tempo slot becomes two loops, and the week's easy runs give back
    # the difference.
    budget = slot.get("distance") or 0
    affordable = int(round(budget / profile.loop_km))
    if affordable < _MIN_LOOP_REPEATS:
        return None

    if prefer_repeats:
        reps = min(_MAX_LOOP_REPEATS, affordable)
        _build_loop_repeats_workout(slot, reps, profile, pace_zones)
        return "backyard_loop_repeats"

    loops = min(_TURNAROUND_DRILL_LOOPS, affordable)
    _build_turnaround_drill_workout(slot, loops, profile, pace_zones)
    return "backyard_turnaround_drill"


def apply_backyard_week(
    workouts: List[Dict[str, Any]],
    *,
    phase: str,
    is_recovery: bool,
    week_in_phase: int,
    total_km: float,
    profile: BackyardProfile,
    simulation: Optional[LoopSimulation],
    pace_zones: Optional[Dict],
) -> Optional[Dict[str, Any]]:
    """Reshape one week for a backyard goal (in place).

    ``simulation`` is this week's rung of the ladder, already fitted to the
    week's volume by ``fit_simulation_to_week`` — ``None`` on weeks that carry
    none. Returns a week-level summary of what was installed, or ``None`` if
    the week was left as an ordinary ultra week (deloads always are: a deload
    with a simulation in it is not a deload).
    """
    if is_recovery:
        return None

    summary: Dict[str, Any] = {"applied": True}

    if simulation is not None:
        summary.update(
            _apply_simulation(
                workouts, simulation, profile, total_km, phase, pace_zones
            )
        )
        return summary

    if phase in ("build", "peak"):
        installed = _apply_specific_quality(
            workouts, profile, week_in_phase, pace_zones
        )
        if installed is None:
            return None
        summary["quality_id"] = installed
        return summary

    return None
