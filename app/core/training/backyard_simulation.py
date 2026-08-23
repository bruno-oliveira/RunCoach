"""Progressive loop simulations — the one session a backyard plan is built on.

Everything else in a backyard block is ordinary endurance work. The session
that actually prepares a runner for the format is the *loop simulation*: run
the race's loop, start the next one on the hour, and repeat. It rehearses the
three things no long run ever teaches —

* **restarting.** A long run is one warm-up. Twelve loops is twelve of them,
  each on legs that have been sitting still for ten minutes.
* **the turnaround.** The gap between crossing the line and the next whistle
  is where the race is won: eat, drink, change socks, deal with a hotspot,
  and be back in the corral. Runners lose races by taking 61 minutes to do a
  50-minute lap, not by running slowly.
* **the arithmetic of pace.** Loop pace is a rest budget (see
  :mod:`app.core.training.backyard_profile`), and the only way to internalise
  it is to run it repeatedly against a real clock.

This module decides *when* simulations land across a plan and *how big* each
one is. It is pure scheduling arithmetic — the weekly builder is what turns a
:class:`LoopSimulation` into a workout, and it may shrink one that does not
fit the week's budget.

Two rules shape the ladder:

* Simulations are spaced ``_SIM_SPACING_WEEKS`` apart and never land on a
  deload. A six-hour simulation *is* the week's hard training; stacking two
  in consecutive weeks buys fatigue, not adaptation.
* The ladder is anchored at its top, not its bottom. The biggest simulation
  is pinned to the last loading week before the taper (the same slot the
  trail Intensive Training Weekend uses) and the rest are stepped backwards
  from there, so the dress rehearsal always lands where there is still time
  to absorb it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, List, Literal, Optional

from app.core.training import phase_calculator
from app.core.training.backyard_profile import BackyardProfile, backyard_summary
from app.utils import format_pace

SimulationRole = Literal["introduction", "progression", "night", "dress_rehearsal"]
StartTime = Literal["morning", "evening"]

# Weeks between two simulations. Three is the gap that lets a big one be
# absorbed rather than merely survived, and it lines up with the 3:1 deload
# cadence so simulations and recovery weeks interleave instead of colliding.
_SIM_SPACING_WEEKS = 3

# The first simulation is deliberately small: three loops is long enough to
# meet the format (two restarts, two turnarounds) and short enough that the
# runner learns from it instead of being wrecked by it.
_FIRST_SIM_LOOPS = 3

# No simulation exceeds this, whatever the goal. Past ~12 hours a rehearsal
# stops being training and becomes an unrecovered race; the remaining
# specificity has to come from the event itself.
_MAX_SIM_LOOPS = 12

# Share of the goal the biggest rehearsal reaches. It falls as the goal
# rises — half of 12 loops is a hard weekend, half of 36 is a second
# race — so ambitious runners rehearse a smaller *fraction* of a much bigger
# night.
_TIER_PEAK_SIM_FRACTION: Dict[str, float] = {
    "first_timer": 0.60,
    "day": 0.50,
    "night": 0.42,
    "multi_day": 0.35,
}

# Share of the week's volume a simulation may claim. The dress rehearsal is
# allowed to be the week (that is the point of it); ordinary simulations
# leave room for the rest of the training week around them.
_SIM_WEEK_SHARE = 0.55
_DRESS_REHEARSAL_WEEK_SHARE = 0.70

# A simulation below this is not one — it is a long run with a drink stop.
_MIN_SIM_LOOPS = 2


@dataclass(frozen=True)
class LoopSimulation:
    """One scheduled loop simulation."""

    week_number: int
    loops: int
    loop_km: float
    role: SimulationRole
    start_time: StartTime

    @property
    def distance_km(self) -> float:
        return round(self.loops * self.loop_km, 1)

    @property
    def elapsed_hours(self) -> int:
        """Hours the session occupies — loops run on the hour, so: loops."""
        return self.loops

    @property
    def is_overnight(self) -> bool:
        return self.start_time == "evening"

    @property
    def label(self) -> str:
        return f"{self.loops}-Loop Simulation"

    def with_loops(self, loops: int) -> "LoopSimulation":
        """A copy resized to ``loops`` — used when the week can't afford it."""
        return LoopSimulation(
            week_number=self.week_number,
            loops=loops,
            loop_km=self.loop_km,
            role=self.role,
            start_time=self.start_time,
        )


def peak_simulation_loops(profile: BackyardProfile) -> int:
    """Loop count of the dress rehearsal for this goal."""
    raw = round(profile.target_loops * _TIER_PEAK_SIM_FRACTION[profile.tier])
    return int(max(_FIRST_SIM_LOOPS + 1, min(_MAX_SIM_LOOPS, raw)))


