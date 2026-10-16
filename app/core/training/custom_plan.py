"""Custom plans: the runner chooses the sessions, the engine still sizes them.

A custom plan is an ordinary generated plan with one difference: for each
phase and each *slot* of the week (the long run, and the one or two quality
days), the runner names the catalog sessions that fill it, and the generator
rotates through them instead of through its own pick. Everything else — the
weekly volume, the phase arc, the deloads, the taper, how far each session
runs and at what pace — stays the engine's, because it is the engine's
guarantees (ramp caps, long-run ceilings, the Daniels share caps) that make a
plan safe to follow.

The grid follows what the frequency composers actually schedule (measured in
``docs/custom-plans-implementation-plan.md``, Phase 0): base weeks carry no
quality day at any frequency, so base offers only the long run; at 3–4 runs a
build or peak week has one quality day, whose type the runner's pick decides;
at 5–6 runs it has a speed day and a threshold/climb day. The taper is never
the runner's: it is structural.

Pure: no I/O, no ORM. Problems are returned as keys plus figures, never
prose, so the web layer words and translates them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.core.training.periodization.phase_calculator import (
    MIN_WEEKS_FOR_PHASES,
    calculate_phases,
    recovery_week_set,
)
from app.core.training.workouts.key_workout_library.selection import (
    KeyWorkoutLibrary,
    custom_eligible_sessions,
)
from app.core.training.workouts.long_run_shapes import get_shape, shapes_for_phase

CUSTOM_PHASES: Tuple[str, ...] = ("base", "build", "peak")
MIN_RUNS_PER_WEEK = 3
MAX_RUNS_PER_WEEK = 6
# A cell takes at most this many choices — and never more than the weeks it
# fills (``cell_limits``): a choice past that would never come round.
MAX_SESSIONS_PER_CELL = 5
MAX_STRENGTH_SESSIONS = 2
SPEC_VERSION = 1


class SlotKind(str, Enum):
    """A slot of the week, as the runner sees it."""

    LONG = "long"
    QUALITY = "quality"  # the single quality day at 3–4 runs a week
    SPEED = "speed"  # the interval day at 5–6 runs
    THRESHOLD = "threshold"  # the tempo / hill day at 5–6 runs


# The catalog ``type`` each quality slot accepts.
SLOT_WORKOUT_TYPES: Dict[SlotKind, Tuple[str, ...]] = {
    SlotKind.QUALITY: ("interval", "tempo", "hill"),
    SlotKind.SPEED: ("interval",),
    SlotKind.THRESHOLD: ("tempo", "hill"),
}

# A threshold/climb day sits in the same week as the speed day, so a VO2max or
# repetition-pace session there would make two VO2 days a week — the one rule
# the book's skeleton states twice.
_THRESHOLD_FORBIDDEN_ZONES = frozenset({"I", "R"})

STRENGTH_TEMPLATES = ("auto", "climb_descent")


def slot_grid(runs_per_week: int) -> Dict[str, Tuple[SlotKind, ...]]:
    """The cells a runner chooses for, per phase, at this frequency."""
    quality: Tuple[SlotKind, ...] = (
        (SlotKind.QUALITY,)
        if runs_per_week <= 4
        else (SlotKind.SPEED, SlotKind.THRESHOLD)
    )
    return {
        "base": (SlotKind.LONG,),
        "build": (SlotKind.LONG, *quality),
        "peak": (SlotKind.LONG, *quality),
    }


@dataclass(frozen=True)
class PhaseSpan:
    """One phase of the plan as the builder draws it: where it sits, how long.

    ``training_weeks`` are the weeks a cell's choices actually fill; the
    phase's recovery weeks keep the engine's easy long run and drop the quality
    day, and every taper week is the engine's.
    """

    phase: str
    first_week: int
    weeks: int
    recovery_weeks: Tuple[int, ...]

    @property
    def last_week(self) -> int:
        return self.first_week + self.weeks - 1

    @property
    def training_weeks(self) -> int:
        return 0 if self.phase == "taper" else self.weeks - len(self.recovery_weeks)


def plan_shape(
    weeks: int, *, target_distance: float, trail_profile=None
) -> List[PhaseSpan]:
    """The plan's phases in order, taper included, with their recovery weeks.

    Raises ``InsufficientTimeException`` (from ``calculate_phases``) for a plan
    too short to periodise.
    """
    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    recovery = recovery_week_set(phases)
    spans: List[PhaseSpan] = []
    start = 1
    for phase in (*CUSTOM_PHASES, "taper"):
        length = phases.get(phase, 0)
        if length <= 0:
            continue
        span = range(start, start + length)
        spans.append(
            PhaseSpan(
                phase=phase,
                first_week=start,
                weeks=length,
                recovery_weeks=tuple(w for w in span if w in recovery),
            )
        )
        start += length
    return spans


def phase_loading_weeks(
    weeks: int, *, target_distance: float, trail_profile=None
) -> Dict[str, int]:
    """How many non-recovery weeks each choosable phase has in this plan.

    A recovery week installs none of the runner's choices (it keeps the
    engine's easy long run and drops the quality day), so these are the weeks
    a cell's rotation actually walks through.
    """
    counts = {phase: 0 for phase in CUSTOM_PHASES}
    for span in plan_shape(
        weeks, target_distance=target_distance, trail_profile=trail_profile
    ):
        if span.phase in counts:
            counts[span.phase] = span.training_weeks
    return counts


def cell_limits(
    weeks: Optional[int], *, target_distance: float, trail_profile=None
) -> Dict[str, int]:
    """The most choices each phase's cells may hold for a plan this long.

    One choice per week the phase fills, up to ``MAX_SESSIONS_PER_CELL``, and
    never fewer than one. With no length (or one too short to periodise, which
    generation refuses anyway) every phase gets the ceiling.
    """
    if weeks is None or weeks < MIN_WEEKS_FOR_PHASES:
        return {phase: MAX_SESSIONS_PER_CELL for phase in CUSTOM_PHASES}
    loading = phase_loading_weeks(
        weeks, target_distance=target_distance, trail_profile=trail_profile
    )
    return {
        phase: max(1, min(MAX_SESSIONS_PER_CELL, loading[phase]))
        for phase in CUSTOM_PHASES
    }


@dataclass(frozen=True)
class StrengthChoice:
    """How many strength sessions a week, and which kind."""

    sessions_per_week: int = 2
    template: str = "auto"


@dataclass(frozen=True)
class CustomPlanSpec:
    """The runner's choices: phase → slot → catalog ids, plus strength."""

    menus: Mapping[str, Mapping[SlotKind, Tuple[str, ...]]]
    strength: StrengthChoice = field(default_factory=StrengthChoice)

    def menu(self, phase: str, slot: SlotKind) -> Tuple[str, ...]:
        return tuple(self.menus.get(phase, {}).get(slot, ()))

    def to_json(self) -> Dict[str, Any]:
        return {
            "version": SPEC_VERSION,
            "menus": {
                phase: {slot.value: list(ids) for slot, ids in cells.items()}
                for phase, cells in self.menus.items()
            },
            "strength": {
                "sessions_per_week": self.strength.sessions_per_week,
                "template": self.strength.template,
            },
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "CustomPlanSpec":
        """Read a stored or submitted spec. Unknown slots raise ``ValueError``."""
        menus: Dict[str, Dict[SlotKind, Tuple[str, ...]]] = {}
        for phase, cells in (raw.get("menus") or {}).items():
            menus[str(phase)] = {
                SlotKind(slot): tuple(str(i) for i in ids)
                for slot, ids in (cells or {}).items()
            }
        strength_raw = raw.get("strength") or {}
        strength = StrengthChoice(
            sessions_per_week=int(strength_raw.get("sessions_per_week", 2)),
            template=str(strength_raw.get("template", "auto")),
        )
        return cls(menus=menus, strength=strength)


@dataclass(frozen=True)
class SessionOption:
    """One choosable session, as the builder page lists it."""

    id: str
    name: str
    structure: str
    rationale: str
    intensity: str
    workout_type: str


@dataclass(frozen=True)
class Problem:
    """One reason a spec can't be generated: a key plus where it applies."""

    key: str
    phase: Optional[str] = None
    slot: Optional[str] = None
    workout_id: Optional[str] = None
    limit: Optional[int] = None


def eligible_options(
    phase: str,
    slot: SlotKind,
    *,
    target_distance: float,
    trail_profile=None,
    terrain: Optional[str] = None,
) -> List[SessionOption]:
    """Every session the runner may put in a cell, in catalog order."""
    if slot is SlotKind.LONG:
        return [
            SessionOption(s.id, s.name, s.structure, s.rationale, "medium", "long")
            for s in shapes_for_phase(phase)
        ]
    entries = custom_eligible_sessions(
        phase,
        SLOT_WORKOUT_TYPES[slot],
        target_distance=target_distance,
        trail_profile=trail_profile,
        terrain=terrain,
    )
    if slot is SlotKind.THRESHOLD:
        entries = [
            w for w in entries if w.get("pace_zone") not in _THRESHOLD_FORBIDDEN_ZONES
        ]
    return [
        SessionOption(
            w["id"],
            w["name"],
            w["structure"],
            w["rationale"],
            w.get("intensity", "medium"),
            w["type"],
        )
        for w in entries
    ]


def validate_spec(
    spec: CustomPlanSpec,
    *,
    runs_per_week: int,
    target_distance: float,
    trail_profile=None,
    terrain: Optional[str] = None,
    weeks: Optional[int] = None,
) -> List[Problem]:
    """Every reason ``spec`` cannot become a plan; empty when it can.

    ``weeks`` bounds each cell by the weeks its phase fills (``cell_limits``);
    without it only the absolute ceiling applies.
    """
    problems: List[Problem] = []
    if runs_per_week < MIN_RUNS_PER_WEEK:
        problems.append(Problem("too_few_runs", limit=MIN_RUNS_PER_WEEK))
        return problems
    if runs_per_week > MAX_RUNS_PER_WEEK:
        problems.append(Problem("too_many_runs", limit=MAX_RUNS_PER_WEEK))
        return problems

    strength = spec.strength
    if not 0 <= strength.sessions_per_week <= MAX_STRENGTH_SESSIONS:
        problems.append(Problem("strength_sessions", limit=MAX_STRENGTH_SESSIONS))
    if strength.template not in STRENGTH_TEMPLATES:
        problems.append(Problem("strength_template"))

    grid = slot_grid(runs_per_week)
    limits = cell_limits(
        weeks, target_distance=target_distance, trail_profile=trail_profile
    )
    for phase, cells in spec.menus.items():
        if phase not in grid:
            problems.append(Problem("unknown_phase", phase=phase))
            continue
        for slot in cells:
            if slot not in grid[phase]:
                problems.append(Problem("unknown_slot", phase=phase, slot=slot.value))

    for phase, slots in grid.items():
        for slot in slots:
            ids = spec.menu(phase, slot)
            if not ids:
                problems.append(Problem("empty_cell", phase=phase, slot=slot.value))
                continue
            if len(ids) > limits[phase]:
                problems.append(
                    Problem(
                        "too_many_sessions",
                        phase=phase,
                        slot=slot.value,
                        limit=limits[phase],
                    )
                )
            if len(set(ids)) != len(ids):
                problems.append(
                    Problem("duplicate_session", phase=phase, slot=slot.value)
                )
            allowed = {
                o.id
                for o in eligible_options(
                    phase,
                    slot,
                    target_distance=target_distance,
                    trail_profile=trail_profile,
                    terrain=terrain,
                )
            }
            for workout_id in ids:
                if workout_id not in allowed:
                    problems.append(
                        Problem(
                            "ineligible_session",
                            phase=phase,
                            slot=slot.value,
                            workout_id=workout_id,
                        )
                    )
    return problems


def default_spec(
    runs_per_week: int,
    *,
    target_distance: float,
    trail_profile=None,
    terrain: Optional[str] = None,
    weeks: Optional[int] = None,
) -> CustomPlanSpec:
    """A valid starting point for every cell, within ``cell_limits``.

    The builder page opens on this, so a runner who changes nothing still gets
    a plan, and every cell shows something real to swap. A single quality day
    starts on two *kinds* of session — threshold first from the half marathon
    up, speed first below it — rather than the catalog's first two, which are
    both VO2max work and would leave a half marathoner without a tempo.
    """
    menus: Dict[str, Dict[SlotKind, Tuple[str, ...]]] = {}
    limits = cell_limits(
        weeks, target_distance=target_distance, trail_profile=trail_profile
    )
    for phase, slots in slot_grid(runs_per_week).items():
        menus[phase] = {}
        for slot in slots:
            options = eligible_options(
                phase,
                slot,
                target_distance=target_distance,
                trail_profile=trail_profile,
                terrain=terrain,
            )
            if slot is SlotKind.LONG:
                preferred = [
                    o.id
                    for o in options
                    if o.id in ("negative_split_long", "steady_long")
                ]
                menus[phase][slot] = tuple(preferred[:2] or [o.id for o in options[:1]])
            elif slot is SlotKind.QUALITY:
                menus[phase][slot] = _mixed_quality_default(options, target_distance)
            else:
                menus[phase][slot] = tuple(o.id for o in options[:2])
            menus[phase][slot] = menus[phase][slot][: limits[phase]]
    return CustomPlanSpec(menus=menus)


def _mixed_quality_default(
    options: Sequence[SessionOption], target_distance: float
) -> Tuple[str, ...]:
    """The first session of the two kinds this goal leans on, in that order."""
    kinds = ("tempo", "interval") if target_distance >= 21.0 else ("interval", "tempo")
    picks = [
        next((o.id for o in options if o.workout_type == kind), None) for kind in kinds
    ]
    chosen = tuple(i for i in picks if i is not None)
    return chosen or tuple(o.id for o in options[:2])


class CustomRotation:
    """Plan-level memory of which choice each cell is on.

    One instance per generated plan, like ``KeyWorkoutRotationState``. Each
    cell walks its own menu in the runner's order, one step per use, so every
    choice appears evenly however the weeks fall. Deterministic: no RNG.
    """

    def __init__(self, spec: CustomPlanSpec, runs_per_week: int) -> None:
        self.spec = spec
        self.runs_per_week = runs_per_week
        self._uses: Dict[Tuple[str, SlotKind], int] = defaultdict(int)
        self._single_slot_turns = 0

    def ordered(self, phase: str, slot: SlotKind) -> List[str]:
        """The cell's menu, starting at the choice whose turn it is."""
        menu = list(self.spec.menu(phase, slot))
        if not menu:
            return []
        start = self._uses[(phase, slot)] % len(menu)
        return menu[start:] + menu[:start]

    def advance(self, phase: str, slot: SlotKind, steps: int = 1) -> None:
        """Move the cell on by ``steps`` — past whichever choice actually ran.

        When the choice whose turn it was needs more room than the day has, a
        later one stands in; advancing past the stand-in (not just one step)
        keeps it from standing in again next week while the others wait.
        """
        self._uses[(phase, slot)] += steps

    def quality_slots(self, phase: str, quality_days: int) -> List[SlotKind]:
        """Which cell fills each of the week's ``quality_days`` quality days.

        At 3–4 runs the one quality day is the QUALITY cell. At 5–6 runs two
        days are SPEED then THRESHOLD; a week the composer gives a single
        quality day alternates between the two so neither is starved; a third
        day (never produced today) is left to the engine.
        """
        if phase not in ("build", "peak") or quality_days <= 0:
            return []
        if self.runs_per_week <= 4:
            return [SlotKind.QUALITY]
        if quality_days == 1:
            turn = self._single_slot_turns
            self._single_slot_turns += 1
            return [SlotKind.SPEED if turn % 2 == 0 else SlotKind.THRESHOLD]
        return [SlotKind.SPEED, SlotKind.THRESHOLD]


def session_type(workout_id: str) -> Optional[str]:
    """The workout type a chosen session is installed as (``None`` if unknown)."""
    if get_shape(workout_id) is not None:
        return "long"
    entry = KeyWorkoutLibrary.get_by_id(workout_id)
    return entry["type"] if entry else None


def quality_assignment(
    rotation: CustomRotation,
    phase: str,
    distribution: Mapping[str, int],
) -> Optional[List[Tuple[SlotKind, List[str]]]]:
    """The week's quality days as (cell, ordered menu) pairs, or ``None``.

    ``None`` means the week is not the runner's to choose (base, taper, or no
    quality day), and the engine's own selection stands.
    """
    quality_days = sum(distribution.get(t, 0) for t in ("interval", "tempo", "hill"))
    slots = rotation.quality_slots(phase, quality_days)
    if not slots:
        return None
    assignment = []
    for slot in slots:
        menu = rotation.ordered(phase, slot)
        if menu:
            assignment.append((slot, menu))
    return assignment or None


def rewrite_distribution(
    distribution: Mapping[str, int],
    assignment: Sequence[Tuple[SlotKind, List[str]]],
) -> Dict[str, int]:
    """The week's distribution with its quality days typed by the picks.

    The quality budget is computed per type (``_quality_budgets``), so the
    type must be the installed session's *before* budgeting: an interval pick
    on a day the engine had sized as a tempo would otherwise run on a tempo's
    budget and min dose.
    """
    # Every key the schedulers read stays present, at zero if unused.
    rewritten = dict(distribution)
    for t in ("interval", "tempo", "hill"):
        rewritten[t] = 0
    original_days = sum(distribution.get(t, 0) for t in ("interval", "tempo", "hill"))
    placed = 0
    for _slot, menu in assignment:
        wtype = session_type(menu[0])
        if wtype in ("interval", "tempo", "hill"):
            rewritten[wtype] = rewritten.get(wtype, 0) + 1
            placed += 1
    # Days beyond the runner's cells keep the engine's types.
    if placed < original_days:
        leftovers = [
            t
            for t in ("interval", "tempo", "hill")
            for _ in range(distribution.get(t, 0))
        ][placed:]
        for t in leftovers:
            rewritten[t] = rewritten.get(t, 0) + 1
    return rewritten