def _candidate_weeks(weeks: int, phases: Dict[str, int]) -> List[int]:
    """Loading weeks a simulation may land on, latest first.

    Starts once the runner is halfway through base — before that there is no
    aerobic floor under the session — and stops at the last loading week
    before the taper. Deloads are excluded outright.
    """
    base = phases.get("base", 0)
    loading_end = base + phases.get("build", 0) + phases.get("peak", 0)
    loading_end = min(loading_end, weeks)
    earliest = max(3, base // 2 + 1)
    recovery = phase_calculator.recovery_week_set(phases)
    return [w for w in range(loading_end, earliest - 1, -1) if w not in recovery]


def _loops_for_rung(index: int, rungs: int, first: int, peak: int) -> int:
    """Loop count for rung ``index`` of a ``rungs``-long ladder."""
    if rungs <= 1:
        return peak
    span = peak - first
    return int(round(first + span * (index / (rungs - 1))))


def build_simulation_schedule(
    weeks: int,
    phases: Dict[str, int],
    profile: BackyardProfile,
) -> Dict[int, LoopSimulation]:
    """Map week number -> :class:`LoopSimulation` for one plan.

    Weeks with no simulation are simply absent. The returned schedule is
    deterministic: same plan shape and goal, same ladder.
    """
    candidates = _candidate_weeks(weeks, phases)
    if not candidates:
        return {}

    # Walk backwards from the last loading week, honouring the spacing rule.
    chosen: List[int] = []
    next_allowed = candidates[0]
    for week in candidates:
        if week <= next_allowed:
            chosen.append(week)
            next_allowed = week - _SIM_SPACING_WEEKS
    chosen.reverse()

    peak_loops = peak_simulation_loops(profile)
    # A ladder needs somewhere to climb from: cap the rung count so each step
    # is a real increase rather than the same session three times over.
    max_rungs = max(1, peak_loops - _FIRST_SIM_LOOPS + 1)
    if len(chosen) > max_rungs:
        chosen = chosen[-max_rungs:]

    rungs = len(chosen)
    # The night rehearsal is the rung before the dress rehearsal — close
    # enough to the race to matter, far enough out that a bad night in the
    # dark is still a lesson rather than a setback.
    night_index = rungs - 2 if (profile.runs_in_darkness and rungs >= 3) else -1

    schedule: Dict[int, LoopSimulation] = {}
    for index, week in enumerate(chosen):
        loops = _loops_for_rung(index, rungs, _FIRST_SIM_LOOPS, peak_loops)
        if index == rungs - 1:
            role: SimulationRole = "dress_rehearsal"
            start: StartTime = "evening" if profile.crosses_full_night else "morning"
        elif index == night_index:
            role = "night"
            start = "evening"
        elif index == 0:
            role = "introduction"
            start = "morning"
        else:
            role = "progression"
            start = "morning"
        schedule[week] = LoopSimulation(
            week_number=week,
            loops=loops,
            loop_km=profile.loop_km,
            role=role,
            start_time=start,
        )
    return schedule


def fit_simulation_to_week(
    simulation: LoopSimulation,
    week_total_km: float,
    long_run_km: float = 0.0,
) -> Optional[LoopSimulation]:
    """Bound a scheduled simulation by the week it has to live in.

    The ladder is written against the goal, not against the runner, so both
    ends need the week's opinion:

    * **Ceiling** — a 10-loop rehearsal is 67 km, more than a whole week for
      many runners early in a plan. The week gets the veto and the session
      drops rungs rather than blowing the progression open.
    * **Floor** — the simulation takes the long run's place, so it must not be
      *smaller* than the long run it displaced. Handing a runner who is
      already doing 40 km long runs a three-hour rehearsal would make the
      simulation week the easiest week of the block, and the loop format is
      the gentler way to cover that distance anyway: the same kilometres,
      spread over hours, with a sit-down every one of them.

    Returns ``None`` when even the minimum won't fit.
    """
    if simulation.loop_km <= 0 or week_total_km <= 0:
        return None
    share = (
        _DRESS_REHEARSAL_WEEK_SHARE
        if simulation.role == "dress_rehearsal"
        else _SIM_WEEK_SHARE
    )
    affordable = int((week_total_km * share) // simulation.loop_km)
    floor = ceil(long_run_km / simulation.loop_km) if long_run_km > 0 else 0
    loops = min(max(simulation.loops, floor), affordable)
    if loops < _MIN_SIM_LOOPS:
        return None
    return simulation if loops == simulation.loops else simulation.with_loops(loops)


_PHASE_FOCUS: Dict[str, str] = {
    "base": (
        "Build the aerobic floor and get comfortable at loop pace. Volume and "
        "consistency now; the loops come later."
    ),
    "build": (
        "Repeatability. Start stacking loops on the hour and make the "
        "turnaround a routine you don't have to think about."
    ),
    "peak": (
        "Full rehearsals — real food, real drop bag, real headlamp. Practise "
        "the hour you'll be worst at, not the one you'll be best at."
    ),
    "taper": (
        "Nothing left to gain. Bank sleep, rehearse the routine, keep the legs "
        "open and let the fitness surface."
    ),
}


def _simulation_payload(simulation: LoopSimulation) -> Dict[str, object]:
    return {
        "loops": simulation.loops,
        "distance_km": simulation.distance_km,
        "elapsed_hours": simulation.elapsed_hours,
        "role": simulation.role,
        "start_time": simulation.start_time,
        "overnight": simulation.is_overnight,
        "label": simulation.label,
    }


def weekly_backyard_focus(
    phase: str,
    is_recovery_week: bool,
    profile: BackyardProfile,
    simulation: Optional[LoopSimulation] = None,
) -> Dict[str, object]:
    """The per-week backyard block rendered on the plan card.

    Always enabled on a backyard plan: the loop-pace and turnaround numbers
    are the runner's operating instructions for every week, not just the ones
    carrying a simulation.
    """
    focus = _PHASE_FOCUS.get(phase, _PHASE_FOCUS["build"])
    if is_recovery_week:
        focus = (
            "Deload. Absorb the last block — the next simulation is only worth "
            "running on legs that have recovered from this one."
        )
    return {
        **backyard_summary(profile),
        "enabled": True,
        "focus": focus,
        "simulation": _simulation_payload(simulation) if simulation else None,
        "guidance": (
            f"Every loop starts on the hour. Run it in about "
            f"{round(profile.loop_budget_minutes)} min "
            f"({format_pace(profile.loop_pace_min_km)}) and the remaining "
            f"{round(profile.turnaround_minutes)} min are yours to eat, drink "
            "and reset in. Going faster doesn't buy a loop — it only buys "
            "more sitting down, and the legs pay for it later."
        ),
    }
